# 마케팅 전략 — SEO/GEO, 검색엔진 등록, 해외(영어권) 노출

이 문서는 코드로 이미 구현된 것(SEO/GEO 기술 인프라)과, 사람이 직접 계정으로 해야
하는 것(구글/네이버 등록), 그리고 실행 방법이 아직 구체화되지 않은 전략(영어권 커뮤니티
노출)을 한곳에 모아둔다. `PLAN.md`가 "이 기능을 왜 이렇게 만들었나"를 다루는 문서라면,
이 문서는 "독자를 어떻게 늘릴 것인가"를 다룬다.

## 1. GEO(생성형 AI 검색 최적화) 리서치 요약

**핵심 근거**: Princeton/Georgia Tech의 GEO 원 논문(arXiv 2311.09735, ACM SIGKDD
2024, GEO-bench로 약 1만 개 쿼리 테스트)에 따르면, **"권위 있는 인용과 구체적
통계"를 담은 콘텐츠가 AI 인용률을 22~41% 끌어올렸고, 키워드 반복이나 단순 문장
유창성은 인용률에 거의 기여하지 않았다.** 2026년 실무 가이드들이 공통으로 꼽는 추가
요소: 직접 답변 우선 구조, "[용어]는 [정의]다" 식 명확한 정의문, Q&A 형식, 신선도
(날짜) 신호, 실명/신뢰 저자 표시. 백링크·도메인 권위는 SEO와 GEO 양쪽 인용 확률에 다
기여한다(아래 4번 영어권 전략이 이 부분과 연결됨).

이 사이트가 이미 가진 강점: `daily_insight`(교차 종합), `implication_ko/en`("왜
중요한가"), `glossary`("[용어]는 [설명]" 형식)가 전부 GEO가 요구하는 방향과 일치한다.
이번에 추가로 적용한 것:
- `SKILL.md` 3단계에 GEO 작문 원칙 추가(요약 첫 문장은 결론부터, 수치는 뭉뚱그리지
  않기) — Claude가 매일 요약을 쓸 때마다 적용됨.
- **`llms.txt`는 이번에 추가하지 않았다** — 2026년 기준 공식 표준이 아니고, OpenAI/
  Google/Anthropic 등 어느 주요 업체도 프로덕션에서 읽는다고 확인된 바 없다. 비용이
  거의 없어 나중에 추가해도 되지만, 효과를 과대평가하면 안 된다는 게 리서치의
  결론이라 이번 우선순위에서는 뺐다.

## 2. SEO/GEO 기술 인프라 (이번에 구현 완료)

- **`docs/robots.txt`**: 전체 허용 + GPTBot/ClaudeBot/Google-Extended/PerplexityBot/
  CCBot/Bingbot 등 AI 크롤러 명시적 허용 + sitemap 위치. `scripts/generate_site.py`가
  매 실행마다 재생성.
- **`docs/sitemap.xml`**: 홈페이지 + 모든 `docs/archive/<날짜>.html` + 모든
  `docs/weekly/<주차>.html`을 매번 전체 재빌드(멱등적). 일요일 새로 생기는 주간 회고는
  `generate_weekly_site.py`가 자체적으로 한 번 더 sitemap을 재빌드해 당일 반영.
- **각 페이지 `<head>`**: canonical, `meta robots`, `og:url`/`og:image`(+width/height/
  alt), `twitter:image`(카드를 `summary_large_image`로), favicon(`favicon.svg`),
  JSON-LD 구조화 데이터.
- **JSON-LD 설계 원칙**: 이 사이트는 원문 기사의 저작자가 아니라 큐레이션/분석
  주체다. 그래서 홈/아카이브 페이지는 `CollectionPage`+`ItemList`로, 각 항목은 우리
  자체 요약을 `Article`로 표시하고 원문은 `citation`으로 분리했다(원문을 우리 것처럼
  `NewsArticle`로 마크업하면 저작권 오인 신호를 줄 수 있음). 주간 회고는 순수 우리
  원저작물이라 `Article`로 직접 마크업.
- **이미지 자산**: `templates/static/favicon.svg`(직접 작성), `templates/static/
  og-image.png`(범용 브랜드 카드, 헤드라인이 없는 날의 최종 대체용).
- **날짜별 동적 OG 이미지** (`scripts/og_image.py`): 그날 `daily_insight`의
  `headline_ko`를 1200×630 이미지에 직접 렌더링해 `docs/og/<날짜>.png`(주간 회고는
  `docs/og/<주차>.png`)로 저장하고, 그 페이지의 `og:image`가 이걸 가리키게 한다.
  링크를 카카오톡/트위터 등에 공유하면 미리보기 이미지만 보고도 그날 무슨 얘기인지
  알 수 있다. 한글 렌더링에는 저장소에 커밋해둔 정적 폰트
  (`templates/static/fonts/NotoSerifKR-Variable.ttf`, Google Fonts 배포본의 한국어
  서브셋 — CJK 통합 세트 대신 이걸 쓴 이유는 용량 때문, 전체 CJK 폰트는 56MB인 반면
  이건 23MB)를 쓴다. 헤드라인이 이미지 폭을 넘으면 실제 텍스트 너비를 측정해 자동
  줄바꿈하고, 3줄을 넘으면 말줄임(…)으로 자른다.
  - **안전장치**: 이 렌더링(Pillow, 폰트 로딩 등)이 무엇 때문이든 실패하면(Pillow
    미설치, 폰트 파일 손상 등) `seo_utils.build_og_image_url()`이 예외를 삼키고
    조용히 기존 정적 `og-image.png`로 대체한다 — 매일 자동 실행되는 파이프라인에서
    "미리보기 이미지 하나 못 만듦"이 "오늘자 사이트 생성 전체 실패"로 번지지
    않도록 하는 게 핵심 설계 원칙이다. 폰트 파일을 실제로 지워서 이 대체 동작을
    검증했다(정상 폴백 확인됨).
- 구현: `scripts/seo_utils.py`(신규 공용 모듈), `scripts/og_image.py`(동적 이미지
  렌더링, Pillow 의존), `scripts/generate_site.py`/`scripts/generate_weekly_site.py`
  에서 호출, `templates/site.html.j2`/`templates/weekly.html.j2` head 수정.

## 3. 구글/네이버 등록 체크리스트 (사람이 직접 — 계정 기반이라 대행 불가)

### 구글 Search Console
1. https://search.google.com/search-console 에서 **도메인 속성**으로
   `dailyaithread.com` 추가.
2. **DNS TXT 레코드 방식**으로 소유 확인 권장(코드 변경 전혀 불필요) — 가비아
   DNS 관리 화면에서 구글이 알려주는 `google-site-verification=...` TXT 레코드를
   도메인 apex에 추가. 이미 Vercel/Resend용 DNS 레코드를 가비아에서 관리 중이므로
   같은 화면에서 처리 가능.
   - HTML 메타태그 방식을 쓰고 싶다면 `config/site_verification.json`의
     `google_site_verification` 값을 채우면 자동으로 `<meta>` 태그가 나간다(재배포 필요).
3. 소유 확인 후 **Sitemaps** 메뉴에서 `sitemap.xml` 제출(`https://www.dailyaithread.com/sitemap.xml`).
4. 색인 반영까지 며칠~몇 주 걸릴 수 있음. **URL 검사** 도구로 개별 페이지 색인 요청도
   가능(신규 페이지 노출을 앞당기고 싶을 때).

### 네이버 서치어드바이저 (후순위)
1. https://searchadvisor.naver.com 에서 네이버 아이디로 로그인 후 사이트 등록.
2. **반드시 HTML 메타태그 방식을 쓴다** — `config/site_verification.json`의
   `naver_site_verification` 값을 채우고 재배포하면 자동으로 `<meta>` 태그가 나간다.
   **HTML 파일 업로드 방식은 이 프로젝트에서 쓸 수 없다**: `vercel.json`의
   `cleanUrls: true`가 `/navera....html` 요청을 확장자 없는 `/navera...`로 308
   리다이렉트시켜, 네이버가 기대하는 정확한 `.html` 경로에서 파일을 찾지 못한다
   (2026-07-24 직접 시도해서 확인됨 — 파일을 올려도 소유확인이 실패한다).
3. 소유 확인 후 `sitemap.xml` 제출(구글과 같은 파일 재사용).
4. 네이버 검색 로봇이 실제로 수집하는 데 14~16일 정도 걸린다고 알려져 있음. HTML
   태그 인증은 1년마다 재인증 필요.
5. 우선순위는 구글보다 낮게 — 이 항목은 시간 날 때 처리.

## 4. 해외(영어권) 시장 노출 전략

### 포지셔닝
뉴스레터 피로도는 실재하는 문제다(평균 25개 이상 구독, 41%가 피로 호소, 매일 100통
넘는 이메일). "또 하나의 AI 뉴스 모음"으로는 승산이 없고, **이미 만들어져 있는
차별점을 앞세워야 한다**: 일별 교차 종합 인사이트(`daily_insight`), 클릭식 용어 설명
패널, 주간 회고, 출처 타입 배지(공식 발표/보도/커뮤니티 구분). 경쟁 구도 참고:

| 경쟁자 | 구독자 규모 | 포지셔닝 |
|---|---|---|
| TLDR AI | ~110만 | 감정 없는 불릿 요약, 개발자/ML 종사자용 |
| The Rundown AI | ~200만 | 최대 규모, 제품 출시 위주 |
| The Neuron | - | "똑똑한 친구가 설명해주는" 톤, 왜 중요한지 분석 — 이 프로젝트의 `implication`과 가장 유사 |
| Superhuman AI | - | 실무자용 워크플로/프롬프트 중심 |
| Ben's Bites | - | 스타트업/투자 앵글 |

### 채널 전략 (TLDR 자체 성장 사례 — 0→13만 구독/20개월 — 의 무료 버전)
1. **Product Hunt 런칭**: 화/수요일 게시 권장, 24시간 노출.
2. **Hacker News "Show HN"** (PH 2~4일 뒤): "원문을 직접 읽고, 여러 출처의 같은
   사건을 교차 감지하고, 용어를 설명하는 파이프라인을 만들었다"는 진솔한 빌드
   스토리로 — HN은 마케팅 카피보다 기술적 진정성에 반응한다.
3. **Indie Hackers**: 빌드-인-퍼블릭 서사에 우호적.
4. **Reddit**: r/artificial, r/singularity, r/OpenAI, r/LocalLLaMA 등. **주의: 셀프
   홍보 링크는 대부분 서브 규칙 위반으로 삭제된다.** 각 서브의 규칙을 먼저 읽고, 진짜
   커뮤니티 구성원으로 참여하다가 self-promo 허용 스레드(있는 경우)에서만 "내가 만든
   것, 피드백 원함" 톤으로 공유.
5. 소규모 구독자 확보 후 비슷한 규모의 뉴스레터와 **상호 홍보(cross-promotion)** —
   TLDR도 성장 후반부에 이 방식을 크게 활용했다.

### 실행 주체
이 전략 전체는 **자동화 대상이 아니라 사용자가 직접 실행하는 항목**이다(이전에 기록해둔
"주간 회고 SNS 홍보"와 같은 성격 — `PLAN.md` §14 참고). 계정 생성, 실제 게시,
커뮤니티 규칙 확인은 전부 사람이 해야 한다 — 아래는 그대로 붙여넣어 쓸 수 있는 초안이다.

## 5. 런칭 카피 초안 (그대로 사용 가능)

### Product Hunt
- **제품명**: Daily AI Thread
- **태그라인**(60자 내외): `AI news that reads the full article, not just the headline`
- **설명**(제품 소개란):
  > Every morning, Daily AI Thread reads the full text of the day's top AI
  > articles (not just RSS snippets), flags when multiple outlets are covering
  > the same story, and writes a daily synthesis of what it all means — with
  > inline plain-English explanations for any jargon. Free, bilingual (EN/KO),
  > no signup required to read.
- **메이커 첫 댓글**(등록 직후 본인 계정으로 다는 소개 댓글 — PH 관례):
  > Hey PH! I built this because most AI newsletters just paste RSS headlines
  > with zero synthesis. Daily AI Thread actually reads each day's top
  > articles in full, notices when multiple outlets are covering the same
  > event (a real significance signal), and writes a "why this matters"
  > analysis across all of it — not just per-article blurbs. Click any
  > unfamiliar term (RAG, MoE, zero-day, etc.) for a plain-English explanation
  > without leaving the page. Runs automatically every morning, free, no
  > login wall. Would love feedback — especially on what you wish AI news
  > coverage did differently.

### Hacker News — Show HN
- **제목**: `Show HN: A pipeline that reads AI news in full and explains why it matters`
- **본문**:
  > Most AI newsletters just paste RSS summaries. I wanted something that
  > actually reads each article, notices when multiple outlets are covering
  > the same event (a signal RSS timestamps alone don't give you), and
  > explains the "so what" — not just the "what happened."
  >
  > How it works: a daily pipeline pulls candidates from ~11 RSS feeds,
  > excludes anything already covered on a previous day, and ranks candidates
  > partly by how many independent sources are covering the same story
  > (keyword clustering on headlines). The top 10 get their full text read,
  > summarized, and analyzed for implications. Once a week it also
  > synthesizes that week's throughlines into a recap.
  >
  > One thing I'm fairly happy with: any jargon term becomes a clickable
  > inline explainer, written the same day, so non-experts don't get lost.
  >
  > Static site (Python + Jinja2) on Vercel; the daily reading/writing step
  > runs on Claude. Bilingual (EN/KO).
  >
  > https://www.dailyaithread.com — happy to answer questions about the
  > pipeline.

### Reddit (self-promo 허용 스레드에서만 사용)
> Built Daily AI Thread — reads AI news in full, flags multi-outlet coverage
> as a significance signal, and explains jargon inline. Free, bilingual,
> no login. Feedback welcome: dailyaithread.com

## 6. 다음에 할 만한 것 (지금은 범위 밖)

- `llms.txt` — 표준화되면 재검토.
- 영어권 전용 착지 페이지(현재는 같은 페이지에서 언어 토글만 지원) — 필요성이 확인되면
  검토.
