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
| **The AI Daily Brief** `aidailybrief.ai` | 인간 분석가(NLW) 데일리 팟캐스트 20~33분 + 뉴스레터 | (2026-08-02 분석) 직접 경쟁 아님 — 오디오 30분과 텍스트 3분은 소비 맥락이 다름. 배울 것: ① "Most Sharable — lines worth quoting" 섹션(공유할 문장을 미리 뽑아 공유 마찰 제거 — daily_insight 헤드라인에 적용 가능, 트래픽 생긴 뒤 검토) ② 광고 제거형 Patreon $3/월(콘텐츠 안 잠그는 유료화 — PRODUCT.md ④ 참고). **주의: 영어권 이름 혼동**("AI Daily Brief" vs "Daily AI Thread") — 대응은 개명이 아니라 포지셔닝: 소개 첫 문장을 항상 reads-full-articles/unattended/bilingual로 시작해 즉시 구분되게 유지 |

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
- **기사별 AI 생성 일러스트** (2026-08-03 검토): ① 유일한 상시 유료 의존성이 생겨
  "한계비용 0" 전제(PRODUCT.md §0)를 깬다 ② "원문을 실제로 읽는 신뢰" 포지셔닝과
  AI 슬롭의 시각 언어가 자기모순 ③ TLDR·AINews 등 텍스트 뉴스레터 관행도 무이미지
  ④ 무인 운영 복잡도(API·폴백·연 3,600장 누적). 공유용 시각물은 동적 OG 이미지가
  이미 담당. 여지: 수치 데이터 기사의 **자동 차트**(장식 아닌 정보, 렌더링 비용 0)는
  트래픽 확보 후 재검토.

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

### 공통 — 게시 전에 확인할 사실 (2026-08-03 기준)

카피에 숫자를 쓸 때 이 값을 쓴다. 게시 시점에 `/about`이나 홈 하단 지표에서
현재 값을 다시 확인할 것 — 매일 늘어난다.

| 항목 | 값 |
|---|---|
| 브리핑 | 11일 연속 (2026-07-23 시작) |
| 누적 기사 | 108건 |
| 용어사전 | 47개 (각각 개별 URL) |
| 주제 | 12개 분류 중 11개에 기사 있음 (2026-07-30 기준, 미재확인) |
| 주간 회고 | 2개 (2026-W30, 2026-W31) |
| RSS 소스 | 12개 — 언론 8, 공식 발표 3, 커뮤니티 1 |
| 총 페이지 | 152쪽 (sitemap 실측, 한/영 합계) |

> 갱신 방법: 브리핑 일수·기사 수·용어 수는 `/about` 하단 지표 줄에 그대로 나온다.
> 총 페이지는 `docs/sitemap.xml`의 `<loc>` 개수, 주간 회고는 `docs/weekly/` 파일 수다.

**8일차에 무엇을 런칭할지 가려야 한다.** GeekNews와 Show HN은 "무엇을 만들었나"에
반응하는 곳이라 규모와 무관하게 지금 나가도 된다. 반대로 **Product Hunt는 아껴둔다**
— 실질적으로 한 번뿐인 카드이고, "8일치 아카이브"보다 "30일 무중단 + 주간 회고 4개"가
훨씬 강한 소재다. 한 달쯤 더 쌓은 뒤에 쓴다.

**채널 순서 (GeekNews 7일 대기 제약 반영, 2026-07-30 기준)**

| 시점 | 채널 | 목적 |
|---|---|---|
| 즉시 | GeekNews **가입만** | 7일 타이머를 시작시킨다. 게시는 나중 |
| ~8/5 | (게시 없음 — 준비 기간) | 댓글 루틴으로 카르마·이력·IH 권한 적립 |
| ~8/6 | **GeekNews 게시** | 국내 첫 실탄. 첫 외부 피드백 |
| 그 며칠 뒤 | **Show HN** | 영어권. 가장 다듬어진 상태로 |
| IH 권한 나오면 | Indie Hackers 게시 | 피드백 채널 (아래 게이트 참고) |
| 8월 말~9월 | Product Hunt + r/SaaS 1회 카드 | 30일 실적이 쌓인 뒤. r/SaaS는 60일 1회 제한(§5 참고) |

큰 채널일수록 뒤에 둔다 — 앞 채널에서 "무엇이 안 통하는지"를 배워서 카피를 고친 뒤
쓰기 위해서다. Show HN과 PH는 같은 프로젝트로 두 번 쓰기 어려운 카드라 특히 그렇다.

**모든 텍스트 채널에 워밍업 게이트가 있다는 게 확인됐다(2026-07-31).** GeekNews는
가입 후 7일, Reddit은 댓글 카르마 ~50, HN은 활동 이력, Indie Hackers는 모더레이터가
"성의 있는 댓글 기여 패턴"을 보고 수동으로 게시 권한을 부여한다(또는 유료 IH Plus).
즉 **"즉시 게시 가능한 무료 채널은 r/SaaS 주간 스레드뿐"**이고, 준비 기간(~8/6)의
댓글 활동은 Reddit 카르마·HN 이력·IH 권한 세 곳에 동시에 기여하는 같은 일이다.

**Hacker News 계정도 미리 만들어 둔다.** 가입 직후 자기 홍보만 올리는 계정은
자동으로 걸러질 수 있으므로, 게시 전까지 관심 있는 스레드에 댓글 몇 개라도 남겨
활동 이력을 만들어 두는 편이 안전하다.

**Reddit 재게시 조건 — 댓글 카르마 50을 목표로 한다.** r/SideProject의 automod는
대략 댓글 카르마 50 이상을 요구하는 것으로 알려져 있다(2026-07 서드파티 자료 기준,
공식 수치 아님). 20~30으로는 다시 걸러질 수 있다. 쌓는 방법: 이 기간에는 자기
링크를 **아예 올리지 않고**, 다른 사람 글에 도움이 되는 댓글만 남긴다 —
r/SideProject의 다른 프로젝트에 구체적 피드백, r/artificial·r/ArtificialInteligence·
r/LocalLLaMA의 기술 댓글이 안전하다. 한편 r/SaaS는 주간 self-promo 스레드 안에서만
홍보를 허용하므로, 카르마가 모자라도 그 스레드는 쓸 수 있다.

> **2026-08-03 수정 — 실측이 초기 요령을 반증했다.** 댓글 8개에 외부 업보트 0.
> 원인은 품질이 아니라 ① 타겟(조회 수백짜리 r/SideProject 신규 글 — 보는 사람이
> 없으면 표도 없다)과 ② 길이(HN식 3문단은 레딧에서 안 읽힌다). 원래 적혀 있던
> "새 글에 일찍"은 삭제한다. 수정된 요령: **큰 서브의 hot/rising으로 상승 중인
> 글에, 2~3문장으로.** 논쟁 주제 회피는 유지 — 큰 서브 hot에는 정치·드라마 글이
> 많으니 기술·프로젝트 글에만 단다. **8/10까지 재시도 후에도 카르마가 안 움직이면
> 레딧은 주 2~3회 유지 채널로 강등한다** — r/SideProject 재게시는 데드라인 없는
> 카드라 늦어져도 주력 일정(GeekNews·Show HN)에 손실이 없다. 또한 **8/6~9 런칭
> 기간에는 런칭 스레드 댓글 대응이 카르마 루틴보다 우선**이다(작성자 응답이 글
> 순위를 밀어올린다).

### 하루 댓글 루틴 (준비 기간 ~8/6 — 전략·글작성 세션(Fable)이 이 섹션 기준으로 하루 계획을 짠다)

목적 세 개가 **같은 활동 하나**로 채워진다: Reddit 댓글 카르마 50, HN 활동 이력,
IH 게시 권한(모더레이터가 "성의 있는 댓글 패턴"을 보고 수동 승인). 하루 총 30~45분,
두 슬롯. 이 시간을 넘기면 지속이 안 되므로 개수를 채우려 억지 댓글을 쓰지 않는다 —
**억지 댓글 1개가 실질 댓글 3개의 신뢰를 깎는다** (IH 모더레이터가 보는 건 개수가
아니라 패턴이고, Reddit 다운보트는 카르마를 되돌린다).

**슬롯 1 — 아침 (KST 08:30~09:00, 미국 저녁)**
- HN `new`/front page에서 아는 주제 글 1개 골라 댓글 1개. Show HN이 최적(작성자가
  답글을 잘 달고, 우리 Show HN 때 받고 싶은 종류의 댓글을 주는 연습이 된다).
- 그날 우리 브리핑에서 다룬 주제와 겹치는 글이 있으면 최우선 — 방금 원문까지 읽은
  주제라 실질 댓글이 가장 빨리 나온다.

**슬롯 2 — 밤 (KST 22:00~23:00, 미국 오전 = 트래픽 피크. 카르마 효율이 가장 좋은 시간)**
- Reddit 2~3개: 큰 서브(r/artificial·r/ArtificialInteligence·r/LocalLLaMA 등)의
  **hot/rising으로 상승 중인 기술·프로젝트 글에 2~3문장** 댓글 (2026-08-03 수정 —
  신규 글 타겟·긴 댓글은 업보트 0으로 반증됨, 위 박스 참고).
- IH 2개: 새 글(최신 피드)에 구체적 피드백. Reddit과 같은 요령.
- 끝나고 1분 기록: Reddit 댓글 카르마 수치, HN 카르마, IH 글쓰기 버튼 열렸는지.

**AI 티 제거 규칙 (2026-08-04 — 커뮤니티에 나가는 모든 글 공통. r/artificial에서
"'Fair' + 긴 대시가 LLM 말투"라고 실제로 지적당한 뒤 규칙화)**
- 긴 대시(—) 금지 → 쉼표·마침표로. "Fair/Sure, but"·"Great point" 류 정형 오프너 금지.
- LLM 빈출 어휘 회피(delve, robust, leverage, nuanced, it's worth noting, that said).
- 3항 병렬·완벽한 대구·정리형 마무리 문장 금지 — 결론 없이 끝나는 게 사람답다.
- 축약형·문장 조각 허용, 1인칭 구체 디테일("I run a…" — we 아님), 댓글에 불릿·이모지 금지.
- **쉬운 단어만 (2026-08-05 추가)** — 문어체·격식 어휘(unsettled, omission,
  evidence, notably 류)는 그 자체가 AI 티다. 일상어로(scared, got dropped, threw
  away). 중학생이 모를 단어면 바꾼다. 문장도 짧게.
- 한국어판: 과도한 "~죠", 번호 매기기, "정리하면" 마무리 회피.
- **최강 방어는 게시 전 사용자가 한두 단어라도 자기 말투로 고치는 것.**

**댓글 품질 체크리스트 (모든 채널 공통)**
1. 글을 실제로 읽고 **본문 속 구체 지점 하나**를 짚는다. 제목만 보고 쓴 댓글은 티가 난다.
2. 구조: 구체적 칭찬 한 줄 → 핵심 지적/질문 하나. 지적은 저자가 "좋은 포인트"라고
   받을 만한 것으로(약점 조롱이 아니라 개선 각도).
3. **질문으로 끝낸다** — 저자가 답글을 달면 스레드가 살고 업보트가 더 붙는다.
4. **자기 링크·사이트 언급 절대 금지.** 사이트는 프로필에만 존재한다.
5. 아는 주제만 쓴다. 우리 전문 영역(LLM 파이프라인, 요약/큐레이션, 정적 사이트,
   무인 운영, 사이드프로젝트 런칭)과 겹치는 글에서 진짜 댓글이 나온다.

**타겟 선정 효율 규칙** (2026-08-03 개정 — 위 수정 박스 반영)
- **트래픽이 이미 확인된 글에만 단다.** 큰 서브의 `hot`/`rising`에서 업보트가 이미
  붙어 상승 중인 글. ~~"올라온 지 1~3시간의 새 글에 일찍"~~은 삭제 — 그 글 자체가
  안 뜨면 아무리 일찍 달아도 보는 사람이 없다(댓글 8개 업보트 0으로 반증됨).
- **그중 댓글이 아직 적은 것**(대략 30개 미만)이 최적 — 트래픽은 오는데 경쟁은 적은
  자리다. 댓글 100개 넘은 대형 스레드는 묻힌다. 단 HN에서 상위 댓글에 다는 실질
  답글은 예외.
- **레딧은 2~3문장.** 길이는 채널마다 다르다 — 레딧은 짧게, HN·IH는 실질 내용이면
  길어도 된다. 대댓글은 그 스레드의 다른 대댓글 길이에 맞춘다.
- 논쟁적 주제(정치·회사 논란)는 피한다 — 다운보트 리스크만 있고 세 목적 어디에도
  기여하지 않는다. 큰 서브 `hot`에는 이런 글이 많으니 **기술·프로젝트 글로 한정**한다.

**종료 조건** — 이 루틴은 무기한이 아니다. Reddit 카르마 50 도달 시 r/SideProject
재게시(§5 카피), IH 권한이 열리면 IH 게시(§5 카피). 둘 다 끝나고 Show HN까지 나가면
루틴은 "주 2~3회 유지 보수"로 줄인다(계정을 죽이지 않는 수준).

### Hacker News — 프로필 `about` (Show HN 전에 채워둘 것)

가입 직후 상태라 `about`이 비어 있으면 "홍보용 일회 계정"으로 보일 수 있다. 아래를
그대로 붙여넣는다 (HN은 평문 필드라 마크업 불필요):

> Building https://www.dailyaithread.com/en/ — a daily AI news briefing
> generated by a pipeline that reads each article in full, checks whether
> multiple outlets are covering the same event, and writes one cross-cutting
> synthesis per day. Bilingual EN/KO, free, no signup.
>
> Contact: dhchun1203@gmail.com

### Hacker News — Show HN (지금 사용 가능)
- **제목**: `Show HN: I built a pipeline that reads AI news in full and explains why it matters`
- **본문**:
  > Most AI newsletters paste RSS summaries. I wanted something that actually
  > reads each article, notices when several outlets are covering the same
  > event, and explains the "so what" instead of just the "what."
  >
  > How it works: every morning it pulls candidates from 12 feeds (8 press,
  > 3 official company blogs, 1 community), drops anything covered on a
  > previous day, and ranks what's left by source type, recency, and how many
  > independent outlets are covering the same story. The top 10 get their full
  > text fetched, summarized, and analyzed. Then it writes one cross-cutting
  > synthesis of what the whole day adds up to — that part is the piece I
  > actually care about. Sundays get a weekly recap if there's a real
  > throughline.
  >
  > Two things I'm happy with:
  >
  > - Any jargon term becomes a clickable inline explainer, written the same
  >   day. 33 terms so far, each with its own URL, so the glossary grew as a
  >   byproduct rather than as a separate writing task.
  > - Same-story detection was the hardest part and I got it wrong twice. My
  >   first version merged on a single shared headline keyword, which decided
  >   that "5 ways to host a dinner party with Google Search" and "Google's AI
  >   search is becoming the default" were the same event — and since it keeps
  >   only one article per cluster, it was silently discarding 4 good articles
  >   a day. Company and product names turned out to be useless as merge
  >   evidence; excluding them fixed it.
  >
  > Known limitation: some outlets block full-text fetching, so those entries
  > fall back to the feed summary. I keep reserve candidates to swap in when
  > that happens, but it's not fully solved.
  >
  > Static site (Python + Jinja2) on Vercel, no server. The daily
  > reading/writing step runs on Claude. Fully bilingual — separate EN and KO
  > page trees, not a toggle. Free, no signup to read.
  >
  > https://www.dailyaithread.com/en/ — happy to answer anything about the
  > pipeline, and genuinely want to hear what you wish AI news coverage did
  > differently.

### Reddit (self-promo 허용 스레드에서만 사용)
> Built Daily AI Thread — it reads the day's top AI articles in full, flags
> when multiple outlets cover the same story as a significance signal, and
> writes one synthesis of what the day adds up to. Jargon is clickable
> inline. Free, bilingual, no login: dailyaithread.com/en/

### r/SaaS (2026-07-31 규칙 강화 확인 — **지금 쓰지 않는다, 8월 말 이후 1회 카드**)

> **2026-07-31 확인된 신규 규칙**: 스팸 대응으로 self-promo가 **60일 1회**로 제한됐다
> — 독립 글뿐 아니라 **댓글 플러그, 링크, 제품 언급까지 포함**이고, 알트 계정도 동일
> 유저로 친다. 위반 시 밴 + 전체 게시물 삭제 + **URL을 automod 블랙리스트에 등록**.
> "주로 홍보하는 계정은 삭제"도 명시됐다.
>
> 판단(같은 논의 반복 방지용): ① 카르마 1짜리 계정이 홍보 댓글을 달면 그게 유일한
> 활동이라 "홍보용 계정 삭제" 조건에 정확히 해당한다. ② URL 블랙리스트는 계정 밴과
> 달리 복구 불가능한 도메인 자산 손실이다. ③ 60일 1회 제한이라 어차피 한 발뿐인
> 카드다 — 9일차 맨몸 계정으로 쏘지 않고, 계정 이력과 제품 숫자가 쌓인 **8월 말~9월
> (PH 시기)에 의도적으로 1회 사용**한다. 이로써 "즉시 게시 가능한 무료 채널"은
> 없어졌고, 준비 기간의 첫 실탄은 GeekNews(8/6)다.

r/SaaS 독자는 빌더라 범용 카피 대신 무인 운영·한계비용 0 앵글을 앞세운다. 숫자는
게시 시점에 `/about` 실측값으로 갱신.

> Built **Daily AI Thread** — a daily AI news briefing that reads the day's
> top articles in full (not just RSS snippets), detects when multiple outlets
> are covering the same story as a significance signal, and writes one
> synthesis of what the day adds up to. Jargon becomes a clickable
> plain-English explainer.
>
> The part this sub might find interesting: the entire pipeline runs
> unattended every morning — collection, ranking, writing, email send,
> deploy — on a static site with free tiers. Marginal cost per day is close
> to zero, whether 10 people read it or 10,000. Nine days in: 88 articles
> analyzed, 39 glossary terms (each grew out of a daily briefing, not
> written separately), fully bilingual EN/KO.
>
> Free, no signup to read: https://www.dailyaithread.com/en/
>
> Honest question for feedback: does the landing page make it clear within
> ~10 seconds how this differs from other AI digests? That's the thing I
> can't judge myself.

### Indie Hackers (게시 권한 확보 후 — 피드백 채널)

> **2026-08-04 실제 게시판 (아래 초안을 §8 원칙으로 개정한 최종본).** 제목을
> 포지셔닝형에서 **스토리형으로 교체**: "My AI news pipeline was silently throwing
> away 4 good articles a day (13 days in)" — 실패+구체 숫자+빌드 신호(정보 격차
> 설계). 본문은 13일·126건·58개 실측, AI 티 제거 문체 적용, URL 칸 비우고 텍스트
> 글로(URL 칸 채우면 본문 280자 잘림 — IH 폼 함정). **의도된 A/B**: IH=스토리형
> 제목, GeekNews(8/6)=포지셔닝형 제목 → 반응 비교해 Show HN 제목 결정에 사용.

> **신규 계정은 바로 글을 못 올린다(2026-07-31 확인).** 게시·링크 공유 권한은
> 모더레이터가 매일 "성의 있고(effortful) 진정성 있게(authentically) 댓글로 기여하는
> 패턴"을 보고 수동 부여하거나, 유료 IH Plus 가입으로 열린다. 걸리는 기간은 공개돼
> 있지 않다. **IH Plus 결제는 하지 않는다** — 게시글 하나를 위한 지출로는 과하고,
> IH는 어차피 주력이 아니라 저위험 피드백 채널이다. 대신 준비 기간의 댓글 활동
> 대상에 IH를 포함시킨다(다른 프로젝트에 구체적 피드백 — Reddit 카르마 쌓기와
> 같은 요령, 같은 기간에 병행).

IH는 빌드-인-퍼블릭 서사와 **솔직한 숫자**에 반응한다. 다듬은 마케팅 카피보다
"8일째, 이렇게 만들었고 이게 안 풀린다"가 성과가 좋다. 게시 시점에 일수·기사 수를
§5 상단 표(및 `/about` 실측값)로 갱신할 것.

- **제목**: `A daily AI news briefing that reads the full articles, not just headlines — 8 days in`
- **본문**:
  > Most AI newsletters paste RSS summaries. I built a pipeline that reads
  > each day's top articles in full, notices when several outlets are
  > covering the same event (that's a significance signal), and writes one
  > synthesis of what the day adds up to. Any jargon term becomes a
  > clickable plain-English explainer, written the same day.
  >
  > Where it stands after 8 days: 79 articles analyzed, 33 glossary terms
  > (each one grew out of a daily briefing rather than being written
  > separately), 116 pages live in English and Korean. It's a static site
  > (Python + Jinja2) on Vercel with the daily reading/writing step running
  > on Claude, so a day of content costs me almost nothing and the whole
  > thing runs unattended every morning.
  >
  > Hardest bug so far: same-story detection merged on a single shared
  > headline keyword, which decided that a listicle about dinner parties
  > and a story about Google's AI search were "the same event" — and
  > silently discarded 4 good articles a day. Excluding company and product
  > names as merge evidence fixed it.
  >
  > What I'd love feedback on:
  >
  > - Does the "so what" analysis actually add value for you over a
  >   headline list, or do you skim past it?
  > - Landing page: is it clear within ~10 seconds how this differs from
  >   other AI news digests?
  >
  > https://www.dailyaithread.com/en/ — free, no signup to read.

### Product Hunt (한 달쯤 뒤 — 지금은 보류)
- **제품명**: Daily AI Thread
- **태그라인**: `AI news that reads the full article, not just the headline`
- **설명**:
  > Every morning, Daily AI Thread reads the full text of the day's top AI
  > articles, flags when multiple outlets are covering the same story, and
  > writes one synthesis of what it all means — with clickable plain-English
  > explanations for any jargon. Browse by topic, search the whole archive,
  > or subscribe by email or RSS. Free, bilingual (EN/KO), no signup to read.
- **메이커 첫 댓글**: §5의 Show HN 본문을 PH 톤으로 줄여 재사용한다(같은 내용을
  두 번 쓰지 않는다). 게시 시점의 무중단 일수와 누적 기사 수로 숫자를 갱신할 것.

## 6. 영어권 URL 트리 (`/en/`)

영어권 방문자가 구글·HN·Reddit에서 들어왔을 때 한국어 제목을 먼저 보는 문제를
없애기 위해 `/en/` 트리를 만들었다. 원문은 이미 한/영 둘 다 작성돼 있으므로 새로
쓸 콘텐츠는 없다.

**처음에는 착지 페이지 하나만 만들고 이후 탐색은 `localStorage`에 언어를 저장해
유지하는 방식이었는데, 그 방식은 버렸다.** 크롤러가 보는 언어와 사람이 보는 언어가
어긋나 한 페이지에 두 언어의 마크업이 섞였고(영어 화면에 한국어 FAQPage 구조화
데이터가 나가는 등), 무엇보다 색인 단위가 하나뿐이어서 영어 페이지가 개별적으로
검색에 걸리지 않았다. 지금은 **한 페이지 = 한 언어**로 완전히 분리했다:

- `docs/`(한국어)와 `docs/en/`(영어)에 홈·아카이브·주제별·용어사전·용어 개별
  페이지·소개·주간 회고·RSS까지 전부 각각 생성된다. sitemap에 들어가는 페이지 수는
  매일 늘어난다(2026-07-30 기준 116쪽 → 2026-08-03 기준 152쪽).
- `/`와 `/en/` 사이에 `hreflang` 상호 참조(`x-default`는 한국어). 중복 콘텐츠로
  오인될 위험 없이 "같은 콘텐츠의 언어 버전"임을 알린다.
- 언어 전환은 클라이언트 토글이 아니라 **상대 URL 이동**이다(`.lang-switch`).
- 접두사가 두 종류인 것이 이 구조의 함정이다 — 공유 자산(CSS·JS·favicon)은 사이트
  루트에, 페이지 링크는 **언어 루트**에 상대적이어야 한다. 둘을 같은 값으로 쓰면
  영어판에서 "Topics"를 눌렀을 때 한국어 페이지로 새는 버그가 생긴다(실제로 발생,
  `dom_smoke.test.js`의 `checkNoLanguageLeak`가 회귀를 막는다).

**해외 채널에 링크를 걸 때는 반드시 `dailyaithread.com/en/`을 쓴다** — Product Hunt의
Website URL 필드도 포함. 그 뒤로 사이트 안 어느 페이지를 눌러도 영어가 유지된다.

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
   > **가입 후 일주일이 지나야 글을 등록할 수 있다**(2026-07-30 확인). 게시할
   > 마음이 생긴 날 바로 올릴 수 없으므로 **가입만 먼저 해두고 타이머를 돌린다.**
   > 이 제약 때문에 "GeekNews 먼저 → 피드백 반영 → Show HN" 순서가 깨진다.
   > §5의 채널 순서 참고.
2. **GPTers(`gpters.org`)** — "AI를 실전에 어떻게 쓰는가"에 초점을 둔 활발한
   국내 커뮤니티. 독자층이 "AI 뉴스를 매일 챙겨보고 싶어하는" 타겟과 정확히
   겹친다. 커뮤니티 내 자기소개/공유 스레드 규칙을 먼저 확인하고 참여.
3. **브런치(`brunch.co.kr`)** — 이미 기록해둔 미해결 과제("주간 회고 SNS 홍보",
   과거 메모 참고)와 직결. 주간 회고를 브런치 글로 다시 발행하면 카카오
   생태계(다음 메인, 카카오톡 뷰 등) 노출 기회가 생긴다.
   **작가 신청 필요**(가입 즉시 발행 불가, 심사 며칠). 2026-08-02 프로필 세팅 완료
   (이름 '솔데브', 파비콘 디자인 프로필 이미지).
   > **1차 신청 탈락(2026-08-03) — 아래 초안 그대로 재사용 금지.** 추정 원인:
   > 신청서가 "서비스 운영자의 채널 확보" 톤이라 홍보성으로 읽힘 + 저장글이 전부
   > 재발행 각색 + 편별 목차 부족. 재신청(8/9~10 목표)은 ① 정체성을 "매일 AI
   > 뉴스를 원문까지 읽는 사람의 기록"으로 재작성(URL 최소화) ② 브런치 네이티브
   > 창작 글 1편(디너파티 오병합 실패담) 추가로 저장글 3편 ③ 활동 계획에 5편치
   > 편별 목차 명시. 브런치 공식 FAQ 기준 재신청 횟수 제한 없음, 이전 내용은
   > 저장 안 됨.
   **2차 신청서 (2026-08-03 작성, 같은 날 v2로 개정 — 이걸 쓴다):**
   > v2 개정 이유(사용자 지적): "만들다 틀리는 사람"도 여전히 개발자 서사다.
   > 브런치 대중 독자의 공감 지점(AI 뉴스 과잉의 불안)에서 출발하고, 독자가
   > 얻어갈 것("기술을 몰라도 방향을 가늠하는 눈")을 명시하는 구조로 재작성.
   - **작가 소개(최종, ~280자)**: "AI가 세상을 바꾼다는 뉴스가 매일 쏟아집니다.
     다 따라가야 할 것 같은 불안에, 아예 뉴스 읽는 프로그램을 만들어 매일 아침
     그날의 AI 기사를 전부 읽고 있습니다. / 그렇게 읽다 보니 알게 된 것이
     있습니다. 뉴스는 매일 세상이 뒤집힐 것처럼 말하지만, 정말 중요한 변화는
     일주일에 하나쯤이고, 그마저 여러 기사에 조각나 흩어져 있다는 것입니다. /
     저는 그 조각을 잇는 글을 씁니다. 오늘의 뉴스가 아니라 뉴스들이 가리키는
     방향에 대해 — 기술을 모르는 사람도 지금 무슨 일이 벌어지는지 가늠할 수
     있도록." (3문단 = 공감→자격→독자 약속. 서비스명·URL 없음 유지)
   - **활동 계획**: 연재 두 축 + **`<혼자 만들다 틀린 것들>` 5편 편별 목차**
     (① 디너파티와 AI 검색이 같은 뉴스가 됐다 — 같은 사건 판별 2회 실패
      ② 일요일이 오지 않았다 — UTC 요일 계산으로 주간 회고가 몇 주 건너뛴 건
      ③ 어려운 말을 쓰지 않기로 하자 사전이 생겼다 — glossary가 부산물로 생긴 것
      ④ 읽을 수 없는 기사들 — 원문 차단 매체 앞에서의 판단
      ⑤ 매일 같은 시각에 보내겠다는 약속 — 발송 마커가 없어 아무도 몰랐던 며칠)
     + 주간 회고 연재 + 맺음 "두 글 모두 브런치 독자를 기준으로 새로 씁니다.
     같은 소재를 다루더라도 기록으로 남기는 글과 읽히기 위해 쓰는 글은 다른
     글이라고 생각합니다."
     → **편별 목차가 이번 재신청의 핵심**이다. 탈락 문구가 "앞으로 좋은 활동을
     보여주시리라 판단하기 어려워"였고, 1차엔 형식(주 1회)만 있고 무엇을 쓸지가
     없었다.
   - **참고 URL**: **최신 주간 회고 1개만.** 사이트 루트는 넣지 않는다 — 홈은
     카드 나열이라 "글"로 안 보이고 자동 수집 사이트 인상만 준다.
   - **서랍 순서**: ① 디너파티 에세이(대표작) ② W31 회고 ③ W30 회고.
     심사자가 첫 글만 볼 수 있으므로 네이티브 에세이를 맨 위에 둔다.
   - **활동 계획 최종 문안(v2, ~290자)**: "두 가지를 연재합니다. 하나는 주 1회
     '주간 AI 회고' — 한 주의 AI 뉴스 수십 건이 결국 무슨 이야기였는지, 기술을
     몰라도 흐름이 보이게 정리합니다. 다른 하나는 <혼자 만들다 틀린 것들> — 뉴스
     읽는 프로그램을 만들며 틀렸던 이야기입니다. ① 디너파티와 AI 검색이 같은
     뉴스가 됐다 ② 일요일이 오지 않았다 ③ 어려운 말을 쓰지 않기로 하자 사전이
     생겼다 ④ 읽을 수 없는 기사들 ⑤ 매일 같은 시각에 보내겠다는 약속. 기계를
     가르치려다 제가 배운 이야기라, 만들기에 관심 없는 분도 읽을 수 있게
     씁니다." (회고를 앞에 — 독자 관점의 주 상품. 편별 목차 5개 유지)

   1차 신청서 초안(기록용 — 재신청 시 위 방향으로 재작성):
   - **작가 소개**: "매일 아침 AI 뉴스를 원문까지 읽고 요약과 시사점을 정리하는
     자동 브리핑 서비스 '데일리 AI 스레드'(dailyaithread.com)를 만들어 운영하고
     있습니다. 기사 수집부터 선별, 집필, 발송까지 사람 손 없이 돌아가는 파이프라인을
     직접 설계했고, 지금까지 하루도 빠짐없이 한국어와 영어로 브리핑을 발행하고
     있습니다. 만드는 과정의 시행착오와, 매일 쌓이는 뉴스가 보여주는 큰 흐름을
     글로 남기려 합니다."
   - **활동 계획**: "주 1회 '주간 AI 회고'를 연재합니다. 한 주의 AI 뉴스 수십 건을
     관통하는 흐름 하나를 골라, 개별 기사가 아니라 '이번 주가 결국 무슨
     이야기였는지'를 정리하는 글입니다. 운영 중인 사이트에서 이미 매주 일요일
     발행하고 있어 소재가 끊길 위험이 없고, 브런치에서는 일반 독자 눈높이로 다듬어
     올립니다. 부정기적으로 무인 자동화 파이프라인 제작기도 쓸 계획입니다."
   - **참고 URL**: `/weekly/2026-W30` + 최신 주간 회고(신청 시점 확인) + 사이트 루트.

   **주간 재발행 절차 (전략·글작성 세션(Fable) 담당 — 2026-08-03 글작성 세션 폐지로
   통합. 이 절차만 보고 실행 가능해야 한다):**
   1. **시점**: 매주 일요일 저녁~월요일 오전(월요일 아침이 "지난주 정리" 수요와 맞음).
   2. **원문**: 저장소 `docs/weekly/<주차>.html`의 "이번 주 종합" 섹션(헤드라인 +
      본문 2문단 + 일별 헤드라인 목록). git pull 후 읽는다.
   3. **변환 규칙** — 사이트 버전은 매일 읽는 독자 전제라 압축돼 있다. 브런치 독자는
      처음 보는 일반인이므로:
      - 도입부 고정 템플릿(2~3문장): "매일 아침 AI 뉴스를 원문까지 읽는 자동 브리핑을
        만들어 운영한다 → 일요일마다 한 주를 관통한 흐름 하나를 정리한다 → 이번 주의
        실은 이것이다" 순서.
      - 전문용어는 나온 자리에서 한 줄로 푼다(예: 샌드박스 = AI가 정해진 범위 밖으로
        나가지 못하게 가둬둔 실행 공간). 괄호 설명보다 문장 속에 자연스럽게.
      - 사건이 요일별로 커져가는 서사를 살린다(수요일엔 단신 → 토요일엔 전모).
      - 중간 소제목 2~3개(굵은 제목)로 끊는다. 마지막은 "이번 주가 남긴 질문" 류의
        짧은 맺음 문단.
      - 끝에 고정 문구: "이 글은 한 주간 매일 발행한 브리핑 N편을 재구성한 것입니다.
        하루 단위 브리핑은 dailyaithread.com에서 무료로 읽을 수 있습니다."
   4. **제목**: 회고 헤드라인의 핵심 구절 인용형(예: "AI에게 준 권한이 통제를 앞지르고
      있다"). **소제목**: `이번 주 AI 뉴스를 꿰는 하나의 실 — YYYY년 M월 N째 주 회고`
      형식 고정(연재 정체성).
   4-1. **이미지 규칙 (2026-08-03 — 브런치 글 전체 공통, 에세이 포함)**:
      - **대표 이미지 = 시리즈 타이포 카드** — 먹색 바탕 + 세리프 제목 + 빨간 점
        (브랜드 마크 문법, Pillow 렌더링, Fable 제작). 매 편 같은 형식 = 작가
        시그니처의 시각 버전. 회고 연재와 에세이 연재는 색/레이아웃을 살짝 달리해
        시리즈를 구분한다.
      - **본문 중간 1~2장 = 실물 자료(스크린샷·커밋 로그 등 진짜 증거물, 사용자
        캡처) 또는 개념 도식(Fable이 SVG/Pillow 제작).** 실패담에는 생성 이미지보다
        실물이 진정성을 증명한다.
      - **AI 일러스트풍 금지** — 브런치 감성(사진·미니멀)과 글의 신뢰 톤에 어긋남.
        사이트 쪽 판단은 §4 배제 목록 참고(그쪽은 아예 이미지 없음).
   5. **형식 견본**: 2026-W30 편(브런치 서랍 저장본, 2026-08-02 작성)이 이 규칙의
      기준 구현이다.
   6. 링크는 한국어 루트(`dailyaithread.com`)를 쓴다 — `/en/` 아님(국내 채널).
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

**GeekNews Show 게시글** (지금 사용 가능 — 국내 첫 채널로 권장)
- 제목: `AI 뉴스를 매일 원문까지 읽고, 여러 매체가 같은 사건을 다루는지 감지해 종합하는 파이프라인을 만들었습니다`
- 본문:
  > 대부분의 AI 뉴스레터는 RSS 요약을 그대로 붙여넣습니다. 저는 매일 그날의 주요
  > AI 기사 원문을 실제로 다 읽고, 여러 매체가 같은 사건을 동시에 다루는지
  > 감지해 중요도 신호로 쓰고, 그날 기사 전체를 가로질러 "결국 무슨 의미인가"를
  > 한 편으로 종합해서 쓰는 파이프라인을 만들었습니다.
  >
  > 동작 방식: 매일 아침 피드 12개(언론 8, 기업 공식 블로그 3, 커뮤니티 1)에서
  > 후보를 모으고, 전날까지 다룬 건 제외하고, 출처 종류·최신성·같은 사건을 다루는
  > 매체 수로 점수를 매겨 상위 10건을 고릅니다. 이 10건만 원문을 가져와 요약과
  > 시사점을 쓰고, 마지막에 그날 전체를 관통하는 흐름을 하나로 종합합니다.
  > 일요일엔 그 주에 흐름이 있었으면 주간 회고를 한 번 더 씁니다.
  >
  > 만들면서 제일 애먹은 건 **같은 사건 판별**이었고 두 번 틀렸습니다. 처음엔
  > 제목에서 특정 키워드 하나만 겹치면 같은 사건으로 묶었는데, 그러다 보니
  > "구글 검색으로 디너파티 여는 5가지 방법"과 "구글 AI 검색이 기본값이 되고 있다"가
  > 같은 사건이 됐습니다. 클러스터당 1건만 채택하는 구조라 **매일 멀쩡한 기사
  > 4건이 조용히 버려지고 있었습니다.** 회사명·제품명은 병합 근거로 쓸 수 없다는
  > 걸 뒤늦게 알고 제외하니 해결됐습니다.
  >
  > 개인적으로 만족하는 부분은 어려운 용어가 나올 때마다 그 자리에서 클릭하면
  > 쉬운 말 설명이 뜨는 것입니다. 지금까지 47개가 쌓였고 각각 개별 URL을 가집니다 —
  > 용어사전을 따로 쓴 게 아니라 매일 쓰던 설명이 그대로 누적된 것입니다.
  >
  > 지금 11일째이고 기사 108건을 다뤘습니다. 한 번도 거르지 않았습니다.
  >
  > 한계도 있습니다. 일부 매체는 원문 접근을 막아서 그런 기사는 피드 요약으로
  > 대체됩니다. 예비 후보를 두고 교체하지만 완전히 해결하진 못했습니다.
  >
  > 정적 사이트(Python + Jinja2)라 서버가 없고 Vercel에 올라갑니다. 매일 읽고 쓰는
  > 단계는 Claude가 맡습니다. 한국어와 영어를 각각 별도 페이지로 만들며, 무료이고
  > 읽는 데 가입이 필요 없습니다.
  >
  > https://www.dailyaithread.com — 피드백 환영합니다. 특히 "AI 뉴스가 이렇게
  > 다뤄줬으면" 하는 부분이 있다면 듣고 싶습니다.

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

## 8. 글쓰기 원칙 — 다음 문단을 읽게 만드는 법 + 작가 시그니처

브런치 에세이·주간 회고 각색 등 **사람이 읽는 긴 글 전부에 적용**한다(2026-08-03
리서치 기반). 매일 브리핑의 GEO 작문 원칙(§1)과는 별개 층위 — 그쪽은 검색·인용용,
이쪽은 사람의 완독·재방문용이다.

### 연구 근거 → 실행 규칙

| 근거 | 발견 | 실행 규칙 |
|---|---|---|
| 정보 격차 이론 (Loewenstein 1994) | 호기심은 **중간 크기 격차**에서 최고. 격차 과대(모르는 용어)면 불안→이탈 | 첫 문단은 답이 아니라 **질문을 구체화**한다. 용어는 나온 자리에서 한 줄로 풀어 격차를 "중간"으로 유지 |
| 자이가르닉 효과 (1927) + 클리프행어 연구 | 미완결이 완결보다 ~2배 강하게 기억에 남음 | **문단 경계에서 닫지 않는다** — 답은 다음 문단 첫 문장에. 각 편 마지막 줄은 다음 편 예고(오픈 루프) |
| 서사 몰입 (Green & Brock 2000) | 주의·감정·심상이 이야기에 집중되면 완독·설득·기억 모두 상승 | 추상 선언 대신 **장면으로 시작**(날짜·상황이 있는 실제 사건). 구체적 숫자·디테일이 심상을 만든다 |
| 아이트래킹 (Poynter EyeTrack, NN/g) | 온라인 독자는 F패턴 스캔, 소제목·인용에서만 정지 | **소제목은 명사구 금지, 미완결 문장으로**("원인 분석" ✕ → "일요일은 어디로 갔나" ○). 소제목만 읽어도 서사 뼈대가 보이게 |
| Upworthy RCT 10만 헤드라인 (Nature Human Behaviour 2023) | 제목의 부정 단어 1개당 CTR +2.3% | 실패·틀림·상실을 제목에서 숨기지 않는다. 단 **본문이 제목의 약속을 지켜야** 재방문이 생긴다(낚시 금지 — Upworthy 자신이 신뢰 잃은 반면교사) |
| 감정과 확산 (Berger & Milkman 2012) | 고각성 감정(경외·놀람·분노)이 공유를 만들고 저각성(슬픔)은 죽임 | 클라이맥스는 **"무관해 보이던 것들이 하나로 이어지는 놀라움"**에 둔다 — 우리 콘텐츠의 천연 자원 |

### 작가 시그니처 — 솔데브 포맷 (모든 글에 반복하는 5가지 고정 장치)

주제가 달라도 "같은 작가"로 느껴지고, 그 형식 자체가 재방문 이유가 되게 한다.
정체성 한 줄: **"기계에게 읽기를 가르치다, 사람의 읽기를 다시 배우는 관찰자."**

1. **첫 문단 = 구체적 장면 하나** (3문장 이내, 날짜·상황이 있는 실제 사건).
   추상 선언("AI 시대에는…")으로 시작하는 글은 쓰지 않는다.
2. **관찰 → 균열 → 발견의 3박자** — 모든 글 중간에 "그런데 이상했다 / 틀렸다"
   전환이 정확히 한 번 온다. (신청서 v2의 3문단 구조와 동일한 리듬)
3. **소제목은 미완결 문장** — 위 아이트래킹 규칙의 시그니처화.
4. **끝에서 두 번째 문단 = 사람 이야기로 접기** — 기계·뉴스 이야기를 독자의
   읽기·삶의 습관으로 착지시킨다("기계가 틀리는 지점은 결국 사람이 뭉뚱그리는
   지점이었다"). 이 반전이 "브리핑하는 사람"과 "작가"를 가르는 지점.
5. **마지막 한 줄 = 열어두기** — 다음 편 예고 또는 남은 질문 한 문장.

문장 톤: 담백한 합니다체(신청서 v2와 동일), 자기연민 없는 담담한 고백, 수치는
정확하게, 전문용어는 그 자리에서 한 줄 풀기. 이 다섯 장치는 이미 쓴 자산(2차
신청서, 디너파티 에세이)의 구조를 규칙화한 것이라 소급 적용 비용이 없다.

## 9. 다음에 할 만한 것 (지금은 범위 밖)

**완료된 항목** — 이 목록에 있던 것 중 다음은 구현됐다. 다시 논의하지 않도록 남긴다.
- ~~`/en/` 트리 확장~~ — 착지 페이지 하나가 아니라 한/영 전체 트리로 완료(§6).
- ~~동일 스토리의 형제 기사 링크~~ — `related[]`가 digest→아카이브→화면까지 흐른다.
  선행 조건이던 클러스터링 오병합 수정도 함께 끝났다.
- ~~용어 페이지 전환 마감~~ — 완료(2026-08-03, Opus 세션). 용어 개별 페이지는 검색
  유입의 주력 착지점(트래픽 2위가 /glossary)인데 구독 유도가 없어 막다른 길이었다.
  하단에 구독폼을 추가했고, 등장 날짜→브리핑 링크는 **이미 구현돼 있었음**(전략
  세션의 WebFetch 요약 기반 점검이 이를 놓침 — 실제 수정은 중복 날짜 정리 + 링크
  확장). 홈은 전환 설계가 이미 충분해 손대지 않았다.

**남은 것**
- **재런칭 전략** (2026-08-02, levels.io 발표에서 채택) — 런칭은 1회성이 아니다. PH
  런칭 후에도 큰 기능(Cmd+K 검색, 주간 지표 등)마다 2~3개월 간격으로 다시 알린다.
  PH는 연 1회 재런칭이 관례적으로 허용된다. 같은 발표에서 하나 더: **PH 당일은 시차
  배치 원칙의 예외**다 — 그날만큼은 X·뉴스레터·커뮤니티를 동시에 몰아 "오늘 하루가
  이 제품 얘기"인 상태를 만든다(채널을 시차로 두는 건 학습 목적인데, PH는 마지막
  카드라 더 배울 다음 채널이 없다).
- **Cmd+K 전역 검색** (§4 AINews 참고) — 지금 검색은 홈 하단 "지난 브리핑" 박스 안에만
  있어 발견되기 어렵다. `search-index.json`과 `/api/search`를 그대로 쓰면 되므로
  비용은 낮은 편. 다만 트래픽이 없는 지금은 "검색할 사람"이 없어 우선순위가 낮다.
- **주간 지표** — 그 주 최다 보도 주제, 신규 등록 용어 수. 데이터는 이미 아카이브에
  다 있다. 주간 회고 페이지를 더 두껍게 만드는 소재.
- `llms.txt` — 표준화되면 재검토(§1의 판단 유지).
- **레딧을 "신호"로 쓰기** (2026-08-03, aitrends.kr 분석에서) — 서브레딧 공개
  JSON/RSS(`reddit.com/r/<sub>/new.json`)로 특정 사건이 r/LocalLLaMA 등에서 크게
  도는지를 `cross_source_count`의 보조 신호로 쓸 수 있다. **콘텐츠 소스로는 쓰지
  않는다** — aitrends처럼 레딧 글을 피드에 넣는 건 "전부 모아 필터로" 모델이고,
  우리는 "10건 선별" 모델이라 선별 비용만 는다. 착수 조건: 선별 품질 문제(중요
  사건 누락)가 실제로 관측될 때. 착수 시 주의: `reddit.com`(또는
  `www.reddit.com`/`oauth.reddit.com`) allowlist 추가 필요 — CLAUDE.md 규칙.
  착수 시 분업(2026-08-03 합의): 신호를 선별 점수에 어떻게 섞을지(가중치·기준)는
  전략 세션이 정하고, 구현·테스트는 Opus 세션이 한다.
  - **타당성 확인 완료(2026-08-03, Opus 세션)** — 세 가지만 미리 확인해뒀다.
    붙일 자리는 있다: `compute_rank_score()`가 세 항목의 단순 합이라 네 번째 항을
    더하면 되고, `compute_cross_source_counts()`가 후보 dict를 in-place로 채우는
    패턴을 그대로 쓸 수 있다. 무인 원칙도 맞출 수 있다: 실패 시 신호를 0으로 두면
    점수 함수가 지금과 완전히 동일하게 동작하므로 선별 결과가 안 바뀐다(타임아웃은
    `FEED_TIMEOUT_SEC`, 예외 삼키기는 `submit_indexnow`가 선례).
  - **allowlist에 넣을 정확한 호스트명은 `www.reddit.com`이다.** `reddit.com`은
    www로 리다이렉트되는데 allowlist는 도메인 정확히 일치라 그것만 넣으면 막힌다
    (2026-07-31에 The Verge·Wired 등 5개 피드가 이것 때문에 죽어 그날 브리핑
    9건 중 8건이 TechCrunch 한 곳에서 나왔다). 공개 JSON만 쓸 거면
    `oauth.reddit.com`은 필요 없다 — 그쪽은 토큰이 필요한 별도 엔드포인트다.
  - **착수 첫 단계는 코드가 아니라 "도달 가능한가" 확인이다.** Reddit이 근래 인증
    없는 데이터센터 IP의 JSON 요청을 403으로 막는 사례가 늘었는데, 우리 Routine이
    정확히 그 조건에서 돈다. 로컬에서 미리 찔러보는 것은 판단 근거가 안 된다
    (가정용 IP라 통과해도 실제 환경에서 막힐 수 있어 잘못된 안심만 준다).
    allowlist 추가 후 실행에서 200을 확인하고, 403이면 거기서 멈춘다 —
    `oauth.reddit.com` + 앱 등록으로 가면 비용 계산이 달라지므로 그때 다시 판단.
