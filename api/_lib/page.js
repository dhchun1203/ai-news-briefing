// /api/confirm, /api/unsubscribe가 공유하는 아주 단순한 결과 안내 페이지.

// 지금 호출부는 신뢰된 상수/환경변수만 넘기지만, 이 함수는 HTML을 문자열로 조립하는
// 자리라 한 번의 리팩터링이면 곧바로 XSS 싱크가 된다(예: 쿼리 파라미터를 메시지에
// 끼워 넣는 순간). 값이 들어오는 모든 구멍을 기본적으로 이스케이프해 둔다.
function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (c) => {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}

const STYLE = `
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans KR", sans-serif;
         max-width: 440px; margin: 96px auto; padding: 0 20px; text-align: center; color: #121212; }
  a { color: #a2201d; }
  button { font: inherit; font-weight: 700; color: #fff; background: #a2201d; border: 0;
           border-radius: 6px; padding: 12px 24px; cursor: pointer; }
  .muted { color: #666; font-size: 14px; }
`;

function layout(title, bodyHtml, siteUrl) {
  return `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex">
<title>${escapeHtml(title)} — AI 뉴스 브리핑</title>
<style>${STYLE}</style>
</head>
<body>
  <h1>${escapeHtml(title)}</h1>
  ${bodyHtml}
  <p><a href="${escapeHtml(siteUrl)}/index.html">브리핑으로 돌아가기</a></p>
</body>
</html>`;
}

function resultPage(title, message, siteUrl) {
  return layout(title, `<p>${escapeHtml(message)}</p>`, siteUrl);
}

// 구독취소 확인 페이지.
//
// 왜 링크를 누르자마자 취소하지 않는가: Outlook SafeLinks 같은 메일 보안 스캐너와
// 브라우저 프리페치는 메일 속 링크를 사용자 대신 **미리 열어본다**. 취소를 GET에서
// 처리하면 누르지도 않은 구독자가 조용히 해지된다(이 링크는 매일 모든 메일에 실린다).
// 그래서 GET은 이 확인 페이지만 보여주고, 실제 취소는 사람이 버튼을 눌러 보내는
// POST에서만 처리한다.
function unsubscribeConfirmPage(email, token, siteUrl) {
  const body = `
  <p>아래 주소의 구독을 취소하시겠어요?</p>
  <p><strong>${escapeHtml(email)}</strong></p>
  <form method="POST" action="/api/unsubscribe">
    <input type="hidden" name="email" value="${escapeHtml(email)}">
    <input type="hidden" name="token" value="${escapeHtml(token)}">
    <button type="submit">구독취소</button>
  </form>
  <p class="muted">버튼을 누르기 전까지는 취소되지 않습니다.</p>`;
  return layout("구독취소 확인", body, siteUrl);
}

// 확인 링크가 만료됐을 때 보여주는 페이지.
//
// 예전에는 "사이트에서 다시 구독을 신청해주세요"라는 안내문만 띄웠는데, 그건 막다른
// 길이었다 — 재신청 경로가 실제로 동작하긴 해도 거기까지 되돌아가는 사람은 드물다.
// 여기서 바로 새 링크를 받을 수 있게 한다.
//
// 왜 GET에서 자동 재발송하지 않고 버튼을 두는가: 구독취소와 같은 이유다. 메일 보안
// 스캐너와 브라우저 프리페치가 링크를 사용자 대신 미리 열어보기 때문에, GET에서
// 메일을 보내면 아무도 누르지 않았는데 메일이 나간다.
function confirmExpiredPage(email, expiry, token, siteUrl) {
  const body = `
  <p>확인 링크가 만료됐어요. 아래 버튼을 누르면 새 링크를 보내드립니다.</p>
  <p><strong>${escapeHtml(email)}</strong></p>
  <form method="POST" action="/api/confirm">
    <input type="hidden" name="email" value="${escapeHtml(email)}">
    <input type="hidden" name="expiry" value="${escapeHtml(expiry)}">
    <input type="hidden" name="token" value="${escapeHtml(token)}">
    <button type="submit">확인 메일 다시 받기</button>
  </form>`;
  return layout("확인 링크 만료", body, siteUrl);
}

module.exports = { resultPage, unsubscribeConfirmPage, confirmExpiredPage, escapeHtml };
