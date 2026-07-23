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

// 이미 존재하는 이메일이면 조용히 무시하고(ignore-duplicates), 없으면 새로 만든다.
async function upsertPendingSubscriber(email) {
  const { url } = config();
  const res = await fetch(`${url}/rest/v1/subscribers?on_conflict=email`, {
    method: "POST",
    headers: headers({ Prefer: "resolution=ignore-duplicates,return=minimal" }),
    body: JSON.stringify([{ email }]),
  });
  if (!res.ok) {
    throw new Error(`supabase insert failed: ${res.status} ${await res.text()}`);
  }
}

async function markConfirmed(email) {
  const { url } = config();
  const res = await fetch(`${url}/rest/v1/subscribers?email=eq.${encodeURIComponent(email)}`, {
    method: "PATCH",
    headers: headers({ Prefer: "return=minimal" }),
    body: JSON.stringify({ confirmed_at: new Date().toISOString(), unsubscribed_at: null }),
  });
  if (!res.ok) {
    throw new Error(`supabase confirm update failed: ${res.status} ${await res.text()}`);
  }
}

async function markUnsubscribed(email) {
  const { url } = config();
  const res = await fetch(`${url}/rest/v1/subscribers?email=eq.${encodeURIComponent(email)}`, {
    method: "PATCH",
    headers: headers({ Prefer: "return=minimal" }),
    body: JSON.stringify({ unsubscribed_at: new Date().toISOString() }),
  });
  if (!res.ok) {
    throw new Error(`supabase unsubscribe update failed: ${res.status} ${await res.text()}`);
  }
}

module.exports = { upsertPendingSubscriber, markConfirmed, markUnsubscribed };
