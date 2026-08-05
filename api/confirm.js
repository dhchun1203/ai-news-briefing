// GET ?email=&expiry=&token= -> 서명을 검증하고 통과하면 구독을 확정한다 (더블 옵트인 2단계).
//
// 구독취소(/api/unsubscribe)와 달리 여기는 GET에서 바로 처리한다. 메일 스캐너가 링크를
// 미리 열어 확정되더라도, 그건 **사용자가 직접 구독 폼에 주소를 넣어 시작한 절차**를
// 대신 마무리한 것이라 되돌리기 쉽고(하단 구독취소 링크) 피해가 없다. 반대로 구독취소는
// 사용자가 원하지 않은 상실이라 확인 절차를 둔다 — 그래서 둘을 다르게 다룬다.
const { isValidEmail, verifyConfirmToken } = require("./_lib/tokens");
const { markConfirmed, getSubscriber, touchConfirmSent } = require("./_lib/supabase");
const { resultPage, confirmExpiredPage } = require("./_lib/page");
const { sendConfirmEmail, withinConfirmCooldown, missingEnv } = require("./_lib/confirm-mail");

// Vercel은 Content-Type에 따라 req.body를 객체로 준다. 폼 전송(urlencoded)과 JSON을
// 모두 받아야 하므로 문자열로 오는 경우까지 방어한다.
function parseBody(body) {
  if (!body) return {};
  if (typeof body !== "string") return body;
  try {
    return JSON.parse(body);
  } catch (e) {
    return Object.fromEntries(new URLSearchParams(body));
  }
}

// 만료 페이지에서 "다시 받기"를 눌렀을 때. 여기까지 왔다는 건 서명이 유효한
// 링크를 들고 있다는 뜻이다.
async function handleResend(email, siteUrl, res) {
  if (missingEnv()) {
    console.error("confirm: resend requested but env vars missing");
    res.status(500).send(resultPage("오류", "서버 설정 오류로 재발송하지 못했습니다.", siteUrl));
    return;
  }

  let existing;
  try {
    existing = await getSubscriber(email);
  } catch (err) {
    console.error("confirm: database error on resend", err);
    res.status(502).send(resultPage("오류", "잠시 후 다시 시도해주세요.", siteUrl));
    return;
  }

  if (existing && existing.confirmed_at && !existing.unsubscribed_at) {
    res.status(200).send(resultPage("이미 확인됨", "이미 구독이 확정된 주소예요. 매일 아침 8시에 보내드립니다.", siteUrl));
    return;
  }

  // 구독 신청 기록이 없으면 보내지 않는다. 서명이 유효해도, 그 사이 해지했거나
  // 정리된 주소에 다시 메일을 보내는 건 원치 않는 발송이다.
  if (!existing || existing.unsubscribed_at) {
    res.status(200).send(resultPage("확인 메일 발송", "구독 신청 기록이 없어요. 사이트에서 다시 신청해주세요.", siteUrl));
    return;
  }

  // 쿨다운은 가입 경로와 똑같이 적용한다 — 이 버튼이 메일 폭탄 증폭기가 되면 안 된다.
  // 이미 방금 보냈으므로 사용자에게는 성공과 같은 화면을 보여준다.
  if (!withinConfirmCooldown(existing)) {
    if (!(await sendConfirmEmail(email)).ok) {
      res.status(502).send(resultPage("오류", "메일 발송에 실패했어요. 잠시 후 다시 시도해주세요.", siteUrl));
      return;
    }
    try {
      await touchConfirmSent(email);
    } catch (err) {
      // 메일은 이미 나갔다. 쿨다운 기록 실패는 로그만 남긴다.
      console.error("confirm: failed to record last_confirm_sent_at", err);
    }
  }

  res
    .status(200)
    .send(resultPage("확인 메일 발송", "새 확인 링크를 보내드렸어요. 메일함을 확인해주세요 (7일 이내 유효).", siteUrl));
}

module.exports = async function handler(req, res) {
  const siteUrl = (process.env.SITE_URL || "").replace(/\/$/, "");
  // 결과 페이지는 사용자별 상태를 담으므로 중간 캐시에 남으면 안 된다.
  res.setHeader("Cache-Control", "no-store");

  // POST는 만료 페이지의 "다시 받기" 버튼 전용이다 (아래 handleResend).
  if (req.method !== "GET" && req.method !== "POST") {
    res.status(405).send(resultPage("확인 실패", "지원하지 않는 요청입니다.", siteUrl));
    return;
  }

  if (!process.env.SUBSCRIBE_TOKEN_SECRET) {
    // 없으면 아래 verifyConfirmToken이 throw 해서 스택 트레이스가 그대로 500으로 나간다.
    console.error("confirm: SUBSCRIBE_TOKEN_SECRET not configured");
    res.status(500).send(resultPage("오류", "서버 설정 오류로 확인을 처리하지 못했습니다.", siteUrl));
    return;
  }

  const source = req.method === "POST" ? parseBody(req.body) : req.query || {};
  const { email, expiry, token } = source;

  if (!email || !expiry || !token || !isValidEmail(String(email))) {
    res.status(400).send(resultPage("확인 실패", "잘못된 확인 링크입니다.", siteUrl));
    return;
  }

  const result = verifyConfirmToken(String(email), expiry, String(token));

  // 서명이 아예 안 맞으면 위조다. 만료(reason === "expired")는 서명 검증을 통과한
  // 뒤에만 나오므로, 이 링크는 우리가 그 주소로 실제 발급한 것이 맞다 — 재발송을
  // 허용해도 새로 노출되는 정보가 없다(같은 주소로 한 번 더 보낼 뿐이다).
  if (!result.ok && result.reason !== "expired") {
    res.status(400).send(resultPage("확인 실패", "유효하지 않은 확인 링크입니다.", siteUrl));
    return;
  }

  if (!result.ok) {
    if (req.method === "POST") {
      await handleResend(String(email), siteUrl, res);
    } else {
      res.status(400).send(confirmExpiredPage(String(email), String(expiry), String(token), siteUrl));
    }
    return;
  }

  // 서명도 유효기간도 멀쩡한 링크를 POST로 다시 눌렀다면 그냥 확정해준다.

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
