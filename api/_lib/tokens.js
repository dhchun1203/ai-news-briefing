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

function makeConfirmToken(email, ttlSeconds = 60 * 60 * 24) {
  const expiry = Math.floor(Date.now() / 1000) + ttlSeconds;
  const token = sign(`confirm|${email}|${expiry}`);
  return { token, expiry };
}

function verifyConfirmToken(email, expiry, token) {
  const expiryNum = parseInt(expiry, 10);
  if (!Number.isFinite(expiryNum) || expiryNum < Math.floor(Date.now() / 1000)) {
    return { ok: false, reason: "expired" };
  }
  const expected = sign(`confirm|${email}|${expiryNum}`);
  if (!safeEqual(expected, token)) return { ok: false, reason: "invalid" };
  return { ok: true };
}

function makeUnsubscribeToken(email) {
  return sign(`unsubscribe|${email}`);
}

function verifyUnsubscribeToken(email, token) {
  const expected = sign(`unsubscribe|${email}`);
  return safeEqual(expected, token);
}

module.exports = {
  isValidEmail,
  makeConfirmToken,
  verifyConfirmToken,
  makeUnsubscribeToken,
  verifyUnsubscribeToken,
};
