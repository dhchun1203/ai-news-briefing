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

let state = { row: null, resendCalls: 0, patches: [] };

global.fetch = async (url, opts = {}) => {
  const u = String(url);
  if (u.startsWith("https://api.resend.com")) {
    state.resendCalls++;
    return { ok: true, status: 200, text: async () => "", json: async () => ({ id: "x" }) };
  }
  if (u.includes("/rest/v1/subscribers")) {
    const method = opts.method || "GET";
    if (method === "GET") {
      return { ok: true, status: 200, text: async () => "", json: async () => (state.row ? [state.row] : []) };
    }
    if (method === "POST") {
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
const tokens = require(ROOT + "/api/_lib/tokens.js");

const results = [];
function check(name, cond, extra = "") {
  results.push({ name, ok: !!cond, extra });
}

(async () => {
  // --- subscribe: rate limiting ---
  state = { row: null, resendCalls: 0, patches: [] };
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
  state = { row: null, resendCalls: 0, patches: [] };
  res = mockRes();
  await subscribe({ method: "POST", body: { email: "u@x.com" } }, res);
  check("db error -> 502", res._status === 502);
  check("db error leaks no internals", !/supabase|table|host/i.test(res._body), res._body);
  global.fetch = brokenFetch;

  // --- unsubscribe: GET must NOT mutate ---
  state = { row: { email: "u@x.com", confirmed_at: "t", unsubscribed_at: null, last_confirm_sent_at: null }, resendCalls: 0, patches: [] };
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

  let pass = 0;
  for (const r of results) {
    console.log((r.ok ? "PASS " : "FAIL ") + r.name + (r.ok ? "" : "  << " + r.extra));
    if (r.ok) pass++;
  }
  console.log(`\n${pass}/${results.length} passed`);
  process.exit(pass === results.length ? 0 : 1);
})();
