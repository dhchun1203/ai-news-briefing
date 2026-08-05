// 확인/구독취소 링크에 쓰는 서명 토큰. 별도 저장소 없이 HMAC 서명만으로 검증한다.
// - confirm 토큰: 이메일 소유권 증명용이라 만료 시간을 둔다 (기본 24시간).
// - unsubscribe 토큰: 링크가 영구히 살아있어야 하므로 만료 시간을 두지 않는다.
const crypto = require("crypto");

function getSecret() {
  const secret = process.env.SUBSCRIBE_TOKEN_SECRET;
  if (!secret) throw new Error("SUBSCRIBE_TOKEN_SECRET not configured");
  return secret;
}

function sign(payload) {
  return crypto.createHmac("sha256", getSecret()).update(payload).digest("base64url");
}

function safeEqual(a, b) {
  const bufA = Buffer.from(String(a));
  const bufB = Buffer.from(String(b));
  if (bufA.length !== bufB.length) return false;
  return crypto.timingSafeEqual(bufA, bufB);
}

function isValidEmail(email) {
  return (
    typeof email === "string" &&
    email.length <= 254 &&
    /^[^\s@<>"']+@[^\s@<>"']+\.[^\s@<>"']+$/.test(email)
  );
}

// 확인 링크 유효기간. 24시간이었을 때 실제로 놓치는 사람이 나왔다 — 가입 45시간 뒤까지
// 확정을 못 한 구독자의 링크가 이미 죽어 있었고, 만료 페이지는 "다시 신청하세요"라는
// 막다른 안내뿐이었다. 이메일 확인 토큰에 7일은 업계 관례 범위이고, 확정 자체가
// 되돌리기 쉬우므로(모든 발송 메일 하단에 구독취소 링크) 늘려도 위험이 낮다.
//
// 이 값은 확인 메일 본문의 "7일 이내 유효" 문구와 반드시 맞아야 한다. 그래서 기본값을
// 여기 한 곳에만 두고 호출부에서 따로 정하지 않는다.
const CONFIRM_TTL_SECONDS = 60 * 60 * 24 * 7;

function makeConfirmToken(email, ttlSeconds = CONFIRM_TTL_SECONDS) {
  const expiry = Math.floor(Date.now() / 1000) + ttlSeconds;
  const token = sign(`confirm|${email}|${expiry}`);
  return { token, expiry };
}

function verifyConfirmToken(email, expiry, token) {
  const expiryNum = parseInt(expiry, 10);
  if (!Number.isFinite(expiryNum)) return { ok: false, reason: "invalid" };
  // 서명을 먼저 검증한다. 만료를 먼저 보면 인증되지 않은 호출자에게 "이 토큰은
  // 서명은 맞는데 만료됐다"와 "아예 위조다"를 구분해 알려주게 된다 — 서명이
  // 통과한 요청에 대해서만 만료 여부를 알려주는 편이 덜 흘린다.
  const expected = sign(`confirm|${email}|${expiryNum}`);
  if (!safeEqual(expected, token)) return { ok: false, reason: "invalid" };
  if (expiryNum < Math.floor(Date.now() / 1000)) return { ok: false, reason: "expired" };
  return { ok: true };
}

// 현재 api/ 안에서는 쓰이지 않는다 — 구독취소 링크는 발송 시점에
// scripts/send_broadcast.py가 파이썬으로 직접 서명해 만든다. 그럼에도 남겨두는 이유는
// 이 함수가 파이썬 구현과 맞물려야 하는 **언어를 넘는 계약**을 코드로 드러내기
// 때문이다(두 구현이 어긋나면 모든 구독취소 링크가 조용히 죽는다). 이 계약은
// tests/에서 양쪽 결과를 비교해 검증한다.
function makeUnsubscribeToken(email) {
  return sign(`unsubscribe|${email}`);
}

function verifyUnsubscribeToken(email, token) {
  const expected = sign(`unsubscribe|${email}`);
  return safeEqual(expected, token);
}

module.exports = {
  CONFIRM_TTL_SECONDS,
  isValidEmail,
  makeConfirmToken,
  verifyConfirmToken,
  makeUnsubscribeToken,
  verifyUnsubscribeToken,
};
