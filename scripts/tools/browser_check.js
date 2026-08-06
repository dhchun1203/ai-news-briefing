// 실제 브라우저(설치된 Chrome)로 UI 동작을 확인하는 개발용 스크립트.
//
// 왜 필요한가: `chrome --headless --dump-dom`으로는 확인할 수 없는 것들이 있다.
//   - 스크롤 이벤트가 아예 발생하지 않는다(맨 위로 버튼이 안 뜨는 것처럼 보인다)
//   - requestAnimationFrame이 돌지 않아 rAF로 묶은 코드가 실행되지 않는다
//   - `--window-size`가 485px 아래로 안 내려가 진짜 모바일 폭을 볼 수 없다
//   - `scroll-behavior: smooth` 애니메이션이 끝나지 않는다
// jsdom 회귀 테스트가 로직은 지켜주지만, "사람이 보는 화면에서 실제로 그렇게 되는가"는
// 별개다. 이 스크립트가 그 마지막 확인을 맡는다.
//
// **tests/run_all.sh에는 넣지 않는다.** 매일 08:00 무인 파이프라인이 도는 환경에
// 브라우저 의존성을 추가하면, UI 확인 도구 하나 때문에 발송이 막힐 수 있다.
// 이건 사람이 UI를 건드렸을 때 손으로 돌리는 도구다.
//
// 준비:  npm install --no-save jsdom playwright-core
//        (jsdom을 함께 적는 이유: package.json이 없는 디렉터리에서 --no-save로 설치하면
//         npm이 나머지 패키지를 정리해버려 jsdom이 사라진다. 실제로 한 번 당했다.)
// 사용:  py -m http.server 8970 --directory docs &
//        node scripts/tools/browser_check.js http://127.0.0.1:8970

const { chromium } = require("playwright-core");
const path = require("path");
const fs = require("fs");

const BASE = process.argv[2] || "http://127.0.0.1:8970";
const SHOTS = process.argv[3] || path.join(process.cwd(), "browser-shots");

const results = [];
function check(name, cond, extra = "") {
  results.push({ name, ok: !!cond, extra });
  console.log((cond ? "  PASS " : "  FAIL ") + name + (cond ? "" : "   << " + extra));
}

async function main() {
  fs.mkdirSync(SHOTS, { recursive: true });
  // 설치된 Chrome을 그대로 쓴다 — playwright-core는 브라우저를 따로 내려받지 않는다.
  const browser = await chromium.launch({ channel: "chrome" });

  // ---------- 1. 맨 위로 버튼 (데스크톱, 실제 스크롤) ----------
  console.log("\n--- 맨 위로 버튼 / 데스크톱 1280x800 ---");
  {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, locale: "ko-KR" });
    const page = await ctx.newPage();
    await page.goto(`${BASE}/archive/2026-07-25.html`, { waitUntil: "load" });
    const btn = page.locator("#scroll-top");

    check("최상단에서는 버튼이 안 보임", !(await btn.isVisible()));

    // 실제 스크롤. 헤드리스 dump-dom과 달리 여기서는 scroll 이벤트와 rAF가 모두 돈다.
    await page.mouse.wheel(0, 1400);
    await page.waitForTimeout(300);
    check("스크롤하면 버튼이 나타남", await btn.isVisible());
    await page.screenshot({ path: path.join(SHOTS, "scrolltop-visible.png") });

    const box = await btn.boundingBox();
    const vp = page.viewportSize();
    check("버튼이 우측 하단에 있음",
      box && box.x + box.width > vp.width - 80 && box.y + box.height > vp.height - 80,
      JSON.stringify(box));
    check("버튼 터치 타깃 44px 이상", box && box.width >= 44 && box.height >= 44, JSON.stringify(box));

    await page.evaluate(() => window.scrollTo({ top: 100, behavior: "auto" }));
    await page.waitForTimeout(300);
    check("다시 위로 오면 버튼이 사라짐", !(await btn.isVisible()));

    // 부드러운 스크롤이 끝날 때까지 기다린다 — 실제 브라우저라 애니메이션이 완주한다.
    await page.mouse.wheel(0, 2000);
    await page.waitForTimeout(300);
    await btn.click();
    await page.waitForFunction(() => window.pageYOffset === 0, null, { timeout: 5000 }).catch(() => {});
    check("클릭하면 맨 위로 이동", (await page.evaluate(() => window.pageYOffset)) === 0,
      String(await page.evaluate(() => window.pageYOffset)));
    check("클릭 후 포커스도 상단 제목으로",
      await page.evaluate(() => document.activeElement === document.querySelector(".site-header h1")),
      await page.evaluate(() => document.activeElement && document.activeElement.tagName));
    await ctx.close();
  }

  // ---------- 1-2. 기사 카드: 접힌 시사점 + 읽는 시간 ----------
  console.log("\n--- 기사 카드 (접기/펼치기) ---");
  for (const [label, url] of [["한국어", "/index.html"], ["영어", "/en/index.html"]]) {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, locale: "ko-KR" });
    const page = await ctx.newPage();
    await page.goto(BASE + url, { waitUntil: "load" });

    const card = page.locator(".article-card").first();
    const details = card.locator("details.article-more");
    const impl = card.locator(".article-implication p");
    const toggle = card.locator(".article-more-toggle");

    check(`${label}: 처음엔 시사점이 접혀 있음`, !(await impl.isVisible()));
    check(`${label}: 토글 라벨이 보임`, await toggle.isVisible());
    const labelText = (await card.locator(".article-more-label").textContent()).trim();
    check(`${label}: 토글 라벨에 문구가 있음`, labelText.length > 0, labelText);

    // 토글이 눈에 띄어야 한다 — 배경/테두리가 있는 알약이라 본문과 구분된다.
    const tbox = await toggle.boundingBox();
    check(`${label}: 토글 터치 타깃 44px 이상`, tbox && tbox.height >= 44, JSON.stringify(tbox));

    await toggle.click();
    await page.waitForTimeout(200);
    check(`${label}: 누르면 시사점이 펼쳐짐`, await impl.isVisible());
    check(`${label}: 펼친 시사점에 본문이 있음`,
      (await impl.textContent()).trim().length > 20);
    await page.screenshot({ path: path.join(SHOTS, `card-open-${label === "한국어" ? "ko" : "en"}.png`) });

    await toggle.click();
    await page.waitForTimeout(200);
    check(`${label}: 다시 누르면 접힘`, !(await impl.isVisible()));

    // 키보드만으로도 열려야 한다(<summary>는 기본 포커서블).
    await toggle.focus();
    await page.keyboard.press("Enter");
    await page.waitForTimeout(200);
    check(`${label}: 키보드(Enter)로도 펼쳐짐`, await impl.isVisible());

    // 접힌 상태에서 첫 화면에 보이는 기사 수 — 이번 변경의 목적이다.
    await page.reload({ waitUntil: "load" });
    const visibleCards = await page.evaluate(() => {
      const h = window.innerHeight;
      return Array.from(document.querySelectorAll(".article-card"))
        .filter((c) => c.getBoundingClientRect().top < h * 3).length;
    });
    console.log(`     (참고) 3화면 안에 들어오는 기사 수: ${visibleCards}`);

    // 읽는 시간
    const times = await page.locator(".article-reading-time").allTextContents();
    check(`${label}: 모든 기사에 읽는 시간`, times.length >= 10 && times.every((s) => s.trim()),
      JSON.stringify(times.slice(0, 3)));
    check(`${label}: 읽는 시간이 기사마다 다름`, new Set(times.map((s) => s.trim())).size > 1,
      JSON.stringify(times));
    await ctx.close();
  }

  // ---------- 1-3. 읽는 위치: 데스크톱 좌측 레일 ----------
  // 스크롤에 따라 하이라이트가 따라오는지는 jsdom으로 검증되지 않는 영역이다.
  console.log("\n--- 좌측 레일 / 데스크톱 1440x900 ---");
  for (const [label, url] of [["한국어", "/index.html"], ["영어", "/en/index.html"]]) {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "ko-KR" });
    const page = await ctx.newPage();
    await page.goto(BASE + url, { waitUntil: "load" });
    const rail = page.locator("#toc-rail");
    check(`${label}: 넓은 화면에서 레일 표시`, await rail.isVisible());

    // 레일이 본문을 가리지 않아야 한다.
    const rbox = await rail.boundingBox();
    const cbox = await page.locator(".article-list").boundingBox();
    check(`${label}: 레일이 본문과 겹치지 않음`,
      rbox && cbox && rbox.x + rbox.width <= cbox.x + 1, JSON.stringify({ rbox, cx: cbox && cbox.x }));

    // 3번째 기사로 스크롤하면 3번이 활성화돼야 한다.
    await page.locator(".article-card").nth(2).scrollIntoViewIfNeeded();
    await page.mouse.wheel(0, 120);
    await page.waitForTimeout(400);
    let active = await page.locator("#toc-rail li.active .rail-num").allTextContents();
    check(`${label}: 스크롤하면 현재 기사가 레일에 표시됨`, active.length === 1, JSON.stringify(active));
    const firstActive = active[0];

    // 더 내려가면 활성 항목이 바뀐다.
    await page.locator(".article-card").nth(6).scrollIntoViewIfNeeded();
    await page.mouse.wheel(0, 120);
    await page.waitForTimeout(400);
    active = await page.locator("#toc-rail li.active .rail-num").allTextContents();
    check(`${label}: 더 내려가면 활성 항목이 바뀜`,
      active.length === 1 && active[0] !== firstActive, `${firstActive} -> ${JSON.stringify(active)}`);
    await page.screenshot({ path: path.join(SHOTS, `rail-${label === "한국어" ? "ko" : "en"}.png`) });

    // 레일을 클릭하면 그 기사로 이동한다.
    await page.locator("#toc-rail li a").nth(1).click();
    // 부드러운 스크롤이 끝나야 위치가 확정된다. 고정 대기로는 페이지 길이에 따라
    // 어긋나므로(멀리서 클릭하면 더 오래 걸린다) 대상 기사의 위치가 두 프레임 연속
    // 같아질 때까지 기다린다.
    // rAF 간격(16ms)으로 두 번 비교하면 부드러운 스크롤이 시작되기도 전에 "멈췄다"고
    // 판정한다(실제로 그렇게 오판했다). 100ms 간격으로 세 번 연속 같아야 안착으로 본다.
    let stable = 0;
    let lastTop = null;
    for (let i = 0; i < 40 && stable < 3; i++) {
      await page.waitForTimeout(100);
      const top = Math.round(
        await page.locator(".article-card").nth(1).evaluate((el) => el.getBoundingClientRect().top));
      stable = top === lastTop ? stable + 1 : 0;
      lastTop = top;
    }
    const secondTop = await page.locator(".article-card").nth(1).evaluate(
      (el) => el.getBoundingClientRect().top);
    check(`${label}: 레일 클릭 시 해당 기사로 이동`, secondTop >= -5 && secondTop < 200, String(Math.round(secondTop)));

    // 접힌 기사를 펼쳐도 추적이 맞아야 한다(높이가 바뀐다).
    await page.locator(".article-card").nth(1).locator(".article-more-toggle").click();
    await page.waitForTimeout(300);
    await page.locator(".article-card").nth(4).scrollIntoViewIfNeeded();
    await page.mouse.wheel(0, 120);
    await page.waitForTimeout(400);
    active = await page.locator("#toc-rail li.active .rail-num").allTextContents();
    check(`${label}: 기사를 펼친 뒤에도 추적이 이어짐`, active.length === 1, JSON.stringify(active));
    await ctx.close();
  }

  // 좁은 화면에서는 레일이 아예 안 보여야 한다.
  {
    const ctx = await browser.newContext({ viewport: { width: 1100, height: 800 }, locale: "ko-KR" });
    const page = await ctx.newPage();
    await page.goto(`${BASE}/index.html`, { waitUntil: "load" });
    check("좁은 화면(1100px)에서는 레일 숨김", !(await page.locator("#toc-rail").isVisible()));
    await ctx.close();
  }

  // ---------- 1-4. 읽는 위치: 모바일 진행 바 ----------
  // Playwright는 뷰포트를 직접 지정하므로 390px 실측이 가능하다
  // (chrome --headless --window-size의 485px 하한과 무관하다).
  console.log("\n--- 모바일 진행 바 / 390x844 ---");
  for (const [label, url] of [["한국어", "/index.html"], ["영어", "/en/index.html"]]) {
    const ctx = await browser.newContext({
      viewport: { width: 390, height: 844 }, locale: "ko-KR", isMobile: true, hasTouch: true,
    });
    const page = await ctx.newPage();
    await page.goto(BASE + url, { waitUntil: "load" });
    const prog = page.locator("#reading-progress");

    check(`${label}: 맨 위에서는 진행 바 숨김`, !(await prog.isVisible()));

    await page.locator(".article-card").nth(2).scrollIntoViewIfNeeded();
    await page.mouse.wheel(0, 120);
    await page.waitForTimeout(400);
    check(`${label}: 기사 목록에 들어가면 진행 바 표시`, await prog.isVisible());

    const text = (await prog.textContent()).replace(/\s+/g, " ").trim();
    check(`${label}: "n/10 · 제목" 형식`, /^\d+\/\d+/.test(text), text);
    check(`${label}: 현재 기사 제목이 실려 있음`, text.length > 6, text);

    // 화면 맨 위에 붙고, 한 줄을 넘지 않는다.
    const pbox = await prog.boundingBox();
    check(`${label}: 진행 바가 화면 맨 위에 붙음`, pbox && Math.abs(pbox.y) < 2, JSON.stringify(pbox));
    check(`${label}: 진행 바가 한 줄 높이`, pbox && pbox.height <= 34, JSON.stringify(pbox));
    check(`${label}: 진행 바가 화면 폭을 넘지 않음`, pbox && pbox.width <= 390, JSON.stringify(pbox));
    await page.screenshot({ path: path.join(SHOTS, `progress-${label === "한국어" ? "ko" : "en"}.png`) });

    // 기사 목록을 벗어나면 사라진다(FAQ·푸터 구간).
    await page.evaluate(() => window.scrollTo({ top: document.body.scrollHeight, behavior: "auto" }));
    await page.waitForTimeout(500);
    check(`${label}: 목록을 벗어나면 진행 바 숨김`, !(await prog.isVisible()));

    // 맨 위로 돌아가도 숨는다.
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: "auto" }));
    await page.waitForTimeout(400);
    check(`${label}: 다시 맨 위로 오면 숨김`, !(await prog.isVisible()));
    await ctx.close();
  }

  // 모션 최소화 설정에서는 전환 효과가 없어야 한다.
  {
    const ctx = await browser.newContext({
      viewport: { width: 390, height: 844 }, locale: "ko-KR", reducedMotion: "reduce",
    });
    const page = await ctx.newPage();
    await page.goto(`${BASE}/index.html`, { waitUntil: "load" });
    // 전역 reduced-motion 블록이 transition-duration을 0.01ms !important로 덮으므로
    // 정확히 "0s"가 아니라 "사실상 0"인지로 본다.
    const nearZero = (s) => s.split(",").every((v) => parseFloat(v) < 0.001);
    const t1 = await page.locator("#reading-progress").evaluate(
      (el) => getComputedStyle(el).transitionDuration);
    check("모션 최소화: 진행 바 전환 사실상 없음", nearZero(t1), t1);
    const t2 = await page.locator(".article-more-chevron").first().evaluate(
      (el) => getComputedStyle(el).transitionDuration);
    check("모션 최소화: 셰브론 전환 사실상 없음", nearZero(t2), t2);
    await ctx.close();
  }

  // ---------- 2. 언어 안내 배너 ----------
  console.log("\n--- 언어 안내 배너 ---");
  for (const [locale, url, shouldShow, label] of [
    ["en-US", "/index.html", true, "영어 브라우저 + 한국어 페이지"],
    ["en-US", "/en/index.html", false, "영어 브라우저 + 영어 페이지"],
    ["ko-KR", "/index.html", false, "한국어 브라우저 + 한국어 페이지"],
    ["ko-KR", "/en/index.html", true, "한국어 브라우저 + 영어 페이지"],
  ]) {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, locale });
    const page = await ctx.newPage();
    await page.goto(BASE + url, { waitUntil: "load" });
    await page.waitForTimeout(200);
    const shown = await page.locator("#lang-suggest").isVisible();
    check(`${label} -> 배너 ${shouldShow ? "표시" : "숨김"}`, shown === shouldShow, `실제=${shown}`);
    await ctx.close();
  }

  // 닫으면 다시 안 뜨는지 (같은 컨텍스트 = 같은 localStorage)
  {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, locale: "en-US" });
    const page = await ctx.newPage();
    await page.goto(`${BASE}/index.html`, { waitUntil: "load" });
    await page.waitForTimeout(200);
    await page.screenshot({ path: path.join(SHOTS, "banner-desktop.png"), clip: { x: 0, y: 0, width: 1280, height: 220 } });
    await page.locator("#lang-suggest-close").click();
    check("닫기를 누르면 즉시 사라짐", !(await page.locator("#lang-suggest").isVisible()));
    await page.reload({ waitUntil: "load" });
    await page.waitForTimeout(200);
    check("다시 방문해도 안 뜸", !(await page.locator("#lang-suggest").isVisible()));
    await ctx.close();
  }

  // ---------- 3. 진짜 모바일 뷰포트 ----------
  console.log("\n--- 모바일 390x844 ---");
  {
    const ctx = await browser.newContext({
      viewport: { width: 390, height: 844 },
      locale: "en-US",
      deviceScaleFactor: 2,
      isMobile: true,
      hasTouch: true,
    });
    const page = await ctx.newPage();
    await page.goto(`${BASE}/index.html`, { waitUntil: "load" });
    await page.waitForTimeout(300);

    const overflow = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      inner: window.innerWidth,
    }));
    check("가로 스크롤 없음", overflow.scrollWidth <= overflow.inner, JSON.stringify(overflow));

    check("모바일에서도 배너 표시", await page.locator("#lang-suggest").isVisible());
    const closeBox = await page.locator("#lang-suggest-close").boundingBox();
    check("닫기 버튼이 화면 안에 있음", closeBox && closeBox.x + closeBox.width <= 390, JSON.stringify(closeBox));
    check("닫기 버튼 터치 타깃 44px 이상",
      closeBox && closeBox.width >= 44 && closeBox.height >= 44, JSON.stringify(closeBox));
    await page.screenshot({ path: path.join(SHOTS, "banner-mobile.png"), fullPage: false });

    await page.mouse.wheel(0, 1500);
    await page.waitForTimeout(400);
    check("모바일에서 맨 위로 버튼 표시", await page.locator("#scroll-top").isVisible());
    const stBox = await page.locator("#scroll-top").boundingBox();
    check("맨 위로 버튼이 화면 안(우측 하단)",
      stBox && stBox.x + stBox.width <= 390 && stBox.y + stBox.height <= 844, JSON.stringify(stBox));
    await page.screenshot({ path: path.join(SHOTS, "scrolltop-mobile.png") });
    await ctx.close();
  }

  await browser.close();

  const pass = results.filter((r) => r.ok).length;
  console.log(`\n${pass}/${results.length} passed`);
  console.log(`스크린샷: ${SHOTS}`);
  process.exit(pass === results.length ? 0 : 1);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
