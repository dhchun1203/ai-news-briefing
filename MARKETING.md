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
  og-image.png`(1200×630, `scripts/tools/generate_og_image.py`로 1회 생성 — 파이프라인
  상시 의존성 아님, Pillow 필요 시 로컬에서만 임시 설치). 지금은 날짜 없는 범용 브랜드
  카드 한 장을 모든 페이지가 공유한다 — 나중에 날짜별 동적 카드로 고도화 가능(현재는
  범위 밖으로 명시적으로 제외).
- 구현: `scripts/seo_utils.py`(신규 공용 모듈), `scripts/generate_site.py`/
  `scripts/generate_weekly_site.py`에서 호출, `templates/site.html.j2`/
  `templates/weekly.html.j2` head 수정.

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
2. **HTML 메타태그 방식 권장**(네이버는 DNS 인증보다 이쪽이 안정적) —
   `config/site_verification.json`의 `naver_site_verification` 값을 발급받은 값으로
   채우고 재배포하면 자동으로 `<meta>` 태그가 나간다. HTML 파일 업로드 방식을 쓰고
   싶다면 그 파일을 `docs/`에 직접 추가해도 된다(별도 코드 지원 불필요).
2. 소유 확인 후 `sitemap.xml` 제출(구글과 같은 파일 재사용).
3. 네이버 검색 로봇이 실제로 수집하는 데 14~16일 정도 걸린다고 알려져 있음. HTML
   태그 인증은 1년마다 재인증 필요.
4. 우선순위는 구글보다 낮게 — 이 항목은 시간 날 때 처리.

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
"주간 회고 SNS 홍보"와 같은 성격 — `PLAN.md` §14 참고). 원하면 Product Hunt
태그라인이나 Show HN 게시글 초안을 이후 별도로 써줄 수 있음 — 이번 구현 범위에는
포함하지 않았다.

## 5. 다음에 할 만한 것 (지금은 범위 밖)

- 날짜별 동적 OG 이미지(그날 헤드라인을 이미지에 직접 렌더) — Pillow를 파이프라인
  상시 의존성으로 추가해야 해서 지금은 보류.
- `llms.txt` — 표준화되면 재검토.
- 영어권 전용 착지 페이지(현재는 같은 페이지에서 언어 토글만 지원) — 필요성이 확인되면
  검토.
