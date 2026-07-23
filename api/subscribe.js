// POST { email } -> Supabase에 대기 상태로 기록하고, 확인 링크가 담긴 이메일을 보낸다.
// 실제 발송 목록에 들어가는 시점은 /api/confirm에서 링크를 클릭한 이후다 (더블 옵트인).
const { isValidEmail, makeConfirmToken } = require("./_lib/tokens");
const { upsertPendingSubscriber } = require("./_lib/supabase");

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
  if (!siteUrl || !sender || !apiKey) {
    res.status(500).json({ error: "server_not_configured" });
    return;
  }

  try {
    await upsertPendingSubscriber(email);
  } catch (err) {
    res.status(502).json({ error: "database_error", detail: String(err) });
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
      const detail = await emailRes.text();
      res.status(502).json({ error: "email_send_failed", detail });
      return;
    }
  } catch (err) {
    res.status(502).json({ error: "email_send_failed", detail: String(err) });
    return;
  }

  res.status(200).json({ ok: true });
};
