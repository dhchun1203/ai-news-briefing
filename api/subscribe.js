// POST { email } -> Supabase에 대기 상태로 기록하고, 확인 링크가 담긴 이메일을 보낸다.
// 실제 발송 목록에 들어가는 시점은 /api/confirm에서 링크를 클릭한 이후다 (더블 옵트인).
const { isValidEmail } = require("./_lib/tokens");
const {
  upsertPendingSubscriber,
  getSubscriber,
  touchConfirmSent,
} = require("./_lib/supabase");
// 발송 본문·토큰 수명·쿨다운은 /api/confirm의 재발송 경로와 공유한다.
const { sendConfirmEmail, withinConfirmCooldown, missingEnv } = require("./_lib/confirm-mail");

module.exports = async function handler(req, res) {
  if (req.method !== "POST") {
    res.status(405).json({ error: "method_not_allowed" });
    return;
  }

  let body = req.body;
  if (typeof body === "string") {
    try {
      body = JSON.parse(body);
    } catch (e) {
      body = {};
    }
  }
  const email = String((body && body.email) || "")
    .trim()
    .toLowerCase();

  // 구독 시점 브라우저 시간대(선택). 지금은 기록만 하고 발송에는 쓰지 않는다.
  // 클라이언트가 보내는 값이므로 그대로 믿지 않고 IANA 이름 형태만 통과시킨다
  // ("Asia/Seoul", "America/Indiana/Indianapolis", "UTC"). 형식이 아니면 버리고
  // 구독은 그대로 진행한다 — 부가 정보 때문에 구독이 막히면 안 된다.
  const rawTz = String((body && body.timezone) || "").trim();
  const timezone =
    rawTz.length > 0 && rawTz.length <= 64 && /^[A-Za-z][A-Za-z0-9_+-]*(\/[A-Za-z0-9_+-]+)*$/.test(rawTz)
      ? rawTz
      : null;

  if (!isValidEmail(email)) {
    res.status(400).json({ error: "invalid_email" });
    return;
  }

  // SUBSCRIBE_TOKEN_SECRET도 여기서 함께 확인한다. 빠져 있으면 토큰 생성이 throw 하는데,
  // 그 시점엔 이미 행을 INSERT 한 뒤라 "DB에는 남았지만 메일은 못 갔고 응답은 스택
  // 트레이스"인 상태가 된다(게다가 재시도해도 ignore-duplicates 때문에 조용히 무시된다).
  if (missingEnv()) {
    console.error("subscribe: missing required env vars");
    res.status(500).json({ error: "server_not_configured" });
    return;
  }

  // 아래 실패 응답들은 의도적으로 내부 정보를 담지 않는다 — Supabase 에러 문자열에는
  // 호스트·테이블·컬럼명이 들어 있어 그대로 내보내면 구조가 노출된다. 상세 내용은
  // 서버 로그에만 남긴다.
  let existing;
  try {
    existing = await getSubscriber(email);
    if (!existing) {
      await upsertPendingSubscriber(email, timezone);
    }
  } catch (err) {
    console.error("subscribe: database error", err);
    res.status(502).json({ error: "database_error" });
    return;
  }

  // 이미 확정된 구독자이거나, 방금 확인 메일을 보낸 주소면 메일을 다시 보내지 않는다.
  // 응답은 성공과 똑같이 돌려준다 — 여기서 "이미 구독 중"과 "처음 보는 주소"를
  // 구분해주면 임의의 주소가 이 목록에 있는지 캐낼 수 있는 조회 창구가 된다.
  const confirmedAlready = Boolean(existing && existing.confirmed_at && !existing.unsubscribed_at);
  if (confirmedAlready || withinConfirmCooldown(existing)) {
    res.status(200).json({ ok: true });
    return;
  }

  if (!(await sendConfirmEmail(email)).ok) {
    res.status(502).json({ error: "email_send_failed" });
    return;
  }

  // 메일이 실제로 나간 뒤에만 쿨다운 시계를 돌린다. 발송에 실패했는데 시계를 돌리면
  // 사용자가 10분 동안 재시도해도 아무 메일도 못 받는 상태에 갇힌다.
  try {
    await touchConfirmSent(email);
  } catch (err) {
    // 메일은 이미 나갔으므로 사용자에겐 성공이다. 쿨다운 기록 실패는 로그만 남긴다.
    console.error("subscribe: failed to record last_confirm_sent_at", err);
  }

  res.status(200).json({ ok: true });
};
