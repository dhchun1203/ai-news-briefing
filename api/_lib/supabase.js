// Supabase REST(PostgREST)를 SDK 없이 fetch로 직접 호출하는 얇은 헬퍼.
// service_role 키를 쓰므로 RLS를 우회한다 — 이 파일은 서버(Vercel Function)에서만 호출한다.
function config() {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) throw new Error("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not configured");
  return { url: url.replace(/\/$/, ""), key };
}

function headers(extra) {
  const { key } = config();
  return {
    apikey: key,
    Authorization: `Bearer ${key}`,
    "Content-Type": "application/json",
    ...extra,
  };
}

// 에러 본문에는 Supabase 호스트·테이블·컬럼명이 담긴다. 이 Error는 서버 로그용이며,
// 절대 그대로 HTTP 응답에 실어 보내지 않는다(호출부에서 일반화된 메시지만 반환한다).
async function assertOk(res, label) {
  if (!res.ok) {
    throw new Error(`supabase ${label} failed: ${res.status} ${await res.text()}`);
  }
}

// 이미 존재하는 이메일이면 조용히 무시하고(ignore-duplicates), 없으면 새로 만든다.
async function upsertPendingSubscriber(email) {
  const { url } = config();
  const res = await fetch(`${url}/rest/v1/subscribers?on_conflict=email`, {
    method: "POST",
    headers: headers({ Prefer: "resolution=ignore-duplicates,return=minimal" }),
    body: JSON.stringify([{ email }]),
  });
  await assertOk(res, "insert");
}

// 구독 신청 처리에 필요한 필드만 조회한다. 없으면 null.
async function getSubscriber(email) {
  const { url } = config();
  const res = await fetch(
    `${url}/rest/v1/subscribers?email=eq.${encodeURIComponent(email)}` +
      `&select=email,confirmed_at,unsubscribed_at,last_confirm_sent_at`,
    { headers: headers() }
  );
  await assertOk(res, "select");
  const rows = await res.json();
  return Array.isArray(rows) && rows.length ? rows[0] : null;
}

// markConfirmed/markUnsubscribed/touchConfirmSent가 전부 같은 PATCH라 하나로 합쳤다.
async function patchSubscriber(email, patch, label) {
  const { url } = config();
  const res = await fetch(`${url}/rest/v1/subscribers?email=eq.${encodeURIComponent(email)}`, {
    method: "PATCH",
    headers: headers({ Prefer: "return=minimal" }),
    body: JSON.stringify(patch),
  });
  await assertOk(res, label);
}

// 확인 메일을 실제로 보낸 직후에만 호출한다 — 이 타임스탬프가 쿨다운의 기준점이다.
function touchConfirmSent(email) {
  return patchSubscriber(email, { last_confirm_sent_at: new Date().toISOString() }, "touch-confirm-sent");
}

// 구독 확정. 예전에 취소했던 사람이 다시 확인하면 취소 상태를 해제한다.
function markConfirmed(email) {
  return patchSubscriber(email, { confirmed_at: new Date().toISOString(), unsubscribed_at: null }, "confirm");
}

function markUnsubscribed(email) {
  return patchSubscriber(email, { unsubscribed_at: new Date().toISOString() }, "unsubscribe");
}

module.exports = {
  upsertPendingSubscriber,
  getSubscriber,
  touchConfirmSent,
  markConfirmed,
  markUnsubscribed,
};
