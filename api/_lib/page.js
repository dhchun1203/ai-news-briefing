// /api/confirm, /api/unsubscribe가 공유하는 아주 단순한 결과 안내 페이지.
function resultPage(title, message, siteUrl) {
  return `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${title} — AI 뉴스 브리핑</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans KR", sans-serif;
         max-width: 440px; margin: 96px auto; padding: 0 20px; text-align: center; color: #121212; }
  a { color: #a2201d; }
</style>
</head>
<body>
  <h1>${title}</h1>
  <p>${message}</p>
  <p><a href="${siteUrl}/index.html">브리핑으로 돌아가기</a></p>
</body>
</html>`;
}

module.exports = { resultPage };
