// GET ?email=&expiry=&token= -> 서명을 검증하고 통과하면 구독을 확정한다 (더블 옵트인 2단계).
const { isValidEmail, verifyConfirmToken } = require("./_lib/tokens");
const { markConfirmed } = require("./_lib/supabase");
const { resultPage } = require("./_lib/page");

module.exports = async function handler(req, res) {
  const siteUrl = (process.env.SITE_URL || "").replace(/\/$/, "");
  const { email, expiry, token } = req.query || {};

  if (!email || !expiry || !token || !isValidEmail(String(email))) {
    res.status(400).send(resultPage("확인 실패", "잘못된 확인 링크입니다.", siteUrl));
    return;
  }

  const result = verifyConfirmToken(String(email), expiry, String(token));
  if (!result.ok) {
    const message =
      result.reason === "expired"
        ? "확인 링크가 만료됐습니다. 사이트에서 다시 구독을 신청해주세요."
        : "유효하지 않은 확인 링크입니다.";
    res.status(400).send(resultPage("확인 실패", message, siteUrl));
    return;
  }

  try {
    await markConfirmed(String(email));
  } catch (err) {
    res.status(502).send(resultPage("오류", "구독 확정 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.", siteUrl));
    return;
  }

  res
    .status(200)
    .send(resultPage("구독 확인 완료", "내일 아침 8시부터 AI 뉴스 브리핑을 이메일로 받아보실 수 있어요.", siteUrl));
};
