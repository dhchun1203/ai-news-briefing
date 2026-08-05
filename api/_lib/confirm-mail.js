// 구독 확인 메일 발송 — /api/subscribe(최초 가입)와 /api/confirm(만료 후 재발송)이 공유한다.
//
// 왜 공유 모듈인가: 두 곳이 각자 Resend를 호출하면 본문 문구와 토큰 수명이 조용히
// 갈라진다. 특히 토큰 수명은 만료 안내 페이지의 문구("7일 이내")와 반드시 맞아야 하는데,
// 값이 두 군데 흩어져 있으면 한쪽만 고치고 끝난다.
const { makeConfirmToken, CONFIRM_TTL_SECONDS } = require("./tokens");

// 같은 주소로 확인 메일을 다시 보내기까지 기다려야 하는 시간.
// 이게 없으면 인증 없는 이 경로가 곧 메일 폭탄 증폭기가 된다 — 공격자가 남의
// 주소로 확인 메일을 무제한 발사해 수신자를 괴롭히고, 발신 도메인 평판과 Resend
// 요금까지 끌어다 쓴다. 재발송 경로에도 똑같이 적용된다.
const CONFIRM_COOLDOWN_MS = 10 * 60 * 1000;

function missingEnv() {
  return (
    !process.env.SITE_URL ||
    !process.env.RESEND_SENDER_EMAIL ||
    !process.env.RESEND_API_KEY ||
    !process.env.SUBSCRIBE_TOKEN_SECRET
  );
}

// 쿨다운 중인지 판단한다. last_confirm_sent_at이 없거나 파싱이 안 되면 "아직 안 보냈다"로
// 본다 — 못 읽는 값 때문에 사용자를 영원히 막아두는 쪽보다 한 번 더 보내는 쪽이 낫다.
function withinConfirmCooldown(subscriber) {
  const lastSent =
    subscriber && subscriber.last_confirm_sent_at ? Date.parse(subscriber.last_confirm_sent_at) : NaN;
  return Number.isFinite(lastSent) && Date.now() - lastSent < CONFIRM_COOLDOWN_MS;
}

// 성공하면 { ok: true }, 실패하면 { ok: false }를 돌려준다. 호출부가 응답 형식을
// 정하므로(JSON / HTML) 여기서는 res를 건드리지 않는다.
async function sendConfirmEmail(email) {
  const siteUrl = (process.env.SITE_URL || "").replace(/\/$/, "");
  const { token, expiry } = makeConfirmToken(email);
  const confirmUrl = `${siteUrl}/api/confirm?email=${encodeURIComponent(email)}&expiry=${expiry}&token=${token}`;

  try {
    const emailRes = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${process.env.RESEND_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from: process.env.RESEND_SENDER_EMAIL,
        // 수신자는 언제나 이 한 주소뿐이다. 배열이나 bcc를 쓰지 않는다 —
        // 확인 메일이 여러 명에게 나갈 수 있는 형태가 되면 사고가 조용히 커진다.
        to: email,
        subject: "AI 뉴스 브리핑 구독을 확인해주세요",
        html: `
          <p>AI 뉴스 브리핑 구독 신청을 확인하려면 아래 링크를 눌러주세요 (7일 이내 유효).</p>
          <p><a href="${confirmUrl}">구독 확인하기</a></p>
          <p style="color:#888;font-size:12px;">본인이 신청하지 않았다면 이 메일은 무시하셔도 됩니다.</p>
        `,
      }),
    });
    if (!emailRes.ok) {
      console.error("confirm-mail: resend send failed", emailRes.status, await emailRes.text());
      return { ok: false };
    }
  } catch (err) {
    console.error("confirm-mail: resend request error", err);
    return { ok: false };
  }
  return { ok: true };
}

module.exports = {
  sendConfirmEmail,
  withinConfirmCooldown,
  missingEnv,
  CONFIRM_COOLDOWN_MS,
  CONFIRM_TTL_SECONDS,
};
