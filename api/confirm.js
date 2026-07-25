// GET ?email=&expiry=&token= -> 서명을 검증하고 통과하면 구독을 확정한다 (더블 옵트인 2단계).
//
// 구독취소(/api/unsubscribe)와 달리 여기는 GET에서 바로 처리한다. 메일 스캐너가 링크를
// 미리 열어 확정되더라도, 그건 **사용자가 직접 구독 폼에 주소를 넣어 시작한 절차**를
// 대신 마무리한 것이라 되돌리기 쉽고(하단 구독취소 링크) 피해가 없다. 반대로 구독취소는
// 사용자가 원하지 않은 상실이라 확인 절차를 둔다 — 그래서 둘을 다르게 다룬다.
const { isValidEmail, verifyConfirmToken } = require("./_lib/tokens");
const { markConfirmed } = require("./_lib/supabase");
const { resultPage } = require("./_lib/page");

module.exports = async function handler(req, res) {
  const siteUrl = (process.env.SITE_URL || "").replace(/\/$/, "");
  // 결과 페이지는 사용자별 상태를 담으므로 중간 캐시에 남으면 안 된다.
  res.setHeader("Cache-Control", "no-store");

  if (req.method !== "GET") {
    res.status(405).send(resultPage("확인 실패", "지원하지 않는 요청입니다.", siteUrl));
    return;
  }

  if (!process.env.SUBSCRIBE_TOKEN_SECRET) {
    // 없으면 아래 verifyConfirmToken이 throw 해서 스택 트레이스가 그대로 500으로 나간다.
    console.error("confirm: SUBSCRIBE_TOKEN_SECRET not configured");
    res.status(500).send(resultPage("오류", "서버 설정 오류로 확인을 처리하지 못했습니다.", siteUrl));
    return;
  }

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
    console.error("confirm: database error", err);
    res.status(502).send(resultPage("오류", "구독 확정 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.", siteUrl));
    return;
  }

  res
    .status(200)
    .send(resultPage("구독 확인 완료", "내일 아침 8시부터 AI 뉴스 브리핑을 이메일로 받아보실 수 있어요.", siteUrl));
};
