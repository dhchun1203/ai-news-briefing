// 구독취소. 만료 없이 영구히 유효한 서명 링크라 매일 발송되는 이메일 하단에 계속 실린다.
//
// GET  ?email=&token=  -> 확인 페이지만 보여준다 (아무것도 바꾸지 않음)
// POST  email, token   -> 실제로 구독을 취소한다
//
// 왜 나눴는가: Outlook SafeLinks 같은 메일 보안 스캐너와 브라우저 프리페치는 메일 속
// 링크를 사용자 대신 미리 열어본다. 취소를 GET에서 처리하면 누르지도 않은 구독자가
// 조용히 해지된다 — 매일 모든 메일에 실리는 링크라 피해가 계속 쌓인다.
const { isValidEmail, verifyUnsubscribeToken } = require("./_lib/tokens");
const { markUnsubscribed } = require("./_lib/supabase");
const { resultPage, unsubscribeConfirmPage } = require("./_lib/page");
const { normalizeLang } = require("./_lib/messages");

function readParams(req) {
  if (req.method === "POST") {
    let body = req.body;
    if (typeof body === "string") {
      try {
        body = JSON.parse(body);
      } catch (e) {
        // Vercel이 파싱하지 않은 폼 전송(application/x-www-form-urlencoded)일 수 있다.
        body = Object.fromEntries(new URLSearchParams(String(req.body)));
      }
    }
    return body || {};
  }
  return req.query || {};
}

module.exports = async function handler(req, res) {
  const siteUrl = (process.env.SITE_URL || "").replace(/\/$/, "");
  // 결과 페이지는 사용자별 상태를 담으므로 중간 캐시에 남으면 안 된다.
  res.setHeader("Cache-Control", "no-store");

  // 구독취소 링크는 매일 발송되는 메일 하단에 실린다. 그 메일을 만들 때
  // 구독자의 언어를 붙여 보내므로, 여기서 그대로 읽어 페이지 언어를 맞춘다.
  const lang = normalizeLang(readParams(req).lang);

  if (req.method !== "GET" && req.method !== "POST") {
    res.status(405).send(resultPage(lang, "method_not_allowed", siteUrl));
    return;
  }

  const { email, token } = readParams(req);
  const emailStr = String(email || "");
  const tokenStr = String(token || "");

  if (!email || !token || !isValidEmail(emailStr) || !verifyUnsubscribeToken(emailStr, tokenStr)) {
    res.status(400).send(resultPage(lang, "unsub_invalid", siteUrl));
    return;
  }

  // GET은 확인만 받고 끝낸다 — 여기서 DB를 바꾸면 스캐너가 대신 눌러버린다.
  if (req.method === "GET") {
    res.status(200).send(unsubscribeConfirmPage(emailStr, tokenStr, siteUrl, lang));
    return;
  }

  try {
    await markUnsubscribed(emailStr);
  } catch (err) {
    console.error("unsubscribe: database error", err);
    res.status(502).send(resultPage(lang, "db_error", siteUrl));
    return;
  }

  res.status(200).send(resultPage(lang, "unsub_ok", siteUrl));
};
