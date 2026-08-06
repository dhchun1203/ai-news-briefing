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
// finishPage 안에서 만든 비동기 검사들. main()이 끝나기 전에 모두 기다린다.
const scrollTopChecks = [];
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


// 영어판 페이지의 내부 링크가 /en/ 밖으로 나가면 안 된다. 자산(CSS·JS·favicon)은
// 사이트 루트에만 있으므로 예외다. 실제로 이 누수가 있었다 — 영어로 보다가
// "Topics"를 누르면 한국어 토픽 페이지가 나왔다(사이트 루트 접두사와 언어 루트
// 접두사를 같은 값으로 쓴 탓).
function checkNoLanguageLeak(relPath, canonicalUrl, label) {
  const { doc } = load(relPath, canonicalUrl);
  const refs = [];
  doc.querySelectorAll("a[href]").forEach((a) => refs.push([a.getAttribute("href"), a.href]));
  doc.querySelectorAll("link[href]").forEach((l) => refs.push([l.getAttribute("href"), l.href]));
  doc.querySelectorAll("script[src]").forEach((s) => refs.push([s.getAttribute("src"), s.src]));
  const leaks = [];
  refs.forEach(([raw, resolved]) => {
    if (!raw || raw.startsWith("#") || raw.startsWith("http") || raw.startsWith("mailto:")) return;
    if (raw.startsWith("/_vercel/")) return;
    const p = resolved.replace(/^https?:\/\/[^/]+/, "");
    if (/\.(css|js|svg|png|json)$/.test(p)) return;   // 사이트 루트 공유 자산
    if (!p.startsWith("/en/")) leaks.push(`${raw} -> ${p}`);
  });
  check(label, "영어판 링크가 /en/ 안에 머무름", leaks.length === 0, leaks.join(" | "));
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
        finishPage(label, doc, window, opts, relPath);
        resolve();
      }, 20);
    });
  }
  finishPage(label, doc, window, opts, relPath);
  return Promise.resolve();
}

function finishPage(label, doc, window, opts, relPath) {
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

  // --- 언어 전환 링크 (드롭다운을 대체) ---
  // 언어가 URL로 분리되면서 CSS 토글이 사라졌다. 상대 언어판으로 가는 링크와
  // hreflang이 없으면 다른 언어판이 발견되지 않는다.
  const langSwitch = doc.querySelector(".lang-switch");
  check(label, "언어 전환 링크 존재", !!langSwitch, langSwitch ? langSwitch.getAttribute("href") : "없음");
  if (langSwitch) {
    const href = langSwitch.getAttribute("href") || "";
    check(label, "언어 전환 링크가 절대 URL", /^https?:\/\//.test(href), href);
    const pageLang = doc.documentElement.getAttribute("lang");
    check(label, "전환 링크가 반대 언어를 가리킴",
      langSwitch.getAttribute("hreflang") !== pageLang,
      `page=${pageLang} link=${langSwitch.getAttribute("hreflang")}`);
  }
  // --- 기사 카드: 요약 앞부분 + 접힌 시사점 ---
  // GeekNews 피드백("스크롤이 길다") 대응. 여기서 지켜야 할 것이 둘이다.
  //   1) 접힌 내용이 **HTML 소스에 그대로** 있어야 한다. JS로 나중에 채우면
  //      크롤러가 시사점을 못 본다 — 이 사이트의 핵심 가치가 통째로 색인에서 빠진다.
  //   2) 시사점 토글이 눈에 띄어야 한다. 라벨이 비면 아무도 펼치지 않는다.
  const cards = doc.querySelectorAll(".article-card");
  if (cards.length) {
    // 서버가 내려준 원본 HTML에서 태그를 벗기고 엔티티를 되돌려 평문으로 만든다.
    // 용어사전 링크(<button>)가 문장 중간에 끼기 때문에, 태그를 안 벗기면 본문이
    // 들어 있어도 문자열 비교가 어긋난다.
    const srcText = fs
      .readFileSync(path.join(DOCS, relPath), "utf-8")
      .replace(/<[^>]+>/g, "")
      .replace(/&(#x27|#39|apos);/g, "'")
      .replace(/&quot;/g, '"')
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&amp;/g, "&")
      .replace(/\s+/g, "");
    let bad = [];
    cards.forEach((card, i) => {
      const details = card.querySelector("details.article-more");
      if (!details) { bad.push(`카드 ${i + 1}: details 없음`); return; }
      if (details.hasAttribute("open")) bad.push(`카드 ${i + 1}: 기본이 펼침`);
      const toggleLabel = card.querySelector(".article-more-label");
      if (!toggleLabel || !toggleLabel.textContent.trim()) bad.push(`카드 ${i + 1}: 토글 라벨 비어 있음`);
      const impl = card.querySelector(".article-implication p");
      if (!impl || !impl.textContent.trim()) bad.push(`카드 ${i + 1}: 시사점 본문 없음`);
      // 접힌 본문이 소스에 실제로 있는지 — 색인의 전제조건이다.
      if (impl) {
        const probe = impl.textContent.trim().replace(/\s+/g, "").slice(0, 30);
        if (probe && !srcText.includes(probe)) {
          bad.push(`카드 ${i + 1}: 시사점이 HTML 소스에 없음(JS 주입?)`);
        }
      }
    });
    check(label, "모든 기사에 접힌 시사점이 있고 기본은 접힘", bad.length === 0, bad.slice(0, 3).join(" | "));

    // 요약 앞부분은 항상 보인다 — 접힌 것은 나머지와 시사점뿐이다.
    check(label, "요약 앞부분은 details 바깥에 있음",
      Array.prototype.every.call(cards, (c) => {
        const lede = c.querySelector(".article-summary p");
        return lede && lede.textContent.trim() && !lede.closest("details");
      }));

    // 기사별 읽는 시간
    const times = Array.prototype.map.call(cards, (c) => {
      const el = c.querySelector(".article-reading-time");
      return el ? el.textContent.trim() : "";
    });
    check(label, "모든 기사에 읽는 시간 표시", times.every((s) => s.length > 0), JSON.stringify(times.slice(0, 3)));
    // 값이 전부 같으면 표시할 이유가 없다(분 단위로 반올림했을 때가 정확히 그랬다).
    check(label, "읽는 시간이 기사마다 구분됨", new Set(times).size > 1, JSON.stringify(times));
  }

  // --- 맨 위로 버튼 ---
  // 스크롤 위치에 따라 나타나야 한다. 항상 떠 있으면 첫 화면부터 본문을 가리고,
  // 안 나타나면 긴 아카이브 페이지에서 상단으로 돌아갈 방법이 없다.
  const topBtn = doc.getElementById("scroll-top");
  check(label, "맨 위로 버튼 존재", !!topBtn);
  if (topBtn) {
    check(label, "맨 위로 버튼에 접근성 라벨",
      (topBtn.getAttribute("aria-label") || "").length > 0, topBtn.getAttribute("aria-label"));
    check(label, "맨 위로 버튼이 문서 최상단에서는 숨김",
      !topBtn.classList.contains("visible"));

    // jsdom은 실제로 스크롤하지 않는다. 핸들러가 읽는 값을 직접 세우고 이벤트를 흘린다.
    const setScroll = (y) => {
      Object.defineProperty(window, "pageYOffset", { value: y, configurable: true });
      window.dispatchEvent(new window.Event("scroll"));
    };
    // rAF로 묶여 있으므로 한 프레임 흘려보내야 클래스가 반영된다.
    const frame = () => new Promise((r) => window.requestAnimationFrame(() => r()));

    scrollTopChecks.push(
      (async () => {
        setScroll(1200);
        await frame();
        check(label, "충분히 내려가면 맨 위로 버튼이 나타남",
          topBtn.classList.contains("visible"), topBtn.className);
        setScroll(100);
        await frame();
        check(label, "다시 위로 오면 맨 위로 버튼이 사라짐",
          !topBtn.classList.contains("visible"), topBtn.className);

        // 클릭하면 화면만 올라가고 포커스가 아래에 남으면 안 된다 —
        // 키보드 사용자는 다음 탭에서 다시 아래로 끌려간다.
        setScroll(1200);
        await frame();
        topBtn.click();
        const heading = doc.querySelector(".site-header h1");
        check(label, "맨 위로 클릭 시 포커스도 상단으로",
          !heading || doc.activeElement === heading,
          doc.activeElement ? doc.activeElement.tagName : "?");
      })()
    );
  }

  // --- 다른 언어판 안내 배너 ---
  // 영어권 방문자가 한국어 페이지에 떨어졌을 때 EN 스위치를 직접 찾아야 했다.
  // 배너는 **기본이 숨김**이어야 한다 — JS가 브라우저 언어를 보고서야 푼다.
  // 처음부터 보이면 한국어 사용자에게 매번 영어 안내가 뜬다.
  const suggest = doc.getElementById("lang-suggest");
  check(label, "언어 안내 배너 존재", !!suggest);
  if (suggest) {
    // 실행된 DOM이 아니라 **원본 HTML**을 본다 — jsdom의 navigator.language가 en-US라
    // 한국어 페이지에서는 스크립트가 이미 hidden을 풀어버린 상태다.
    check(label, "언어 안내 배너가 원본에서 기본 숨김",
      /<div class="lang-suggest" id="lang-suggest" hidden>/.test(
        fs.readFileSync(path.join(DOCS, relPath), "utf-8")),
      "원본에 hidden 없음");
    const sLink = doc.getElementById("lang-suggest-link");
    check(label, "언어 안내 링크 존재", !!sLink);
    if (sLink) {
      const pageLang = doc.documentElement.getAttribute("lang");
      const href = sLink.getAttribute("href") || "";
      check(label, "언어 안내 링크가 절대 URL", /^https?:\/\//.test(href), href);
      check(label, "언어 안내 링크가 반대 언어를 가리킴",
        sLink.getAttribute("hreflang") !== pageLang,
        `page=${pageLang} link=${sLink.getAttribute("hreflang")}`);
      // 영어 페이지의 안내는 한국어판으로, 한국어 페이지의 안내는 /en/ 으로 가야 한다.
      const goesToEn = href.replace(/^https?:\/\/[^/]+/, "").startsWith("/en");
      check(label, "언어 안내 링크 방향이 페이지 언어와 반대",
        pageLang === "ko" ? goesToEn : !goesToEn, `page=${pageLang} href=${href}`);
    }
    check(label, "언어 안내 닫기 버튼 존재", !!doc.getElementById("lang-suggest-close"));
    // jsdom의 navigator.language는 en-US다. 즉 "영어 브라우저"로 본 것과 같으므로
    // 한국어 페이지에서는 배너가 떠야 하고 영어 페이지에서는 떠 있으면 안 된다.
    // 이 한 줄이 브라우저 언어 판정이 실제로 도는지를 확인한다.
    const shown = !suggest.hasAttribute("hidden");
    check(label, "영어 브라우저(jsdom)에서 배너 노출이 페이지 언어에 맞음",
      doc.documentElement.getAttribute("lang") === "ko" ? shown : !shown,
      `lang=${doc.documentElement.getAttribute("lang")} shown=${shown}`);
  }

  // 한 페이지에 한 언어만 담겨야 한다 — 남은 lang-ko/lang-en 클래스는 분리 누락 신호다.
  check(label, "페이지에 한 언어만 담김",
    doc.querySelectorAll(".lang-ko, .lang-en").length === 0,
    `잔여 ${doc.querySelectorAll(".lang-ko, .lang-en").length}개`);
  const alt = doc.querySelector('link[rel="alternate"][hreflang]');
  check(label, "hreflang 대체 링크 존재", !!alt);

  const feedLink = doc.querySelector('link[type="application/rss+xml"]');
  check(label, "RSS 피드 link 태그 존재", !!feedLink, feedLink ? feedLink.getAttribute("href") : "없음");

  // --- 모바일 내비 서랍 (site.js가 런타임에 만든다) ---
  const toggle = doc.getElementById("nav-toggle");
  const drawer = doc.getElementById("nav-drawer");
  check(label, "햄버거 버튼이 생성됨", !!toggle);
  check(label, "내비 서랍이 생성됨", !!drawer);
  if (toggle && drawer) {
    check(label, "서랍은 닫힌 채 시작하고 inert", !drawer.classList.contains("open") && drawer.hasAttribute("inert"));
    check(label, "aria-controls가 서랍을 가리킴", toggle.getAttribute("aria-controls") === "nav-drawer");
    // 유틸리티 바의 링크가 복제돼 들어갔는지 — 서랍이 비어 있으면 모바일에서 메뉴가 사라진다.
    const drawerLinks = drawer.querySelectorAll("a[href]");
    check(label, "서랍에 링크가 복제됨", drawerLinks.length >= 2, `count=${drawerLinks.length}`);
    let dupId = false;
    drawerLinks.forEach((a) => { if (a.id) dupId = true; });
    check(label, "복제본에 id가 남아 중복되지 않음", !dupId);

    toggle.click();
    check(label, "햄버거 클릭 시 열림", drawer.classList.contains("open") && !drawer.hasAttribute("inert"));
    check(label, "열림 상태가 aria-expanded에 반영", toggle.getAttribute("aria-expanded") === "true");

    const esc = new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true });
    doc.dispatchEvent(esc);
    check(label, "Escape로 닫힘", !drawer.classList.contains("open"));
    check(label, "닫으면 다시 inert + aria-expanded=false",
      drawer.hasAttribute("inert") && toggle.getAttribute("aria-expanded") === "false");
  }
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
  if (fs.existsSync(path.join(DOCS, "en", "glossary.html"))) {
    checkCleanUrlLinks("en/glossary.html", "https://www.dailyaithread.com/en/glossary", "en/glossary (clean URL)");
  }
  // --- 구독폼 영문 문구가 도착 시각을 사실대로 말하는지 ---
  // 08:00 KST는 미국 동부 기준 전날 19시다(방문자 국가 1위가 미국). 시각을 밝히지
  // 않고 "every morning"만 쓰면 아침에 올 거라 기대하고 구독한 사람이 전날 저녁에
  // 받는다. 한국어는 실제로 아침이므로 그대로 둔다.
  [["index.html", "https://www.dailyaithread.com/", "ko"],
   ["en/index.html", "https://www.dailyaithread.com/en/", "en"]].forEach(([f, url, lang]) => {
    if (!fs.existsSync(path.join(DOCS, f))) return;
    const { doc } = load(f, url);
    const title = (doc.querySelector(".subscribe-title") || {}).textContent || "";
    const desc = (doc.querySelector(".subscribe-desc") || {}).textContent || "";
    if (lang === "en") {
      check("en/index", "구독폼이 시각 없이 아침을 주장하지 않음",
        !/every morning/i.test(title + desc), (title + desc).trim().slice(0, 60));
      check("en/index", "구독폼이 발송 시각을 밝힘", /KST/.test(desc), desc.trim().slice(0, 80));
    } else {
      check("index", "한국어 구독폼은 아침 문구를 유지", /아침/.test(title), title.trim());
    }
  });

  // --- 구독 이메일 검증 (오타 도메인 제안 + 형식 검사) ---
  // ...@gmail.om 으로 구독을 시도한 사람이 확인 메일을 영영 못 받고 유실된 적이 있다.
  // 오타는 눈에 잘 안 띄고, 메일이 안 오는 이유도 알 길이 없다.
  [["index.html", "https://www.dailyaithread.com/", "ko"],
   ["en/index.html", "https://www.dailyaithread.com/en/", "en"]].forEach(([f, url, lang]) => {
    if (!fs.existsSync(path.join(DOCS, f))) return;
    const { window, doc } = load(f, url);
    const input = doc.querySelector('#subscribe-form input[name="email"]');
    const hintEl = doc.getElementById("subscribe-hint");
    const statusEl = doc.getElementById("subscribe-status");
    if (!input || !hintEl) {
      check(f, "구독 폼과 제안 요소가 있음", false);
      return;
    }
    const hintAfter = (value) => {
      input.value = value;
      input.dispatchEvent(new window.Event("input", { bubbles: true }));
      input.dispatchEvent(new window.Event("blur", { bubbles: true }));
      return hintEl.hidden ? "" : (hintEl.textContent || "").trim();
    };

    // 오타는 제안이 뜬다 — 단 **막지는 않는다**(.om은 오만의 실존 TLD다).
    const typo = hintAfter("kim@gmail.om");
    check(`${f} (${lang})`, "gmail.om에 제안이 뜸", typo.includes("kim@gmail.com"), typo);
    const typo2 = hintAfter("kim@gmial.com");
    check(`${f} (${lang})`, "gmial.com에 제안이 뜸", typo2.includes("kim@gmail.com"), typo2);

    // 정상 주소는 방해받지 않는다 — 흔한 도메인도, 회사 도메인도.
    check(`${f} (${lang})`, "gmail.com은 조용함", hintAfter("kim@gmail.com") === "");
    check(`${f} (${lang})`, "회사 도메인은 조용함", hintAfter("kim@mycompany.co.kr") === "");

    // 형식이 아닌 값은 전송을 막는다.
    input.value = "plain-text";
    doc.getElementById("subscribe-form").dispatchEvent(
      new window.Event("submit", { bubbles: true, cancelable: true }));
    const msg = (statusEl.textContent || "").trim();
    check(`${f} (${lang})`, "형식 오류는 전송을 막고 안내함", msg.length > 0, msg);
    check(`${f} (${lang})`, "안내 문구가 해당 언어임",
      lang === "ko" ? /형식/.test(msg) : /format/i.test(msg), msg);
  });

  // 영어판에 한국어가 남지 않는지 — 기사 카드만 고치고 목차를 빠뜨린 적이 있다
  // (2026-08-03). 한 군데만 놓쳐도 그 목록 전체가 읽을 수 없는 글자로 남는다.
  if (fs.existsSync(path.join(DOCS, "en", "index.html"))) {
    const { doc } = load("en/index.html", "https://www.dailyaithread.com/en/");
    const hangul = /[가-힣]/;
    const spots = [
      [".toc-text", "목차"],
      [".article-title a, .article h2 a", "기사 제목"],
    ];
    spots.forEach(([sel, label]) => {
      const nodes = [].slice.call(doc.querySelectorAll(sel));
      if (!nodes.length) return;
      const bad = nodes.filter((n) => hangul.test(n.textContent || ""));
      check("en/index", `${label}에 한글 없음`, bad.length === 0,
        bad.map((n) => (n.textContent || "").trim().slice(0, 30)).join(" | "));
    });
  }

  // 용어 페이지의 전환 경로. 검색 유입의 주력 착지점인데 구독 유도가 하나도 없어
  // 읽고 나가면 끝나는 막다른 길이었다(2026-08-02 점검). 조용히 사라지면 안 된다.
  ["glossary/mcp.html", "en/glossary/mcp.html"].forEach((f) => {
    if (!fs.existsSync(path.join(DOCS, f))) return;
    const url = "https://www.dailyaithread.com/" + f.replace(/\.html$/, "");
    const { doc } = load(f, url);
    check(f, "구독 폼이 있음", !!doc.querySelector("#subscribe-form .subscribe-submit"));
    const dates = doc.querySelectorAll(".term-page-dates a");
    check(f, "등장 브리핑이 링크로 있음", dates.length >= 1,
      `링크 ${dates.length}개`);
    const bad = [].filter.call(dates, (a) => !/\/archive\/\d{4}-\d{2}-\d{2}$/.test(
      a.href.replace(/^https?:\/\/[^/]+/, "").replace(/\.html$/, "")));
    check(f, "등장 브리핑 링크가 아카이브를 가리킴", bad.length === 0,
      bad.map((a) => a.getAttribute("href")).join(" | "));
  });

  // 언어 누수 검사 — 영어판 주요 페이지 전체
  [["en/index.html", "/en/"], ["en/glossary.html", "/en/glossary"], ["en/about.html", "/en/about"],
   ["en/topics/index.html", "/en/topics"], ["en/archive/index.html", "/en/archive"]].forEach(([f, u]) => {
    if (fs.existsSync(path.join(DOCS, f))) {
      checkNoLanguageLeak(f, "https://www.dailyaithread.com" + u, `${u} (언어 누수)`);
    }
  });
  if (fs.existsSync(path.join(DOCS, "en", "topics", "index.html"))) {
    checkCleanUrlLinks("en/topics/index.html", "https://www.dailyaithread.com/en/topics", "en/topics (clean URL)");
  }
  if (fs.existsSync(path.join(DOCS, "about.html"))) {
    checkCleanUrlLinks("about.html", "https://www.dailyaithread.com/about", "about (clean URL)");
  }
  if (fs.existsSync(path.join(DOCS, "glossary", "mcp.html"))) {
    checkCleanUrlLinks("glossary/mcp.html", "https://www.dailyaithread.com/glossary/mcp", "glossary/mcp (clean URL)");
  }
  checkCleanUrlLinks("archive/2026-07-25.html", "https://www.dailyaithread.com/archive/2026-07-25", "archive (clean URL)");
  // 아카이브 목록은 /topics와 같은 깊이(세그먼트 1개)라 같은 함정이 있는 자리다.
  if (fs.existsSync(path.join(DOCS, "archive", "index.html"))) {
    checkCleanUrlLinks("archive/index.html", "https://www.dailyaithread.com/archive", "archive/index (clean URL)");
  }
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

  // 맨 위로 버튼 검사는 rAF를 기다리므로 비동기다. 결과를 세기 전에 모두 끝내야 한다 —
  // 안 기다리면 검사가 통째로 빠진 채 "전부 통과"로 보인다.
  await Promise.all(scrollTopChecks);

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
