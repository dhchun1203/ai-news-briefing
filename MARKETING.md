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
- **`docs/glossary.html`(AI 용어사전)**: 매일 이미 작성하던 glossary 설명을 버리지
  않고 영구 집계해 만든 별도 페이지. "[용어]는 [정의]다" 구조가 GEO에서 가장 확실히
  효과가 있다고 확인된 형식 그 자체라, 콘텐츠를 새로 쓰지 않고도(3단계에서 이미
  Claude가 쓰는 설명 재활용) GEO 자산을 하나 더 얻은 셈이다. `schema.org`의
  `DefinedTermSet`/`DefinedTerm`으로 마크업했다(일반 `Article`보다 정의문 콘텐츠에
  더 정확히 맞는 타입).

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

> **2026-07-30 전부 완료.** 아래 절차는 기록용으로 남긴다.
>
> | | 소유 확인 | sitemap | 그 외 |
> |---|---|---|---|
> | 구글 | DNS TXT (도메인 속성) | ✅ 116개 | — |
> | Bing | GSC 임포트 | ✅ 116개 | IndexNow 자동 통보 |
> | 네이버 | 메타태그 (`config/site_verification.json`) | ✅ | RSS·웹페이지 수집·robots 검증 |
>
> 겪은 함정 두 가지:
> - **Bing은 apex(`dailyaithread.com`)로 등록됐다.** GSC 도메인 속성을 임포트하면
>   www가 아니라 apex가 들어온다. URL 검사 화면은 apex로 정규화해 "리다이렉트라
>   색인 불가"를 띄우지만, **sitemap을 www 전체 URL로 제출하면 116개를 정상
>   인식한다.** 삭제·재등록은 불필요했다.
> - **구글 sitemap은 재제출해야 갱신된다.** "다시 읽기" 버튼이 없어서, 같은 URL을
>   그대로 다시 제출하는 것이 곧 재수집 요청이다(중복 행은 생기지 않는다). 7/29 밤
>   `/en/` 트리가 들어와 24→116개가 됐는데 구글은 며칠째 24로 알고 있었다.
>
> 네이버 서치어드바이저 UI에 **"검증 → 사이트 최적화" 메뉴는 더 이상 없다**.
> 지금은 색인 상태 확인 / URL 검사 / robots.txt 세 개다. 이 중 **색인 상태 확인**이
> 구글의 `색인 생성 → 페이지`에 해당하는 성과 지표다.

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
| The Neuron | ~50~70만 | "똑똑한 친구가 설명해주는" 톤, 왜 중요한지 분석 — 이 프로젝트의 `implication`과 가장 유사 |
| Superhuman AI | - | 실무자용 워크플로/프롬프트 중심 |
| Ben's Bites | - | 스타트업/투자 앵글 |

### 기능 단위 벤치마킹 (2026-07-27 리서치)

경쟁·유사 사이트를 실제로 열어 기능 단위로 비교한 결과. 위 표가 "누가 얼마나 큰가"라면
이건 "그들이 갖고 있는데 우리가 없는 게 무엇인가"다.

| 사이트 | 성격 | 참고할 점 |
|---|---|---|
| **AI Trends** `aitrends.kr` | 한국어, 글로벌 AI/ML 자동 수집 + 한국어 요약 | **직접 경쟁자.** 8개 카테고리 필터, 콘텐츠 유형 필터(논문/영상/레딧/팟캐스트/웹), 북마크·개인화 피드, 커뮤니티 |
| **AINews** `news.smol.ai` | 15만, LLM 자동 생성 데일리 | **구조적 쌍둥이.** `/tags/<slug>`를 Companies(200+)/Models(500+)/Topics(400+)로 나누고 언급 횟수 표시, Cmd+K 검색, RSS, 연구자 추천사 |
| **TLDR AI** `tldr.tech/ai` | 110만 | 랜딩이 거의 전부 전환 설계 — 구독자 수 명시, 포지셔닝 FAQ("누구를 위한 것이고 누구를 위한 게 아닌가") |
| **The Neuron** `theneuron.ai` | 50~70만 | 뉴스레터 밖으로 확장(툴 디렉토리·아카데미·팟캐스트·이벤트), 구독자 수 + 기업 로고로 소셜 프루프 |
| **AI Weekly** `aiweekly.co` | 11년 아카이브 | 스토리별 heat 점수, "최다 보도/급상승/급락", 113개 엔티티 추적 대시보드 |
| **Ground News / Particle** | 뉴스 앱 | 같은 사건을 출처별로 묶어 보여주고 출처 목록을 항상 노출 |
| **Emergent Mind** | AI 논문 특화 | 논문 + X/Reddit/GitHub 토론을 함께 집계 |

**이 리서치로 메운 격차 (구현 완료)**
1. **아웃바운드 RSS** — 위 사이트 대부분이 갖고 있는데 우리만 없었다. `/feed.xml`,
   `/en/feed.xml`. 항목 단위는 기사가 아니라 하루(우리 편집 단위와 일치).
   Feedly/Inoreader 유입과 RSS→SNS 자동화의 전제 조건이기도 하다.
2. **토픽 태그 + `/topics/<slug>`** — 가장 큰 구조적 격차였다. `config/topics.json`의
   고정 12개 taxonomy. AINews처럼 자유 태그로 가지 않은 이유는 규모 차이다 — 하루 10건
   규모에서 자유 태그는 태그당 1~2건짜리 thin page를 양산한다.
3. **다출처 커버리지 배지** — `cross_source_count`가 기사 선별에는 쓰이는데 화면에는
   안 나왔다. AI Weekly의 "최다 보도"와 Ground News가 파는 가치가 이미 계산된 채
   버려지던 셈. 2 이상일 때만 표시(1은 노이즈).
4. **랜딩 신뢰 신호 + FAQ** — TLDR/The Neuron 방식. 단 구독자 수 대신 누적
   브리핑 일수·기사 수·용어 수를 쓴다(작은 숫자를 소셜 프루프로 내세우면 역효과).
   FAQ는 `FAQPage` JSON-LD로도 나가 질문형 쿼리 인용에 직접 기여한다.

**의도적으로 도입하지 않은 것** — 나중에 다시 논의하지 않기 위해 이유까지 남긴다.
- 로그인·북마크·개인화 피드(aitrends.kr): 정적 사이트 + 무인 운영이라는 구조와 충돌.
- 댓글·투표·커뮤니티: 모더레이션은 자동화할 수 없고, 방치된 댓글난은 없느니만 못하다.
- 툴 디렉토리·아카데미·팟캐스트(The Neuron): 수익화 단계의 이야기이고 미션 밖이다.
- 추천인 리워드 프로그램: 구독 규모가 붙기 전엔 관리 비용만 든다.
- 오디오/TTS 버전: 이중 언어라 비용이 두 배이고, 읽기 시간 3분짜리 콘텐츠에 맞지 않는다.

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

**어디든 링크를 걸 때는 `dailyaithread.com`이 아니라 `dailyaithread.com/en/`을
쓴다** — Product Hunt의 "Website URL" 필드도 포함(§6 참고: `/en/`에 착지하면
그 뒤로 사이트 안 다른 페이지를 눌러도 영어가 유지됨).

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
  > https://www.dailyaithread.com/en/ — happy to answer questions about the
  > pipeline.

### Reddit (self-promo 허용 스레드에서만 사용)
> Built Daily AI Thread — reads AI news in full, flags multi-outlet coverage
> as a significance signal, and explains jargon inline. Free, bilingual,
> no login. Feedback welcome: dailyaithread.com/en/

## 6. 영어권 착지 페이지 (`/en/`)

기존엔 한 페이지 안에서 언어 토글만 지원해서, 구글 검색결과나 Reddit/HN에서
클릭해 들어온 영어권 방문자도 처음엔 한국어 제목·설명을 먼저 보게 되는
문제가 있었다. `dailyaithread.com/en/`을 새로 만들어 같은 날 콘텐츠를
`default_lang="en"`으로만 다시 렌더링한다 — 원문은 이미 한/영 둘 다 작성돼
있으므로 새로 쓸 콘텐츠는 없다.
- `/`(한국어 기본)과 `/en/`(영어 기본) 사이에 `hreflang` 상호 참조 태그를
  추가했다(`x-default`는 한국어). 구글에 "같은 콘텐츠의 언어 버전"이라고
  정확히 알려주는 정식 방법 — 중복 콘텐츠로 오인될 위험 없음.
- `/en/`에 착지하면 언어 선택이 `localStorage`에 저장돼, 이후 아카이브·주간
  회고·용어사전 등 다른 페이지로 이동해도(전부 이미 한/영 토글을 지원하므로)
  영어가 계속 유지된다 — 이 트릭 덕분에 모든 페이지를 `/en/` 아래에 따로
  미러링할 필요가 없었다(범위를 "착지 페이지 하나"로 좁게 유지).
- 매일 오늘자 `docs/index.html`과 함께 `docs/en/index.html`도 자동 생성되고
  `sitemap.xml`에도 포함된다. Product Hunt/HN/Reddit 링크는 앞으로 이
  `/en/` URL을 우선 사용하면 된다.

## 7. 국내(한국) 시장 노출 전략

### 포지셔닝
국내엔 뉴닉·어피티·캐릿 같은 뉴스레터가 이미 확고하지만 전부 MZ 트렌드/경제
제너럴 매체고, **AI 전문 뉴스레터는 상대적으로 비어 있다**(눈에 띄는 건
"AI 코리아 커뮤니티 뉴스레터" 정도 — 직접 겨루기보다 상호 홍보 대상으로 접근).
차별점은 영어권 전략(§4)과 동일: 원문을 실제로 다 읽는다, 여러 매체가 같은
사건을 다루는지 감지한다, 용어를 클릭 한 번으로 설명한다, 교차 종합 인사이트를
쓴다 — "또 하나의 헤드라인 모음"이 아니라는 것.

### 채널별 적합도 판단
콘텐츠 성격이 "극단적으로 정보성"(텍스트 기반 분석·종합)이라, 채널마다 적합도가
다르다:
- **적합**: GeekNews, X(트위터), Threads, 브런치, IT 미디어 기고 — 전부 텍스트
  기반이거나 텍스트를 그대로 재활용 가능.
- **낮은 우선순위**: 유튜브 쇼츠/틱톡. 쇼츠는 튜토리얼·하우투처럼 시각적으로
  보여줄 게 있는 콘텐츠에 강하고, 조회의 85%가 무음 시청이라 자막·비주얼 훅이
  필수라 제작 비용이 크다. 지금 콘텐츠(교차 종합 분석, 텍스트 설명)는 이 형식과
  안 맞는다. 굳이 시도한다면 "AI 용어 하나, 30초 설명"처럼 이미 써둔 `glossary`
  설명을 그대로 낭독하는 최소 제작비 포맷으로 한정 — 새 영상 스토리보드를
  만들 필요는 없다.

### 채널 전략
1. **GeekNews(`news.hada.io`) "Show" 게시판** — 국내 개발자/기술 커뮤니티의
   Hacker News 격. Show HN과 같은 문화(마케팅 카피보다 진짜 빌드 스토리에
   반응)라 §5의 Show HN 초안을 한국어로 각색해 그대로 재사용 가능(아래 초안 참고).
2. **GPTers(`gpters.org`)** — "AI를 실전에 어떻게 쓰는가"에 초점을 둔 활발한
   국내 커뮤니티. 독자층이 "AI 뉴스를 매일 챙겨보고 싶어하는" 타겟과 정확히
   겹친다. 커뮤니티 내 자기소개/공유 스레드 규칙을 먼저 확인하고 참여.
3. **브런치(`brunch.co.kr`)** — 이미 기록해둔 미해결 과제("주간 회고 SNS 홍보",
   과거 메모 참고)와 직결. 주간 회고를 브런치 글로 다시 발행하면 카카오
   생태계(다음 메인, 카카오톡 뷰 등) 노출 기회가 생긴다.
4. **요즘IT / 아웃스탠딩 기고·제보** — "AI가 매일 뉴스를 원문까지 읽고 종합하는
   파이프라인을 만들었다"는 빌드 스토리 앵글로 기고 제안. 아웃스탠딩은
   `help@outstanding.kr`로 명함을 담은 메일을 보내면 창업자방 커뮤니티 입장도
   가능(추가 네트워킹 채널).
5. **X(트위터)** — 국내 AI/테크 트위터 니치에 `daily_insight`(교차 종합)를
   스레드로 게시(매일 또는 주 3회). 리서치상 후크가 스레드 성과의 90%를
   좌우하므로, 일반 요약이 아니라 "겉보기엔 무관한 기사들이 사실 하나의
   흐름이었다"는 연결형/반전형 후크를 쓴다(아래 템플릿 참고).
6. **Threads** — 긴 글보다 짧고 잦은 포스팅이 맞는 채널. `glossary`에 이미
   쓴 설명을 "이 용어 아세요?" 데일리 퀴즈로 재활용(뉴닉/어피티가 "상식테스트"로
   재미를 유도해 구독 전환시키는 것과 같은 원리) — 새 콘텐츠 비용 없이 매일
   포스팅 소재를 확보할 수 있다.

### 실행 주체
§4와 동일 — **자동화 대상이 아니라 사용자가 직접 실행하는 항목**이다. 계정
운영, 실제 게시, 커뮤니티 규칙 확인은 전부 사람이 해야 한다.

### 초안 카피

**GeekNews Show 게시글**
- 제목: `AI 뉴스를 매일 원문까지 읽고, 여러 매체가 같은 사건을 다루는지 감지해 종합하는 파이프라인을 만들었습니다`
- 본문:
  > 대부분의 AI 뉴스레터는 RSS 요약을 그대로 붙여넣습니다. 저는 매일 그날의
  > 주요 AI 기사 원문을 실제로 다 읽고, 여러 매체가 같은 사건을 동시에
  > 다루는지 감지하고(중요도 신호로 씀), 그날 기사 전체를 가로질러 "결국 무슨
  > 의미인가"를 종합해서 쓰는 파이프라인을 만들었습니다.
  >
  > 동작 방식: 매일 RSS 피드 약 11개에서 후보를 모으고, 전날 이미 다룬 건
  > 제외하고, 여러 출처가 동시에 다루는 사건에 가중치를 줘 상위 10개를
  > 고릅니다. 이 10개만 원문을 읽어 요약·시사점을 씁니다. 일요일엔 그 주
  > 전체를 관통하는 흐름을 주간 회고로 한 번 더 종합합니다.
  >
  > 개인적으로 만족하는 부분: 어려운 용어가 나올 때마다 그 자리에서 클릭하면
  > 쉬운 말로 설명이 뜹니다(같은 날 바로 등록되고, 누적돼 용어사전으로도
  > 남습니다). 무료, 회원가입 없음, 한/영 둘 다 지원합니다.
  >
  > https://www.dailyaithread.com — 피드백 환영합니다, 특히 "AI 뉴스가 이렇게
  > 다뤄줬으면" 하는 부분이 있다면 듣고 싶어요.

**X/Threads 데일리 인사이트 스레드 템플릿** (매일 `daily_insight` 기반)
- 1번째 글(후크, 연결형/반전형 예시):
  > 오늘 나온 AI 뉴스 10개 중 [N]개, 사실 같은 얘기를 하고 있었습니다.
  > 무슨 뜻이냐면 🧵
- 2번째 글부터: `daily_insight.paragraphs_ko`를 트윗/포스트 단위로 나눠 이어붙임
  (문장을 새로 쓰지 않고 그대로 재활용 — 이미 그날 작성된 종합 분석이라 원가 0).
- 마지막 글: `다른 이야기 이어보기 → dailyaithread.com`

**Threads 용어 퀴즈 포맷** (매일 새 용어가 등록될 때)
> 오늘의 AI 용어: "OOO", 아시나요?
>
> [한 줄 띄우고 설명 — glossary의 explanation_ko 그대로 재사용]
>
> 더 많은 용어: dailyaithread.com/glossary

## 8. 다음에 할 만한 것 (지금은 범위 밖)

- `llms.txt` — 표준화되면 재검토.
- `/en/`을 아카이브·주간 회고·주제별 페이지까지 확장(지금은 착지 페이지와 영어 피드만
  있고, 이후 탐색은 localStorage 유지 트릭에 의존) — 실제 영어권 트래픽이 늘어
  개별 페이지 색인 필요성이 확인되면 검토.
- **Cmd+K 전역 검색** (§4 AINews 참고) — 지금 검색은 홈 하단 "지난 브리핑" 박스 안에만
  있어 발견되기 어렵다. `search-index.json`을 그대로 쓰면 되므로 비용은 낮은 편.
- **동일 스토리의 형제 기사 링크** (§4 Ground News/Particle 참고) — `cross_source_count`로
  "몇 곳이 다뤘는지"는 이제 보여주지만 "어디가 다뤘는지"는 아직이다. `fetch_articles.py`가
  클러스터에서 1등만 남기고 나머지를 버리므로, 형제 링크를 digest까지 넘기는 작업이 선행돼야 한다.
- **주간 지표** — 그 주 최다 보도 주제, 신규 등록 용어 수. 데이터는 이미 아카이브에 다 있다.
