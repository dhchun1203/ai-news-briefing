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
async function upsertPendingSubscriber(email, timezone, lang) {
  const { url } = config();
  // timezone은 선택 필드다. 값이 없거나 형식이 이상하면 그냥 빼고 넣는다 —
  // 기록용 부가 정보 때문에 구독 자체가 실패하면 안 된다.
  // lang은 다르다 — 이 값이 앞으로 그 사람이 받을 모든 메일의 언어를 정하므로
  // 반드시 넣는다(호출부가 이미 'ko'/'en'으로 정규화해 넘긴다).
  const row = timezone ? { email, timezone, lang } : { email, lang };
  const res = await fetch(`${url}/rest/v1/subscribers?on_conflict=email`, {
    method: "POST",
    headers: headers({ Prefer: "resolution=ignore-duplicates,return=minimal" }),
    body: JSON.stringify([row]),
  });
  await assertOk(res, "insert");
}

// 구독 신청 처리에 필요한 필드만 조회한다. 없으면 null.
async function getSubscriber(email) {
  const { url } = config();
  const res = await fetch(
    `${url}/rest/v1/subscribers?email=eq.${encodeURIComponent(email)}` +
      `&select=email,confirmed_at,unsubscribed_at,last_confirm_sent_at,lang`,
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

// 아카이브 전문 검색. PostgREST 필터(?col=ilike.*값*)가 아니라 RPC로 호출한다 —
// 질의어가 URL 필터 문법이 아니라 JSON 본문의 함수 인자로 전달되므로, 사용자 입력이
// 필터 문법(*, 쉼표, 괄호)으로 해석될 여지가 없다. LIKE 와일드카드 무력화는
// search_archive 함수 안에서 처리한다(supabase/schema.sql 참고).
async function searchArchive(q, limit) {
  const { url } = config();
  const res = await fetch(`${url}/rest/v1/rpc/search_archive`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ q, max_results: limit }),
  });
  await assertOk(res, "search");
  const rows = await res.json();
  return Array.isArray(rows) ? rows : [];
}

module.exports = {
  upsertPendingSubscriber,
  getSubscriber,
  touchConfirmSent,
  markConfirmed,
  markUnsubscribed,
  searchArchive,
};
