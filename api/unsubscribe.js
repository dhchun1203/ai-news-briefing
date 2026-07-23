// GET ?email=&token= -> 서명을 검증하고 통과하면 구독을 취소한다. 만료 없이 영구히 유효한
// 링크라 매일 발송되는 이메일 하단 링크로 계속 재사용된다.
const { isValidEmail, verifyUnsubscribeToken } = require("./_lib/tokens");
const { markUnsubscribed } = require("./_lib/supabase");
const { resultPage } = require("./_lib/page");

module.exports = async function handler(req, res) {
  const siteUrl = (process.env.SITE_URL || "").replace(/\/$/, "");
  const { email, token } = req.query || {};

  if (!email || !token || !isValidEmail(String(email)) || !verifyUnsubscribeToken(String(email), String(token))) {
    res.status(400).send(resultPage("처리 실패", "유효하지 않은 구독취소 링크입니다.", siteUrl));
    return;
  }

  try {
    await markUnsubscribed(String(email));
  } catch (err) {
    res.status(502).send(resultPage("오류", "구독취소 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.", siteUrl));
    return;
  }

  res.status(200).send(resultPage("구독취소 완료", "더 이상 이메일이 발송되지 않습니다. 언제든 다시 구독하실 수 있어요.", siteUrl));
};
