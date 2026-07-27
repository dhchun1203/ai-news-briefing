// 실제로 생성된 HTML을 jsdom에 띄우고 공용 site.js를 실행해, 모든 페이지에서 인터랙션이
// 정상 동작하는지 확인한다. 브라우저가 없는 환경에서 할 수 있는 가장 실제에 가까운 검증이라,
// templates/static/site.js를 3개 템플릿에서 추출할 때 회귀를 잡아준 테스트다.
//
// jsdom은 devDependency이지만 이 저장소는 package.json을 두지 않는 방침이라(런타임 의존성
// 0개) 설치돼 있지 않으면 조용히 건너뛴다. CI는 npm install jsdom --no-save로 설치한다.
//   사용법: node tests/dom_smoke.test.js [docs디렉토리]
let JSDOM, VirtualConsole;
try {
  ({ JSDOM, VirtualConsole } = require("jsdom"));
} catch (e) {
  console.log("SKIP: jsdom 미설치 (npm install jsdom --no-save 후 다시 실행)");
  process.exit(0);
}

const fs = require("fs");
const path = require("path");

const DOCS = process.argv[2] || path.join(__dirname, "..", "docs");

const SITE_JS = fs.readFileSync(path.join(DOCS, "site.js"), "utf-8");

const results = [];
function check(page, name, cond, extra = "") {
  results.push({ page, name, ok: !!cond, extra });
}

function load(relPath, urlOverride) {
  const file = path.join(DOCS, relPath);
  const html = fs.readFileSync(file, "utf-8");
  const vc = new VirtualConsole();
  const errors = [];
  vc.on("jsdomError", (e) => errors.push(e.message));
  const dom = new JSDOM(html, {
    url: urlOverride || "https://www.dailyaithread.com/" + relPath.replace(/\\/g, "/"),
    runScripts: "dangerously",
    pretendToBeVisual: true,
    virtualConsole: vc,
  });
  const { window } = dom;
  // clipboard 스텁 (jsdom 미구현)
  window.navigator.clipboard = { writeText: () => Promise.resolve() };
  // 공용 스크립트를 <script defer>처럼 문서 파싱 후 실행
  window.eval(SITE_JS);
  return { window, doc: window.document, errors };
}

// vercel.json의 cleanUrls:true는 <파일명>.html 요청을 확장자·트레일링 슬래시 없는
// 경로로 308 리다이렉트한다(예: /topics/index.html -> /topics). 그 결과 실제로
// 브라우저에 남는 URL은 이 파일의 디스크 경로와 "세그먼트 깊이"가 다를 수 있고,
// 페이지 안의 상대경로(href="agents.html" 등)는 파일 경로가 아니라 이 최종 URL
// 기준으로 풀린다. templates/topic.html.j2가 항상 "한 단계 아래"로 가정해 깨졌던
// 사고(주제 목록 페이지 /topics에서 개별 주제 링크가 /agents.html로 잘못 풀려 404)가
// 바로 이 어긋남 때문이었다. 이 함수는 실제 배포 시 브라우저가 보게 될 clean URL을
// base로 놓고 모든 상대 링크/자산이 실제 파일로 해석되는지 전수 검사해, 같은 종류의
// 사고가 어느 페이지에서도 조용히 재발하지 않게 한다.
function resolveExists(absUrl) {
  let p = absUrl.replace(/^https?:\/\/[^/]+/, "").replace(/^\//, "");
  if (p === "") p = "index.html";
  const candidates = [path.join(DOCS, p), path.join(DOCS, p + ".html"), path.join(DOCS, p, "index.html")];
  return candidates.some((c) => fs.existsSync(c));
}

function checkCleanUrlLinks(relPath, canonicalUrl, label) {
  const { doc } = load(relPath, canonicalUrl);
  const refs = [];
  doc.querySelectorAll("a[href]").forEach((a) => refs.push([a.getAttribute("href"), a.href]));
  doc.querySelectorAll("link[href]").forEach((l) => refs.push([l.getAttribute("href"), l.href]));
  doc.querySelectorAll("script[src]").forEach((s) => refs.push([s.getAttribute("src"), s.src]));
  const broken = [];
  refs.forEach(([raw, resolved]) => {
    if (!raw || raw.startsWith("#") || raw.startsWith("http") || raw.startsWith("mailto:")) return;
    // Vercel이 런타임에 직접 서빙하는 절대경로라 로컬 docs/에는 실존하지 않는 게 정상 —
    // 상대경로 계산과 무관하므로 이 검사 대상이 아니다.
    if (raw.startsWith("/_vercel/")) return;
    if (!resolveExists(resolved)) broken.push(`${raw} -> ${resolved}`);
  });
  check(label, `실제 배포 URL(${canonicalUrl})에서 모든 상대 링크가 실존 파일로 해석됨`, broken.length === 0, broken.join(" | "));
}

function exercise(relPath, label, opts = {}) {
  const { window, doc, errors } = load(relPath);
  check(label, "스크립트 실행 중 에러 없음", errors.length === 0, errors.join(" | "));

  // --- 테마 토글 ---
  const themeBtn = doc.getElementById("theme-toggle");
  if (themeBtn) {
    const before = doc.documentElement.getAttribute("data-theme");
    themeBtn.click();
    const after = doc.documentElement.getAttribute("data-theme");
    check(label, "테마 토글이 data-theme을 바꾼다", before !== after, `${before} -> ${after}`);
    check(label, "테마 토글이 쿠키에 저장한다", /theme=/.test(doc.cookie), doc.cookie);
    check(label, "테마 토글 aria-checked 반영", themeBtn.getAttribute("aria-checked") === String(after === "dark"));
  }

  // --- 언어 토글 ---
  const trigger = doc.getElementById("lang-select-trigger");
  const list = doc.getElementById("lang-select-list");
  if (trigger && list) {
    check(label, "언어 목록 초기 닫힘", list.hidden === true);
    trigger.click();
    check(label, "트리거 클릭 시 열림", list.hidden === false && trigger.getAttribute("aria-expanded") === "true");
    const enOpt = list.querySelector('li[data-lang-value="en"]');
    enOpt.click();
    check(label, "영어 선택 시 data-lang=en", doc.documentElement.getAttribute("data-lang") === "en");
    check(label, "영어 선택 시 lang 속성도 en", doc.documentElement.getAttribute("lang") === "en");
    check(label, "영어 선택 시 title 교체", doc.title === doc.documentElement.getAttribute("data-title-en"), doc.title);
    check(label, "선택 후 목록 닫힘", list.hidden === true);
    check(label, "aria-selected 갱신됨(새로 추가한 접근성 개선)", enOpt.getAttribute("aria-selected") === "true");
    check(label, "localStorage에 저장", window.localStorage.getItem("lang") === "en");

    // placeholder가 언어에 맞게 바뀌는지 (weekly에는 입력이 없어 skip)
    const ph = doc.querySelector("[data-placeholder-ko]");
    if (ph) {
      check(label, "언어 전환 시 placeholder도 영어로", ph.getAttribute("placeholder") === ph.getAttribute("data-placeholder-en"), ph.getAttribute("placeholder"));
    }
    // aria-label은 속성값이라 .lang-ko/.lang-en CSS 토글로는 안 바뀐다 — 영어 모드에서
    // 스크린리더가 한국어 라벨을 읽던 문제.
    const arias = doc.querySelectorAll("[data-aria-ko]");
    check(label, "이중언어 aria-label 요소가 존재", arias.length > 0, `count=${arias.length}`);
    let ariaOk = true;
    arias.forEach((el) => {
      if (el.getAttribute("aria-label") !== el.getAttribute("data-aria-en")) ariaOk = false;
    });
    check(label, "언어 전환 시 aria-label도 영어로", ariaOk,
      Array.from(arias).map((e) => e.getAttribute("aria-label")).join(" | "));
    // 되돌리기
    trigger.click();
    list.querySelector('li[data-lang-value="ko"]').click();
    check(label, "한국어로 되돌리면 data-lang=ko", doc.documentElement.getAttribute("data-lang") === "ko");
  }

  // --- 공유 버튼 (live region) ---
  const shareBtn = doc.getElementById("share-button");
  const tooltip = doc.getElementById("share-tooltip");
  if (shareBtn && tooltip) {
    check(label, "툴팁이 빈 채로 시작(live region 필수 조건)", tooltip.textContent.trim() === "");
    shareBtn.click();
    return new Promise((resolve) => {
      setTimeout(() => {
        check(label, "복사 후 툴팁 텍스트가 채워짐(스크린리더가 읽음)", tooltip.textContent.trim().length > 0, JSON.stringify(tooltip.textContent));
        check(label, "복사 후 visible 클래스", tooltip.classList.contains("visible"));
        finishPage(label, doc, window, opts);
        resolve();
      }, 20);
    });
  }
  finishPage(label, doc, window, opts);
  return Promise.resolve();
}

function finishPage(label, doc, window, opts) {
  // --- 용어 패널 ---
  const panel = doc.getElementById("term-panel");
  if (panel) {
    check(label, "닫힌 패널에 inert (탭 포커스 차단)", panel.hasAttribute("inert"));
    const termLink = doc.querySelector(".term-link");
    if (termLink) {
      termLink.click();
      check(label, "용어 클릭 시 패널 열림", panel.classList.contains("open"));
      check(label, "열린 패널은 inert 해제", !panel.hasAttribute("inert"));
      check(label, "패널에 용어 제목 채워짐", doc.getElementById("term-panel-title").textContent.length > 0);
      check(label, "패널에 설명 채워짐", doc.getElementById("term-panel-body").textContent.length > 0);
      const esc = new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true });
      doc.dispatchEvent(esc);
      check(label, "Escape로 닫힘", !panel.classList.contains("open"));
      check(label, "닫으면 다시 inert", panel.hasAttribute("inert"));
    } else if (opts.expectTermLinks) {
      check(label, "용어 링크가 존재해야 함", false, "term-link 없음");
    }
  }

  // --- 아카이브 검색 입력 존재 시 ---
  const search = doc.getElementById("archive-search-input");
  if (search) {
    check(label, "검색 입력 placeholder 설정됨", (search.getAttribute("placeholder") || "").length > 0);
  }

  // --- 용어사전 목록 검색 ---
  const gs = doc.getElementById("glossary-search-input");
  if (gs) {
    const terms = doc.querySelectorAll(".glossary-term");
    gs.value = "zzzznomatch";
    gs.dispatchEvent(new window.Event("input", { bubbles: true }));
    const hidden = Array.from(terms).filter((t) => t.hidden).length;
    check(label, "용어 검색 필터 동작(전부 숨김)", hidden === terms.length, `${hidden}/${terms.length}`);
    gs.value = "";
    gs.dispatchEvent(new window.Event("input", { bubbles: true }));
    const shown = Array.from(terms).filter((t) => !t.hidden).length;
    check(label, "검색어 지우면 전부 표시", shown === terms.length);
  }

  // --- 뒤로가기 버튼 ---
  const back = doc.getElementById("glossary-back");
  if (back) check(label, "뒤로가기 버튼 존재", true);

  // --- 주제 칩 / FAQ / 피드 링크 ---
  // 칩과 배지는 digest에 필드가 있어야만 렌더링되므로, 옵션으로 기대치를 넘긴
  // 페이지에서만 확인한다(과거 아카이브에는 없을 수 있다).
  if (opts.expectTopicChips) {
    const chips = doc.querySelectorAll(".topic-chip");
    check(label, "주제 칩이 렌더링됨", chips.length > 0, `count=${chips.length}`);
    let hrefOk = true;
    chips.forEach((c) => {
      // 링크가 페이지 위치에 맞는 상대경로여야 한다(/en/과 /archive/는 한 단계 아래).
      if (!/topics\/[a-z]+\.html$/.test(c.getAttribute("href") || "")) hrefOk = false;
    });
    check(label, "주제 칩 링크가 topics/<slug>.html 형태", hrefOk);
  }

  if (opts.expectFaq) {
    const items = doc.querySelectorAll(".faq-item");
    check(label, "FAQ 항목이 렌더링됨", items.length > 0, `count=${items.length}`);
    if (items.length) {
      // <details>는 기본 접힘이어야 본문 흐름을 밀어내지 않는다.
      check(label, "FAQ가 접힌 채로 시작", !items[0].hasAttribute("open"));
      items[0].open = true;
      check(label, "FAQ를 펼칠 수 있음", items[0].hasAttribute("open"));
    }
  } else if (opts.expectNoFaq) {
    // 아카이브 페이지에 반복되면 중복 콘텐츠이고 FAQPage 마크업도 여러 URL에 퍼진다.
    check(label, "FAQ가 없어야 하는 페이지에 없음", doc.querySelectorAll(".faq-item").length === 0);
  }

  const feedLink = doc.querySelector('link[type="application/rss+xml"]');
  check(label, "RSS 피드 link 태그 존재", !!feedLink, feedLink ? feedLink.getAttribute("href") : "없음");
}

(async () => {
  await exercise("index.html", "index", { expectTermLinks: true, expectTopicChips: true, expectFaq: true });
  await exercise("en/index.html", "en/index", { expectTopicChips: true, expectFaq: true });
  await exercise("glossary.html", "glossary");
  await exercise("archive/2026-07-25.html", "archive", { expectNoFaq: true });
  if (fs.existsSync(path.join(DOCS, "weekly"))) {
    const wk = fs.readdirSync(path.join(DOCS, "weekly"))[0];
    if (wk) await exercise(path.join("weekly", wk), "weekly");
  }
  // 주제별 아카이브 — 같은 크롬(언어·테마·공유)을 별도 템플릿으로 복제한 페이지라
  // 다른 페이지에서 잡히는 회귀가 여기서만 빠질 수 있다.
  let firstTopicSlug = null;
  if (fs.existsSync(path.join(DOCS, "topics", "index.html"))) {
    await exercise(path.join("topics", "index.html"), "topics/index");
    const first = fs.readdirSync(path.join(DOCS, "topics")).find((f) => f !== "index.html");
    if (first) {
      firstTopicSlug = first.replace(/\.html$/, "");
      await exercise(path.join("topics", first), "topics/" + first);
    }
  }

  // cleanUrls 실제 배포 URL 기준 링크 무결성 — /topics(세그먼트 1개, 슬래시 없음)에서
  // 터졌던 사고를 다시 잡아낸다. 같은 위험을 안고 있는 다른 depth-0 페이지(/glossary)와
  // depth-2 페이지(/archive/<날짜>)도 함께 실제 clean URL로 검사한다.
  checkCleanUrlLinks("glossary.html", "https://www.dailyaithread.com/glossary", "glossary (clean URL)");
  checkCleanUrlLinks("archive/2026-07-25.html", "https://www.dailyaithread.com/archive/2026-07-25", "archive (clean URL)");
  if (fs.existsSync(path.join(DOCS, "topics", "index.html"))) {
    checkCleanUrlLinks("topics/index.html", "https://www.dailyaithread.com/topics", "topics/index (clean URL)");
  }
  if (firstTopicSlug) {
    checkCleanUrlLinks(
      path.join("topics", firstTopicSlug + ".html"),
      `https://www.dailyaithread.com/topics/${firstTopicSlug}`,
      `topics/${firstTopicSlug} (clean URL)`
    );
  }

  let pass = 0;
  let lastPage = null;
  for (const r of results) {
    if (r.page !== lastPage) {
      console.log(`\n--- ${r.page} ---`);
      lastPage = r.page;
    }
    console.log((r.ok ? "  PASS " : "  FAIL ") + r.name + (r.ok ? "" : "   << " + r.extra));
    if (r.ok) pass++;
  }
  console.log(`\n${pass}/${results.length} passed`);
  process.exit(pass === results.length ? 0 : 1);
})();
