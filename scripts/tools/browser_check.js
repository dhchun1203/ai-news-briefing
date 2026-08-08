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
    // 10으로 못박으면 안 된다 — 원문을 못 읽어 그날 9건만 나가는 날이 있다
    // (실제로 2026-08-08이 그랬고, 이 검사가 그것 때문에 빨갛게 떴다).
    const cardCount = await page.locator(".article-card").count();
    check(`${label}: 모든 기사에 읽는 시간`,
      cardCount > 0 && times.length >= cardCount && times.every((s) => s.trim()),
      `카드 ${cardCount}개 / 표시 ${times.length}개 ${JSON.stringify(times.slice(0, 3))}`);
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
    // 한 줄을 유지하되 읽을 수 있는 크기여야 한다. 12px/6px일 때 실기기에서 너무
    // 작다는 피드백을 받아 14px/10px로 올렸다 — 위아래 경계를 모두 잡아둔다.
    check(`${label}: 진행 바가 한 줄 높이`, pbox && pbox.height >= 40 && pbox.height <= 56,
      JSON.stringify(pbox));
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

  // ---------- 1-5. 모달 열림 중 배경 스크롤 잠금 ----------
  // 반투명 백드롭이 덮인 상태에서 뒤가 계속 스크롤되면, 패널을 닫았을 때 읽던 자리를
  // 잃는다. 스크롤 잠금 자체가 브라우저에서만 재현되는 동작이라 여기서 확인한다.
  console.log("\n--- 배경 스크롤 잠금 ---");
  {
    const ctx = await browser.newContext({
      viewport: { width: 1280, height: 800 }, locale: "ko-KR", reducedMotion: "reduce",
    });
    const page = await ctx.newPage();
    await page.goto(`${BASE}/index.html`, { waitUntil: "load" });
    const y = () => page.evaluate(() => Math.round(window.pageYOffset));
    const colWidth = () => page.evaluate(
      () => Math.round(document.querySelector(".article-list").getBoundingClientRect().width));

    await page.evaluate(() => window.scrollTo(0, 1500));
    await page.waitForTimeout(150);
    const y0 = await y();
    const w0 = await colWidth();

    // 서랍과 같은 이유로 locator.click()을 쓰지 않는다 — 요소를 화면에 스크롤해
    // 넣고 누르기 때문에, 검사하려는 스크롤 위치 자체가 바뀌어버린다. 본문 레이아웃이
    // 조금만 달라져도 첫 용어 링크가 화면 밖으로 나가 그때부터 깨진다(실제로 겪었다).
    await page.evaluate(() => document.querySelector(".term-link").click());
    await page.waitForTimeout(250);
    check("용어 패널이 열림", await page.locator(".term-panel").isVisible());

    await page.mouse.wheel(0, 600);
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("PageDown");
    await page.waitForTimeout(250);
    check("패널 열린 동안 배경이 스크롤되지 않음", (await y()) === y0, `${y0} -> ${await y()}`);
    // 스크롤바가 사라지며 본문이 옆으로 튀면 그것대로 거슬린다.
    check("잠금 중 본문 폭이 그대로", (await colWidth()) === w0, `${w0} -> ${await colWidth()}`);

    await page.keyboard.press("Escape");
    await page.waitForTimeout(250);
    check("닫으면 읽던 위치가 유지됨", (await y()) === y0, `${y0} -> ${await y()}`);
    await page.mouse.wheel(0, 300);
    await page.waitForTimeout(250);
    check("닫은 뒤 스크롤이 다시 동작", (await y()) > y0, String(await y()));

    // 열린 채 다른 용어를 누르면 잠금이 두 번 걸려 영영 안 풀릴 수 있다.
    await page.evaluate(() => window.scrollTo(0, 1500));
    await page.waitForTimeout(150);
    await page.evaluate(() => document.querySelector(".term-link").click());
    await page.waitForTimeout(200);
    await page.evaluate(() => {
      const links = document.querySelectorAll(".term-link");
      if (links[1]) links[1].click();
    });
    await page.waitForTimeout(200);
    await page.keyboard.press("Escape");
    await page.waitForTimeout(250);
    await page.mouse.wheel(0, 300);
    await page.waitForTimeout(250);
    check("용어를 연달아 눌러도 잠금이 남지 않음", (await y()) > 1500, String(await y()));
    await ctx.close();
  }

  // 모바일 서랍도 같은 규칙을 따른다.
  {
    const ctx = await browser.newContext({
      viewport: { width: 390, height: 844 }, locale: "ko-KR", isMobile: true, hasTouch: true,
      reducedMotion: "reduce",
    });
    const page = await ctx.newPage();
    await page.goto(`${BASE}/index.html`, { waitUntil: "load" });
    const y = () => page.evaluate(() => Math.round(window.pageYOffset));
    await page.evaluate(() => window.scrollTo(0, 1200));
    await page.waitForTimeout(150);
    const y0 = await y();
    // locator.click()은 요소를 화면에 스크롤해 넣고 누른다. 햄버거는 <header> 안에
    // 있어 아래로 내려가면 화면 밖이라, 그 자동 스크롤이 위치를 맨 위로 되돌려버린다
    // (실제 사용자는 그 상태에서 햄버거를 누를 수 없다). 검사하려는 건 잠금이지
    // 클릭 경로가 아니므로 스크롤 없이 직접 연다.
    await page.evaluate(() => document.querySelector("#nav-toggle").click());
    await page.waitForTimeout(250);
    check("모바일 서랍이 열림", await page.locator(".nav-drawer").evaluate(
      (el) => el.classList.contains("open")));
    await page.mouse.wheel(0, 600);
    await page.waitForTimeout(250);
    check("서랍 열린 동안 배경이 스크롤되지 않음", (await y()) === y0, `${y0} -> ${await y()}`);
    await page.keyboard.press("Escape");
    await page.waitForTimeout(250);
    check("서랍 닫으면 읽던 위치가 유지됨", (await y()) === y0, `${y0} -> ${await y()}`);
    await page.mouse.wheel(0, 300);
    await page.waitForTimeout(250);
    check("서랍 닫은 뒤 스크롤이 다시 동작", (await y()) > y0, String(await y()));

    // 서랍이 열린 채로 용어 패널까지 열면 잠금이 두 번 걸린다. 하나를 닫을 때
    // 무조건 풀어버리면 아직 열려 있는 다른 하나 뒤에서 배경이 다시 움직인다.
    await page.evaluate(() => window.scrollTo(0, 1200));
    await page.waitForTimeout(200);
    const yNest = await y();
    await page.evaluate(() => document.querySelector("#nav-toggle").click());
    await page.waitForTimeout(200);
    await page.evaluate(() => {
      const el = document.querySelector(".term-link");
      if (el) el.click();
    });
    await page.waitForTimeout(200);
    const bothOpen = await page.evaluate(() =>
      document.querySelector(".nav-drawer").classList.contains("open") &&
      document.querySelector(".term-panel").classList.contains("open"));
    check("서랍과 용어 패널이 함께 열린 상태를 만들 수 있음", bothOpen);
    if (bothOpen) {
      // 용어 패널만 닫는다 — 서랍은 아직 열려 있으므로 잠금이 유지돼야 한다.
      await page.evaluate(() => document.getElementById("term-panel-close").click());
      await page.waitForTimeout(200);
      await page.mouse.wheel(0, 600);
      await page.waitForTimeout(250);
      check("하나만 닫으면 잠금이 유지됨", (await y()) === yNest, `${yNest} -> ${await y()}`);
      await page.keyboard.press("Escape");
      await page.waitForTimeout(250);
      await page.mouse.wheel(0, 300);
      await page.waitForTimeout(250);
      check("둘 다 닫으면 잠금이 풀림", (await y()) > yNest, String(await y()));
    }
    await ctx.close();
  }

  // ---------- 1-6. /data 막대 정합성 ----------
  // 값 칸을 auto로 뒀더니 "49 31.4%"와 "5 3.2%"의 글자 폭 차이로 행마다 트랙이
  // 415/423/431px로 갈렸다. 같은 비율이 행마다 다른 길이로 그려지면 막대 차트의
  // 존재 이유가 없어진다. 픽셀로만 잡히는 문제라 여기서 본다.
  console.log("\n--- /data 막대 ---");
  for (const [label, url] of [["한국어", "/data.html"], ["영어", "/en/data.html"]]) {
    for (const [vp, w, h, mob] of [["데스크톱", 1280, 900, false], ["모바일", 390, 844, true]]) {
      const ctx = await browser.newContext({
        viewport: { width: w, height: h }, locale: "ko-KR", isMobile: mob, hasTouch: mob,
        reducedMotion: "reduce",
      });
      const page = await ctx.newPage();
      await page.goto(BASE + url, { waitUntil: "load" });

      const tracks = await page.locator(".bar-row .bar-track").evaluateAll((els) =>
        els.map((e) => {
          const r = e.getBoundingClientRect();
          return { x: Math.round(r.x), w: Math.round(r.width) };
        }));
      check(`${label}/${vp}: 모든 막대 트랙 폭이 같음`,
        new Set(tracks.map((t) => t.w)).size === 1,
        JSON.stringify([...new Set(tracks.map((t) => t.w))]));
      check(`${label}/${vp}: 모든 막대 시작점이 같음`,
        new Set(tracks.map((t) => t.x)).size === 1,
        JSON.stringify([...new Set(tracks.map((t) => t.x))]));

      // 막대 길이가 값에 비례하는지. **섹션마다 따로 본다** — 매체와 토픽은 서로
      // 다른 기준으로 정규화되므로 섞어서 비교하면 안 된다(처음에 그렇게 짜서 틀렸다).
      // 값은 textContent가 아니라 data-count로 읽는다("49"와 "31.4%"가 붙어 나온다).
      const bad = await page.evaluate(() => {
        const problems = [];
        document.querySelectorAll(".data-section").forEach((sec, si) => {
          const rows = [...sec.querySelectorAll(".bar-row")].map((e) => ({
            value: Number(e.querySelector(".bar-value").dataset.count),
            fill: Math.round(e.querySelector(".bar-fill").getBoundingClientRect().width),
          }));
          if (rows.length < 2) return;
          const sorted = [...rows].sort((a, b) => b.value - a.value);
          sorted.forEach((r, i) => {
            if (i && r.fill > sorted[i - 1].fill + 1) {
              problems.push(`섹션${si}: ${r.value}(${r.fill}px) > ${sorted[i - 1].value}(${sorted[i - 1].fill}px)`);
            }
          });
        });
        return problems;
      });
      check(`${label}/${vp}: 값이 큰 항목의 막대가 더 김`, bad.length === 0, bad.slice(0, 3).join(" | "));

      // "들어온 양과 실린 양"은 라벨·트랙 클래스를 위 막대들과 공유한다. 모바일에서
      // .bar-label/.bar-track에 grid-area를 클래스 단위로 걸었더니 이 행까지 끌려가
      // **매체명이 오른쪽으로 튕기고 막대가 왼쪽 절반에 찌그러졌다**(있지도 않은
      // 이름의 영역을 가리켜 암시적 트랙이 생겼다). 픽셀로만 드러나는 종류다.
      const pair = await page.evaluate(() => {
        const row = document.querySelector(".pair-row");
        if (!row) return null;   // 후보 기록이 없는 날에는 섹션 자체가 없다
        const box = (el) => { const r = el.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width }; };
        const label = box(row.querySelector(".bar-label"));
        const bars = box(row.querySelector(".pair-bars"));
        const sec = row.closest(".data-section");
        return {
          label, bars,
          트랙폭: [...new Set([...sec.querySelectorAll(".bar-track")].map(
            (e) => Math.round(e.getBoundingClientRect().width)))],
          값x: [...new Set([...sec.querySelectorAll(".pair-value")].map(
            (e) => Math.round(e.getBoundingClientRect().x)))],
          넘침: sec.scrollWidth > sec.clientWidth,
        };
      });
      if (pair) {
        const stacked = mob;   // 좁은 화면에서는 라벨이 막대 위로 올라간다
        check(`${label}/${vp}: 2단 막대 — 라벨이 ${stacked ? "막대 위" : "막대 왼쪽"}`,
          stacked ? pair.label.y < pair.bars.y : pair.label.x < pair.bars.x,
          JSON.stringify({ label: Math.round(pair.label.x) + "," + Math.round(pair.label.y),
                           bars: Math.round(pair.bars.x) + "," + Math.round(pair.bars.y) }));
        check(`${label}/${vp}: 2단 막대 트랙 폭이 모두 같음`, pair.트랙폭.length === 1,
          JSON.stringify(pair.트랙폭));
        check(`${label}/${vp}: 2단 막대 값이 한 줄로 정렬`, pair.값x.length === 1,
          JSON.stringify(pair.값x));
        check(`${label}/${vp}: 2단 막대 섹션 가로 넘침 없음`, !pair.넘침);
      }

      // 막대 폭이 곧 표기된 비율이어야 한다. 최댓값을 100%로 늘려 그리면 1위 막대가
      // 트랙을 꽉 채우는데 옆 숫자는 31.4%라, 막대와 숫자가 서로 다른 말을 한다.
      // 순위 비교용으로는 흔한 방식이지만 이 페이지는 숫자가 곧 신뢰라 맞지 않는다.
      const mismatched = await page.evaluate(() =>
        [...document.querySelectorAll(".bar-row")]
          .map((e) => {
            const pct = Number(e.querySelector(".bar-percent").dataset.percent);
            const fill = e.querySelector(".bar-fill").getBoundingClientRect().width;
            const track = e.querySelector(".bar-track").getBoundingClientRect().width;
            return { pct, drawn: Number((fill / track * 100).toFixed(1)) };
          })
          .filter((r) => Math.abs(r.pct - r.drawn) > 0.6));
      check(`${label}/${vp}: 막대 폭이 표기 비율과 일치`, mismatched.length === 0,
        JSON.stringify(mismatched.slice(0, 3)));

      // 설명 없는 막대를 두지 않는다 — 제목이나 범례가 붙은 것만 남긴다.
      const unlabeled = await page.evaluate(() =>
        [...document.querySelectorAll("main .share-bar")]
          .filter((el) => !el.parentElement.querySelector(".legend")).length);
      check(`${label}/${vp}: 범례 없는 스택 막대 없음`, unlabeled === 0, String(unlabeled));

      const over = await page.evaluate(
        () => document.documentElement.scrollWidth > window.innerWidth + 1);
      check(`${label}/${vp}: 가로 넘침 없음`, !over);
      if (vp === "데스크톱") {
        await page.screenshot({ path: path.join(SHOTS, `data-${label === "한국어" ? "ko" : "en"}.png`), fullPage: true });
      }
      await ctx.close();
    }
  }

  // ---------- 1-7. 데이터 요약 카드 ----------
  // 목차 바로 위라 이 블록이 길어지면 정작 기사 목록이 화면 밖으로 밀린다.
  // 픽셀 높이는 브라우저에서만 잡힌다.
  console.log("\n--- 유틸리티 바 정렬 ---");
  // 1280px 이상: 홈 마크는 왼쪽 여백(기둥 머리), 컨트롤은 그 거울상 자리, 메뉴는 화면 정중앙.
  // 그 아래: 셋 다 본문 칼럼 안에 인라인으로 줄지어 선다.
  // 세로는 폭과 무관하게 한 줄 — 메뉴 글자만 4px 내려앉아 있던 적이 있다.
  for (const [vp, w] of [["1920", 1920], ["1440", 1440], ["1280", 1280], ["1279", 1279], ["1024", 1024]]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: 900 }, reducedMotion: "reduce" });
    const page = await ctx.newPage();
    // 로컬 서버는 캐시 헤더를 주지 않아 크롬이 옛 CSS를 그대로 재사용한다. 실제로
    // 그 때문에 "영어판만 정렬이 다르다"는 유령 버그를 쫓은 적이 있다.
    await page.route("**/*.css", async (route) => {
      const res = await route.fetch();
      route.fulfill({ response: res, headers: { ...res.headers(), "cache-control": "no-store" } });
    });
    await page.goto(`${BASE}/index.html`, { waitUntil: "load" });
    await page.waitForTimeout(200);
    const wide = w >= 1280;
    const m = await page.evaluate(() => {
      const vw = document.documentElement.clientWidth;
      const box = (s) => { const b = document.querySelector(s).getBoundingClientRect(); return { x: b.x, r: b.x + b.width, cx: b.x + b.width / 2, cy: b.y + b.height / 2 }; };
      const link = document.querySelector(".site-nav-group > .site-nav-link");
      const lb = link.getBoundingClientRect(), cs = getComputedStyle(link);
      // 링크는 밑줄을 바 경계선까지 흘리려고 아래로 삐져나온다 — 상자 중심이 아니라
      // 글자 중심을 봐야 다른 컨트롤과 비교가 된다.
      const 글자중심 = lb.y + parseFloat(cs.paddingTop)
        + (lb.height - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom) - 3) / 2;
      const bar = document.querySelector(".utility-bar").getBoundingClientRect();
      return {
        vw, brand: box(".brand-mark"), actions: box(".utility-actions"), nav: box(".site-nav-group"),
        col: box("main.content"), 제목: box(".header-inner h1"), 메뉴글자중심: 글자중심,
        theme: box(".theme-toggle").cy, share: box(".share-button").cy, lang: box(".lang-switch").cy,
        밑줄바닥: lb.y + lb.height, 바바닥: bar.y + bar.height,
      };
    });
    const near = (a, b, t = 1.5) => Math.abs(a - b) <= t;

    check(`${vp}: 메뉴·공유·언어·테마가 같은 높이`,
      near(m.메뉴글자중심, m.theme) && near(m.메뉴글자중심, m.share) && near(m.메뉴글자중심, m.lang),
      JSON.stringify({ 메뉴: +m.메뉴글자중심.toFixed(1), 공유: +m.share.toFixed(1), 언어: +m.lang.toFixed(1), 테마: +m.theme.toFixed(1) }));
    check(`${vp}: 현재 탭 밑줄이 바 경계선 위`, near(m.밑줄바닥, m.바바닥),
      JSON.stringify({ 밑줄: +m.밑줄바닥.toFixed(1), 바: +m.바바닥.toFixed(1) }));

    if (wide) {
      check(`${vp}: 메뉴가 화면 정중앙`, near(m.nav.cx, m.vw / 2),
        JSON.stringify({ 메뉴중심: +m.nav.cx.toFixed(1), 화면중심: m.vw / 2 }));
      // 마크의 왼쪽 여백과 컨트롤의 오른쪽 여백이 같아야 좌우가 거울상이 된다.
      check(`${vp}: 마크와 컨트롤이 좌우 대칭`, near(m.brand.x, m.vw - m.actions.r),
        JSON.stringify({ 왼: +m.brand.x.toFixed(1), 오: +(m.vw - m.actions.r).toFixed(1) }));
      check(`${vp}: 마크가 본문 칼럼 바깥(왼쪽 여백)`, m.brand.r <= m.col.x + 1);
      check(`${vp}: 컨트롤이 본문 칼럼 바깥(오른쪽 여백)`, m.actions.x >= m.col.r - 1);
      check(`${vp}: 메뉴가 마크·컨트롤과 겹치지 않음`, m.nav.x > m.brand.r && m.nav.r < m.actions.x,
        JSON.stringify({ nav: [+m.nav.x.toFixed(0), +m.nav.r.toFixed(0)], brandR: +m.brand.r.toFixed(0), actionsX: +m.actions.x.toFixed(0) }));
    } else {
      // 기준은 칼럼 상자가 아니라 **글자가 시작하는 선**이다 — 칼럼 상자에는 24px
      // 안쪽 여백이 있어 상자 모서리로 재면 24px씩 어긋난 것으로 나온다.
      check(`${vp}: 마크가 제목 글자와 같은 선에서 시작`, near(m.brand.x, m.제목.x),
        JSON.stringify({ 마크: +m.brand.x.toFixed(1), 제목: +m.제목.x.toFixed(1) }));
      check(`${vp}: 컨트롤이 본문 오른쪽 끝선에 맞음`, near(m.actions.r, m.제목.r),
        JSON.stringify({ 컨트롤: +m.actions.r.toFixed(1), 본문끝: +m.제목.r.toFixed(1) }));
    }
    check(`${vp}: 가로 스크롤 없음`,
      !(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)));
    await ctx.close();
  }


  console.log("\n--- 데이터 요약 카드 ---");
  // 1280px 이상: 왼쪽 기둥(.side-rail) 안, 목차 레일 위.
  // 그 아래: 기둥이 없으므로 본문 목차 앞에 링크 한 줄만. 막대를 그대로 두면
  //          카드 하나가 첫 화면을 차지해 기사 목록이 그만큼 밀린다.
  for (const [vp, w, h, mob] of [
    ["데스크톱1440", 1440, 900, false],
    ["경계1280", 1280, 900, false],
    ["경계1279", 1279, 900, false],
    ["태블릿820", 820, 1100, false],
    ["모바일390", 390, 844, true],
  ]) {
    const ctx = await browser.newContext({
      viewport: { width: w, height: h }, locale: "ko-KR", isMobile: mob, hasTouch: mob,
      reducedMotion: "reduce",
    });
    const page = await ctx.newPage();
    await page.goto(`${BASE}/index.html`, { waitUntil: "load" });
    await page.waitForTimeout(200);
    const wide = w >= 1280;
    const card = page.locator(".data-card");
    const box = await card.boundingBox();

    check(`${vp}: 카드가 하나만 존재`, (await card.count()) === 1);
    check(`${vp}: /data 링크 표시`, await page.locator(".data-card-link").isVisible());
    check(`${vp}: 상단 메뉴에 데이터 항목`,
      (await page.locator(".utility-bar .site-nav-link", { hasText: "데이터" }).count()) >= 1);
    check(`${vp}: 막대 ${wide ? "표시" : "숨김"}`,
      (await page.locator(".data-card-bars").isVisible()) === wide);

    if (wide) {
      const inRail = await page.evaluate(() => {
        const c = document.querySelector(".data-card");
        return !!(c && c.closest(".side-rail"));
      });
      check(`${vp}: 카드가 왼쪽 기둥 안`, inRail);
      const rail = await page.locator("#toc-rail").boundingBox();
      const col = await page.locator("main.content").boundingBox();
      check(`${vp}: 목차 레일보다 위`, box && rail && box.y + box.height <= rail.y + 1,
        JSON.stringify({ cardEnd: Math.round(box.y + box.height), rail: Math.round(rail.y) }));
      check(`${vp}: 본문과 겹치지 않음`, box && col && box.x + box.width <= col.x + 1,
        JSON.stringify({ cardEnd: Math.round(box.x + box.width), col: Math.round(col.x) }));
      check(`${vp}: 기둥이 화면 왼쪽 밖으로 나가지 않음`, box && box.x >= 0, String(Math.round(box.x)));
      const sr = await page.locator(".side-rail").boundingBox();
      check(`${vp}: 기둥이 화면 아래로 넘치지 않음`, sr && sr.y + sr.height <= h + 1,
        JSON.stringify({ end: Math.round(sr.y + sr.height), h }));
      const tracks = await page.locator(".data-card-bars li:visible .data-card-track")
        .evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().width)));
      check(`${vp}: 카드 막대 트랙 폭 일정`, new Set(tracks).size <= 2, JSON.stringify(tracks));
    } else {
      const col = await page.locator("main.content").boundingBox();
      check(`${vp}: 본문 폭 안`, box && col && box.x >= col.x - 1 && box.x + box.width <= col.x + col.width + 1,
        JSON.stringify(box));
      const toc = await page.locator("nav.toc").boundingBox();
      check(`${vp}: 목차보다 위`, box && toc && box.y < toc.y,
        JSON.stringify({ card: Math.round(box.y), toc: Math.round(toc.y) }));
      // 링크 한 줄이면 70px 안쪽이다. 넘으면 접기 규칙이 어딘가에서 덮인 것이다 —
      // site-desktop.css가 site-base.css 뒤에 실려 실제로 그랬다(768~1279px 구간).
      check(`${vp}: 카드가 링크 한 줄 높이`, box && box.height < 70, `${Math.round(box.height)}px`);
    }
    check(`${vp}: 가로 스크롤 없음`,
      !(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)));
    await ctx.close();
  }

  // 창 크기를 오가도 카드가 사라지거나 두 벌이 되지 않아야 한다.
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
    const page = await ctx.newPage();
    await page.goto(`${BASE}/index.html`, { waitUntil: "load" });
    await page.waitForTimeout(200);
    const where = () => page.evaluate(() =>
      document.querySelector(".data-card").closest(".side-rail") ? "rail" : "flow");
    check("리사이즈: 1440에서 기둥", (await where()) === "rail");
    await page.setViewportSize({ width: 1000, height: 900 });
    await page.waitForTimeout(300);
    check("리사이즈: 1000으로 줄이면 본문 복귀", (await where()) === "flow");
    check("리사이즈: 줄인 뒤에도 링크 표시", await page.locator(".data-card-link").isVisible());
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.waitForTimeout(300);
    check("리사이즈: 넓히면 다시 기둥", (await where()) === "rail");
    check("리사이즈: 왕복 후에도 카드는 하나", (await page.locator(".data-card").count()) === 1);
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
