// api/ 핸들러들을 실제 네트워크 없이 돌려보는 최소 하네스.
// Supabase/Resend fetch를 가로채 호출을 기록하고, 응답 객체를 흉내낸다.
process.env.SUBSCRIBE_TOKEN_SECRET = "test-secret";
process.env.SITE_URL = "https://www.dailyaithread.com/";
process.env.RESEND_SENDER_EMAIL = "briefing@dailyaithread.com";
process.env.RESEND_API_KEY = "re_test";
process.env.SUPABASE_URL = "https://proj.supabase.co";
process.env.SUPABASE_SERVICE_ROLE_KEY = "svc_test";

const path = require("path");
const ROOT = path.join(__dirname, "..");

const freshState = (over = {}) =>
  ({ row: null, resendCalls: 0, patches: [], rpcCalls: [], rpcFails: false, inserts: [], mails: [], ...over });
let state = freshState();

global.fetch = async (url, opts = {}) => {
  const u = String(url);
  if (u.startsWith("https://api.resend.com")) {
    state.resendCalls++;
    state.mails.push(JSON.parse(opts.body));
    return { ok: true, status: 200, text: async () => "", json: async () => ({ id: "x" }) };
  }
  if (u.includes("/rest/v1/rpc/search_archive")) {
    state.rpcCalls.push(JSON.parse(opts.body));
    if (state.rpcFails) {
      return { ok: false, status: 500, text: async () => "boom at proj.supabase.co table=search_articles" };
    }
    return {
      ok: true,
      status: 200,
      text: async () => "",
      json: async () => [{ date: "2026-07-27", title: "T", link: "https://x", source: "S" }],
    };
  }
  if (u.includes("/rest/v1/subscribers")) {
    const method = opts.method || "GET";
    if (method === "GET") {
      return { ok: true, status: 200, text: async () => "", json: async () => (state.row ? [state.row] : []) };
    }
    if (method === "POST") {
      state.inserts.push(JSON.parse(opts.body)[0]);
      state.row = { email: "u@x.com", confirmed_at: null, unsubscribed_at: null, last_confirm_sent_at: null };
      return { ok: true, status: 201, text: async () => "", json: async () => ({}) };
    }
    if (method === "PATCH") {
      const patch = JSON.parse(opts.body);
      state.patches.push(patch);
      state.row = { ...(state.row || {}), ...patch };
      return { ok: true, status: 204, text: async () => "", json: async () => ({}) };
    }
  }
  throw new Error("unexpected fetch: " + u);
};

function mockRes() {
  const r = { _status: 200, _body: "", _headers: {} };
  r.status = (c) => { r._status = c; return r; };
  r.json = (o) => { r._body = JSON.stringify(o); return r; };
  r.send = (s) => { r._body = s; return r; };
  r.setHeader = (k, v) => { r._headers[k] = v; };
  return r;
}

const subscribe = require(ROOT + "/api/subscribe.js");
const unsubscribe = require(ROOT + "/api/unsubscribe.js");
const confirm = require(ROOT + "/api/confirm.js");
const { MESSAGES, LANGS, normalizeLang, homePath } = require(ROOT + "/api/_lib/messages.js");
const { COPY } = require(ROOT + "/api/_lib/confirm-mail.js");
const page = require(ROOT + "/api/_lib/page.js");
const search = require(ROOT + "/api/search.js");
const tokens = require(ROOT + "/api/_lib/tokens.js");

const results = [];
function check(name, cond, extra = "") {
  results.push({ name, ok: !!cond, extra });
}

(async () => {
  // --- subscribe: rate limiting ---
  state = freshState();
  let res = mockRes();
  await subscribe({ method: "POST", body: { email: "u@x.com" } }, res);
  check("subscribe #1 succeeds", res._status === 200 && state.resendCalls === 1);
  check("subscribe #1 records last_confirm_sent_at",
    state.patches.some((p) => p.last_confirm_sent_at));

  res = mockRes();
  await subscribe({ method: "POST", body: { email: "u@x.com" } }, res);
  check("subscribe #2 within cooldown sends NO 2nd mail", state.resendCalls === 1, `resendCalls=${state.resendCalls}`);
  check("subscribe #2 still returns 200 (no enumeration oracle)", res._status === 200);

  // cooldown expired -> should send again
  state.row.last_confirm_sent_at = new Date(Date.now() - 60 * 60 * 1000).toISOString();
  res = mockRes();
  await subscribe({ method: "POST", body: { email: "u@x.com" } }, res);
  check("subscribe after cooldown sends again", state.resendCalls === 2, `resendCalls=${state.resendCalls}`);

  // already confirmed -> no mail
  state.row = { email: "u@x.com", confirmed_at: new Date().toISOString(), unsubscribed_at: null, last_confirm_sent_at: null };
  res = mockRes();
  await subscribe({ method: "POST", body: { email: "u@x.com" } }, res);
  check("already-confirmed sends no mail", state.resendCalls === 2, `resendCalls=${state.resendCalls}`);

  // --- subscribe: no internal detail leak ---
  const brokenFetch = global.fetch;
  global.fetch = async () => { throw new Error("supabase insert failed: 500 host=proj.supabase.co table=subscribers"); };
  state = freshState();
  res = mockRes();
  await subscribe({ method: "POST", body: { email: "u@x.com" } }, res);
  check("db error -> 502", res._status === 502);
  check("db error leaks no internals", !/supabase|table|host/i.test(res._body), res._body);
  global.fetch = brokenFetch;

  // --- unsubscribe: GET must NOT mutate ---
  state = freshState({ row: { email: "u@x.com", confirmed_at: "t", unsubscribed_at: null, last_confirm_sent_at: null } });
  const tok = tokens.makeUnsubscribeToken("u@x.com");
  res = mockRes();
  await unsubscribe({ method: "GET", query: { email: "u@x.com", token: tok } }, res);
  check("GET unsubscribe returns confirm page", res._status === 200 && res._body.includes("<form") && res._body.includes("POST"));
  check("GET unsubscribe does NOT touch DB (scanner-safe)", state.patches.length === 0, `patches=${state.patches.length}`);
  check("GET unsubscribe sets no-store", res._headers["Cache-Control"] === "no-store");

  // --- unsubscribe: POST does mutate ---
  res = mockRes();
  await unsubscribe({ method: "POST", body: { email: "u@x.com", token: tok } }, res);
  check("POST unsubscribe applies", res._status === 200 && state.patches.some((p) => p.unsubscribed_at));

  // --- unsubscribe: bad token rejected on both verbs ---
  state.patches = [];
  res = mockRes();
  await unsubscribe({ method: "POST", body: { email: "u@x.com", token: "forged" } }, res);
  check("forged token rejected", res._status === 400 && state.patches.length === 0);

  // --- confirm token: signature checked before expiry ---
  const { token: ct, expiry } = tokens.makeConfirmToken("u@x.com");
  check("valid confirm token ok", tokens.verifyConfirmToken("u@x.com", expiry, ct).ok === true);
  const expired = tokens.makeConfirmToken("u@x.com", -10);
  check("expired-but-signed -> 'expired'", tokens.verifyConfirmToken("u@x.com", expired.expiry, expired.token).reason === "expired");
  check("forged+expired -> 'invalid' (no expiry oracle)",
    tokens.verifyConfirmToken("u@x.com", expired.expiry, "forged").reason === "invalid");

  // --- search: 정상 조회 ---
  state.rpcCalls = [];
  res = mockRes();
  await search({ method: "GET", query: { q: "오퍼스" } }, res);
  check("search returns results", res._status === 200 && JSON.parse(res._body).results.length === 1);
  check("search passes query as RPC arg (not a URL filter)",
    state.rpcCalls.length === 1 && state.rpcCalls[0].q === "오퍼스", JSON.stringify(state.rpcCalls));

  // --- search: 빈 질의는 에러가 아니라 빈 결과 ---
  state.rpcCalls = [];
  res = mockRes();
  await search({ method: "GET", query: { q: "   " } }, res);
  check("empty query -> 200 empty, no DB hit",
    res._status === 200 && JSON.parse(res._body).results.length === 0 && state.rpcCalls.length === 0);

  // --- search: 길이 상한 (인증 없는 공개 엔드포인트라 입구에서 막아야 한다) ---
  state.rpcCalls = [];
  res = mockRes();
  await search({ method: "GET", query: { q: "가".repeat(101) } }, res);
  check("over-long query rejected without hitting DB",
    res._status === 400 && state.rpcCalls.length === 0);

  // --- search: limit 상한 (임의로 큰 값을 넣어도 DB에 그대로 안 넘어간다) ---
  state.rpcCalls = [];
  res = mockRes();
  await search({ method: "GET", query: { q: "ai", limit: "9999" } }, res);
  check("limit is capped", state.rpcCalls[0].max_results === 50, JSON.stringify(state.rpcCalls[0]));

  // --- search: GET 외 거부 ---
  res = mockRes();
  await search({ method: "POST", query: {} }, res);
  check("non-GET rejected", res._status === 405);

  // --- search: DB 오류 시 내부 정보가 새지 않아야 한다 ---
  state.rpcFails = true;
  res = mockRes();
  await search({ method: "GET", query: { q: "ai" } }, res);
  const errBody = res._body;
  check("db failure -> 502 with generic code", res._status === 502 && JSON.parse(errBody).error === "search_unavailable");
  check("db failure leaks no host/table name",
    !errBody.includes("supabase.co") && !errBody.includes("search_articles"), errBody);
  state.rpcFails = false;

  // --- subscribe: 구독 시점 시간대 기록 (기록 전용, 발송에는 아직 안 쓴다) ---
  // 이 필드가 조용히 유실되면 되돌릴 방법이 없다 — 지난 구독자의 시간대는
  // 나중에 복구할 수 없으므로 저장 경로를 테스트로 고정한다.
  const freshSubscribe = async (body) => {
    state = freshState();
    const r = mockRes();
    await subscribe({ method: "POST", body }, r);
    return r;
  };

  await freshSubscribe({ email: "tz@x.com", timezone: "America/New_York" });
  check("subscribe stores browser timezone",
    state.inserts[0] && state.inserts[0].timezone === "America/New_York",
    JSON.stringify(state.inserts[0]));

  await freshSubscribe({ email: "tz2@x.com", timezone: "America/Indiana/Indianapolis" });
  check("3-segment IANA name accepted",
    state.inserts[0] && state.inserts[0].timezone === "America/Indiana/Indianapolis",
    JSON.stringify(state.inserts[0]));

  // 시간대는 부가 정보다. 없거나 이상해도 구독 자체는 반드시 성공해야 한다.
  let r0 = await freshSubscribe({ email: "notz@x.com" });
  check("missing timezone still subscribes",
    r0._status === 200 && state.inserts[0] && !("timezone" in state.inserts[0]),
    `status=${r0._status} row=${JSON.stringify(state.inserts[0])}`);

  for (const bad of ["../../etc/passwd", "<script>", "Asia/Seoul; DROP TABLE x", "x".repeat(80)]) {
    r0 = await freshSubscribe({ email: "bad@x.com", timezone: bad });
    check(`rejects junk timezone (${bad.slice(0, 18)}) but still subscribes`,
      r0._status === 200 && state.inserts[0] && !("timezone" in state.inserts[0]),
      `status=${r0._status} row=${JSON.stringify(state.inserts[0])}`);
  }

  // --- confirm: 만료된 링크에서 새 확인 메일 받기 ---
  // 24시간 만료 때문에 실제로 확정을 못 한 구독자가 나왔다. 만료 페이지가 다시
  // 막다른 길로 돌아가지 않도록 재발송 경로를 고정한다.
  const { makeConfirmToken, makeUnsubscribeToken } = require(ROOT + "/api/_lib/tokens.js");
  const expiredLink = (email) => {
    const t = makeConfirmToken(email, -60); // 이미 만료된 토큰
    return { email, expiry: String(t.expiry), token: t.token };
  };
  const pendingRow = (over = {}) =>
    ({ email: "u@x.com", confirmed_at: null, unsubscribed_at: null, last_confirm_sent_at: null, ...over });

  // GET은 메일을 보내지 않는다 — 메일 스캐너가 링크를 미리 열기 때문이다.
  state = freshState({ row: pendingRow() });
  res = mockRes();
  await confirm({ method: "GET", query: expiredLink("u@x.com") }, res);
  check("expired GET sends no mail, shows resend button",
    state.resendCalls === 0 && res._body.includes("확인 메일 다시 받기"), `calls=${state.resendCalls}`);

  // 버튼을 눌러 POST 하면 그때 보낸다.
  state = freshState({ row: pendingRow() });
  res = mockRes();
  await confirm({ method: "POST", body: expiredLink("u@x.com") }, res);
  check("expired POST resends confirm mail",
    res._status === 200 && state.resendCalls === 1, `status=${res._status} calls=${state.resendCalls}`);
  check("resend records last_confirm_sent_at",
    state.patches.some((p) => p.last_confirm_sent_at), JSON.stringify(state.patches));

  // 폼 전송(urlencoded 문자열)로 와도 동작해야 한다.
  state = freshState({ row: pendingRow() });
  res = mockRes();
  await confirm({ method: "POST", body: new URLSearchParams(expiredLink("u@x.com")).toString() }, res);
  check("expired POST accepts urlencoded form body", state.resendCalls === 1, `calls=${state.resendCalls}`);

  // 쿨다운 중이면 보내지 않는다 — 이 버튼이 메일 폭탄 증폭기가 되면 안 된다.
  state = freshState({ row: pendingRow({ last_confirm_sent_at: new Date().toISOString() }) });
  res = mockRes();
  await confirm({ method: "POST", body: expiredLink("u@x.com") }, res);
  check("resend within cooldown sends NO mail", state.resendCalls === 0, `calls=${state.resendCalls}`);

  // 서명이 틀리면 만료 페이지조차 보여주지 않는다.
  state = freshState({ row: pendingRow() });
  res = mockRes();
  await confirm({ method: "POST", body: { email: "u@x.com", expiry: "1", token: "forged" } }, res);
  check("forged token: no mail, no resend page",
    state.resendCalls === 0 && res._status === 400 && !res._body.includes("다시 받기"), res._status);

  // 남의 주소로 서명을 재사용할 수 없다 — 토큰은 주소마다 다르다.
  state = freshState({ row: pendingRow() });
  res = mockRes();
  const stolen = expiredLink("u@x.com");
  res = mockRes();
  await confirm({ method: "POST", body: { ...stolen, email: "victim@x.com" } }, res);
  check("token cannot be replayed for another address",
    state.resendCalls === 0 && res._status === 400, `calls=${state.resendCalls} status=${res._status}`);

  // 해지한 주소에는 다시 보내지 않는다.
  state = freshState({ row: pendingRow({ unsubscribed_at: new Date().toISOString() }) });
  res = mockRes();
  await confirm({ method: "POST", body: expiredLink("u@x.com") }, res);
  check("unsubscribed address is not re-mailed", state.resendCalls === 0, `calls=${state.resendCalls}`);

  // 유효한 링크는 예전처럼 바로 확정된다 (회귀 방지).
  state = freshState({ row: pendingRow() });
  res = mockRes();
  const live = makeConfirmToken("u@x.com");
  await confirm({ method: "GET", query: { email: "u@x.com", expiry: String(live.expiry), token: live.token } }, res);
  check("valid link still confirms directly",
    res._status === 200 && res._body.includes("구독 확인 완료"), res._status);

  // 확인 링크 유효기간이 7일인지 — 만료 페이지 문구("7일 이내")와 맞아야 한다.
  const ttl = makeConfirmToken("u@x.com").expiry - Math.floor(Date.now() / 1000);
  check("confirm token TTL is 7 days", Math.abs(ttl - 7 * 24 * 3600) <= 5, `ttl=${ttl}s`);

  // --- 언어: /en/ 구독자에게 한국어가 새면 안 된다 ---
  // 영어 화면·메일에 한글이 한 글자라도 있으면 분기를 빠뜨린 것이다. 한국어 사용자는
  // 영어 화면을 볼 일이 없어 사람 눈으로는 절대 안 잡힌다.
  const HANGUL = /[가-힣]/g;
  const noKorean = (s) => (String(s).match(HANGUL) || []).join("");

  // 1) 메시지 표 자체 — 두 언어가 다 있고, 영어에 한글이 없어야 한다.
  {
    let bad = [];
    for (const [key, entry] of Object.entries(MESSAGES)) {
      for (const lang of LANGS) {
        if (!entry[lang]) bad.push(`${key}.${lang} 없음`);
      }
      const koKeys = Object.keys(entry.ko || {}).sort().join(",");
      const enKeys = Object.keys(entry.en || {}).sort().join(",");
      if (koKeys !== enKeys) bad.push(`${key} 필드 불일치 ko(${koKeys}) en(${enKeys})`);
      for (const [f, v] of Object.entries(entry.en || {})) {
        if (noKorean(v)) bad.push(`${key}.en.${f}에 한글`);
        if (!String(v).trim()) bad.push(`${key}.en.${f} 비어 있음`);
      }
      for (const [f, v] of Object.entries(entry.ko || {})) {
        if (!String(v).trim()) bad.push(`${key}.ko.${f} 비어 있음`);
      }
    }
    check("every message key has both languages, English has no Korean", bad.length === 0, bad.join(" | "));
  }

  // 2) 확인 메일 문구
  {
    let bad = [];
    if (Object.keys(COPY.ko).sort().join() !== Object.keys(COPY.en).sort().join()) bad.push("키 불일치");
    for (const [k, v] of Object.entries(COPY.en)) if (noKorean(v)) bad.push(`confirm mail en.${k}`);
    check("confirm mail copy: English has no Korean", bad.length === 0, bad.join(" | "));
  }

  // 3) 렌더된 페이지 전수 검사 — 모든 메시지 키를 영어로 그려 한글이 없는지 본다.
  {
    let bad = [];
    for (const key of Object.keys(MESSAGES)) {
      if (key === "back_link") continue; // 페이지가 아니라 링크 문구
      if (key === "confirm_expired" || key === "unsub_confirm") continue; // 아래에서 폼째로 검사
      const html = page.resultPage("en", key, "https://x.test");
      if (noKorean(html)) bad.push(`${key}: ${noKorean(html)}`);
      if (!html.includes('<html lang="en">')) bad.push(`${key}: lang 속성 틀림`);
    }
    const expired = page.confirmExpiredPage("u@x.com", "1", "t", "https://x.test", "en");
    if (noKorean(expired)) bad.push(`confirm_expired: ${noKorean(expired)}`);
    const unsub = page.unsubscribeConfirmPage("u@x.com", "t", "https://x.test", "en");
    if (noKorean(unsub)) bad.push(`unsub_confirm: ${noKorean(unsub)}`);
    check("every English page renders without Korean", bad.length === 0, bad.join(" | "));
  }

  // 4) 한국어 페이지는 그대로 한국어여야 한다 (영문화가 한국어를 깨뜨리지 않았는지)
  check("Korean pages are still Korean",
    /[가-힣]/.test(page.resultPage("ko", "confirm_ok", "https://x.test")) &&
    page.resultPage("ko", "confirm_ok", "https://x.test").includes('<html lang="ko">'));

  // 5) 영어 페이지의 "돌아가기" 링크는 /en 으로 가야 한다 — 한국어 홈으로 보내면 길을 잃는다.
  check("English pages link back to /en",
    page.resultPage("en", "confirm_ok", "https://x.test").includes('href="https://x.test/en"'),
    page.resultPage("en", "confirm_ok", "https://x.test"));
  check("Korean pages link back to /", homePath("ko") === "/" && homePath("en") === "/en");

  // 6) 알 수 없는 언어는 한국어로 떨어진다 (요청을 실패시키지 않는다)
  check("unknown lang falls back to ko",
    ["fr", "", null, undefined, "EN-US", 5].every((v) => LANGS.includes(normalizeLang(v))) &&
    normalizeLang("fr") === "ko" && normalizeLang(" EN ") === "en");

  // 7) 구독 시 언어가 저장되고, 그 언어로 확인 메일이 나간다
  state = freshState();
  res = mockRes();
  await subscribe({ method: "POST", body: { email: "en@x.com", lang: "en" } }, res);
  check("subscribe stores lang", state.inserts[0] && state.inserts[0].lang === "en",
    JSON.stringify(state.inserts[0]));
  check("English signup gets English confirm mail",
    state.mails[0] && !noKorean(state.mails[0].subject) && !noKorean(state.mails[0].html),
    state.mails[0] ? noKorean(state.mails[0].subject + state.mails[0].html) : "메일 없음");
  check("English confirm link carries lang=en",
    state.mails[0] && state.mails[0].html.includes("lang=en"), state.mails[0] && state.mails[0].html);

  state = freshState();
  res = mockRes();
  await subscribe({ method: "POST", body: { email: "ko@x.com" } }, res);
  check("subscribe defaults lang to ko", state.inserts[0] && state.inserts[0].lang === "ko",
    JSON.stringify(state.inserts[0]));
  check("Korean signup gets Korean confirm mail",
    state.mails[0] && /[가-힣]/.test(state.mails[0].subject));

  state = freshState();
  res = mockRes();
  await subscribe({ method: "POST", body: { email: "x@x.com", lang: "klingon" } }, res);
  check("junk lang falls back to ko without failing signup",
    res._status === 200 && state.inserts[0].lang === "ko", `status=${res._status}`);

  // 8) 이미 있는 구독자는 처음 등록한 언어를 유지한다
  state = freshState({ row: { email: "u@x.com", confirmed_at: null, unsubscribed_at: null, last_confirm_sent_at: null, lang: "en" } });
  res = mockRes();
  await subscribe({ method: "POST", body: { email: "u@x.com", lang: "ko" } }, res);
  check("existing subscriber keeps their original language",
    state.mails[0] && !noKorean(state.mails[0].subject),
    state.mails[0] ? state.mails[0].subject : "메일 없음");

  // 9) 만료 재발송도 영어로
  state = freshState({ row: pendingRow() });
  res = mockRes();
  await confirm({ method: "POST", body: { ...expiredLink("u@x.com"), lang: "en" } }, res);
  check("expired resend uses the page language",
    state.mails[0] && !noKorean(state.mails[0].subject + state.mails[0].html) && !noKorean(res._body),
    state.mails[0] ? noKorean(state.mails[0].subject + state.mails[0].html) : "메일 없음");

  // 10) 구독취소 페이지 언어
  {
    const { makeUnsubscribeToken: mk } = require(ROOT + "/api/_lib/tokens.js");
    state = freshState({ row: pendingRow() });
    res = mockRes();
    await unsubscribe({ method: "GET", query: { email: "u@x.com", token: mk("u@x.com"), lang: "en" } }, res);
    check("English unsubscribe page has no Korean", !noKorean(res._body), noKorean(res._body));
    res = mockRes();
    await unsubscribe({ method: "POST", body: { email: "u@x.com", token: mk("u@x.com"), lang: "en" } }, res);
    check("English unsubscribe result has no Korean",
      res._status === 200 && !noKorean(res._body), noKorean(res._body));
    res = mockRes();
    await unsubscribe({ method: "GET", query: { email: "u@x.com", token: mk("u@x.com") } }, res);
    check("Korean unsubscribe page is still Korean", /[가-힣]/.test(res._body));
  }

  let pass = 0;
  for (const r of results) {
    console.log((r.ok ? "PASS " : "FAIL ") + r.name + (r.ok ? "" : "  << " + r.extra));
    if (r.ok) pass++;
  }
  console.log(`\n${pass}/${results.length} passed`);
  process.exit(pass === results.length ? 0 : 1);
})();
