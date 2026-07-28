// 아카이브 검색. GET /api/search?q=질의어 -> JSON 배열
//
// 원래는 브라우저가 docs/search-index.json을 통째로 내려받아 클라이언트에서 훑었다.
// 그 파일은 하루 약 12KB씩 자라 180일 상한에서 2.2MB가 되고, 그 상한 때문에 180일
// 이전 기사는 아카이브에 남아 있는데도 검색되지 않았다. 검색을 서버로 옮겨 두 문제를
// 함께 없앤다(다운로드 0, 기간 제한 없음).
//
// 정적 페이지는 그대로 둔다 — 이 엔드포인트가 죽어도 site.js가 정적 인덱스로
// 폴백하므로 검색이 통째로 멈추지는 않는다.
const { searchArchive } = require("./_lib/supabase");

// 질의어 길이 상한. 검색은 인증 없이 누구나 호출할 수 있고 매 호출이 DB를 때리므로,
// 긴 문자열로 트라이그램 매칭을 무겁게 만드는 걸 입구에서 막는다.
const MAX_QUERY_LENGTH = 100;
const DEFAULT_LIMIT = 20;
const MAX_LIMIT = 50;

module.exports = async function handler(req, res) {
  if (req.method !== "GET") {
    res.setHeader("Allow", "GET");
    res.status(405).json({ error: "method_not_allowed" });
    return;
  }

  const q = String((req.query && req.query.q) || "").trim();
  if (!q) {
    // 빈 질의는 정상 상태다(입력을 지운 경우) — 에러가 아니라 빈 결과로 답한다.
    res.setHeader("Cache-Control", "no-store");
    res.status(200).json({ results: [] });
    return;
  }
  if (q.length > MAX_QUERY_LENGTH) {
    res.status(400).json({ error: "query_too_long" });
    return;
  }

  let limit = parseInt(String((req.query && req.query.limit) || ""), 10);
  if (!Number.isFinite(limit) || limit < 1) limit = DEFAULT_LIMIT;
  if (limit > MAX_LIMIT) limit = MAX_LIMIT;

  try {
    const rows = await searchArchive(q, limit);
    // 같은 질의어는 짧게 캐시해도 안전하다(아카이브는 하루 한 번만 바뀐다).
    // 사용자별 상태가 전혀 없는 공개 데이터라 공유 캐시에 담겨도 문제없다.
    res.setHeader("Cache-Control", "public, max-age=60, s-maxage=300");
    res.status(200).json({ results: rows });
  } catch (err) {
    // 에러 본문에는 Supabase 호스트·테이블명이 들어 있다. 로그에만 남기고
    // 응답에는 일반화된 코드만 보낸다(다른 엔드포인트와 같은 원칙).
    console.error("search: database error", err);
    res.status(502).json({ error: "search_unavailable" });
  }
};
