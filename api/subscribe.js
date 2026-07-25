// POST { email } -> Supabase에 대기 상태로 기록하고, 확인 링크가 담긴 이메일을 보낸다.
// 실제 발송 목록에 들어가는 시점은 /api/confirm에서 링크를 클릭한 이후다 (더블 옵트인).
const { isValidEmail, makeConfirmToken } = require("./_lib/tokens");
const {
  upsertPendingSubscriber,
  getSubscriber,
  touchConfirmSent,
} = require("./_lib/supabase");

// 같은 주소로 확인 메일을 다시 보내기까지 기다려야 하는 시간.
// 이게 없으면 인증 없는 이 엔드포인트가 곧 메일 폭탄 증폭기가 된다 — 공격자가 남의
// 주소로 확인 메일을 무제한 발사해 수신자를 괴롭히고, 발신 도메인 평판과 Resend
// 요금까지 끌어다 쓴다.
const CONFIRM_COOLDOWN_MS = 10 * 60 * 1000;

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

  if (!isValidEmail(email)) {
    res.status(400).json({ error: "invalid_email" });
    return;
  }

  const siteUrl = (process.env.SITE_URL || "").replace(/\/$/, "");
  const sender = process.env.RESEND_SENDER_EMAIL;
  const apiKey = process.env.RESEND_API_KEY;
  // SUBSCRIBE_TOKEN_SECRET도 여기서 함께 확인한다. 빠져 있으면 아래 makeConfirmToken이
  // try/catch 밖에서 throw 하는데, 그 시점엔 이미 행을 INSERT 한 뒤라 "DB에는 남았지만
  // 메일은 못 갔고 응답은 스택 트레이스"인 상태가 된다(게다가 재시도해도
  // ignore-duplicates 때문에 조용히 무시된다).
  if (!siteUrl || !sender || !apiKey || !process.env.SUBSCRIBE_TOKEN_SECRET) {
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
      await upsertPendingSubscriber(email);
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
  const lastSent = existing && existing.last_confirm_sent_at ? Date.parse(existing.last_confirm_sent_at) : NaN;
  const withinCooldown = Number.isFinite(lastSent) && Date.now() - lastSent < CONFIRM_COOLDOWN_MS;
  if (confirmedAlready || withinCooldown) {
    res.status(200).json({ ok: true });
    return;
  }

  const { token, expiry } = makeConfirmToken(email);
  const confirmUrl = `${siteUrl}/api/confirm?email=${encodeURIComponent(email)}&expiry=${expiry}&token=${token}`;

  try {
    const emailRes = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from: sender,
        to: email,
        subject: "AI 뉴스 브리핑 구독을 확인해주세요",
        html: `
          <p>AI 뉴스 브리핑 구독 신청을 확인하려면 아래 링크를 눌러주세요 (24시간 이내 유효).</p>
          <p><a href="${confirmUrl}">구독 확인하기</a></p>
          <p style="color:#888;font-size:12px;">본인이 신청하지 않았다면 이 메일은 무시하셔도 됩니다.</p>
        `,
      }),
    });
    if (!emailRes.ok) {
      console.error("subscribe: resend send failed", emailRes.status, await emailRes.text());
      res.status(502).json({ error: "email_send_failed" });
      return;
    }
  } catch (err) {
    console.error("subscribe: resend request error", err);
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
