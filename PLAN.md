# AI 뉴스 브리핑 자동화

## Context

사용자는 AI 관련 기사를 매일 자동으로 수집해서 각 기사의 "요약"과 "이 기사가 시사하는 점"을
보여주는 정적 웹페이지를 만들고, GitHub Pages로 자동 배포하고 싶어한다. 이 프로젝트는
`dhchun1203/business-trend-briefing`(유튜브 트렌드 자동 브리핑, Notion + PDF + 이메일 발송
기반)과 같은 설계 철학 — "검색/수집은 스크립트로 싸게, 의미 해석은 선별된 것만 Claude가
직접" — 을 따르는 자매 프로젝트지만, 결과물 형태(정적 웹페이지 vs PDF 이메일)와 저장소가
완전히 분리되어 있다.

목표: 사람 개입 없이 **매일 아침 8시(KST)** 에
1) `config/feeds.json`에 등록된 AI 뉴스 RSS 피드들을 순회해 최근 게시된 기사 중 출처
   다양성을 지키면서 상위 10개를 선별하고,
2) 선별된 10개만 Claude가 WebFetch로 원문을 직접 읽어 요약과 시사점을 작성하고,
3) 정적 HTML로 렌더링해 GitHub Pages에 배포한다.

## 조사 결과 요약 (설계 판단 근거)

| 영역 | 선택 | 이유 |
|---|---|---|
| 기사 수집 | **RSS 피드 직접 파싱** (`feedparser`), API 아님 | AI 뉴스는 전용 API가 거의 없고(TechCrunch, VentureBeat 등 대부분 언론사가 별도 뉴스 API를 공개하지 않음), 반대로 거의 모든 매체가 RSS는 무료·무인증으로 제공한다. NewsAPI 같은 서드파티 뉴스 API는 무료 티어가 하루 100회·개발용으로 제한되고 상업적 재배포에 제약이 있어, 매일 자동 실행되는 무인 파이프라인에는 RSS가 더 안정적이고 비용이 없다. |
| 원문 확보 | **선별된 10개만 WebFetch로 원문 정독** | RSS의 `summary`/`description` 필드는 매체마다 품질 편차가 크고(한두 문장짜리부터 광고성 문구까지) 그대로 쓰기엔 부실하다. 그렇다고 전체 후보 기사를 다 원문 fetch하면 실행 시간·비용이 커진다. `business-trend-briefing`이 "검색은 API로 싸게, 트렌드 해석은 Claude가 직접"했던 것과 동일하게, **1단계에서 스크립트로 10개까지 좁혀놓은 뒤에만** Claude가 원문을 읽는 2단계 구조로 비용을 통제한다. |
| 요약·시사점 작성 | **Claude가 직접 작성, 스크립트로 대체 불가** | "이 기사가 시사하는 점"은 사실 추출이 아니라 맥락 판단(왜 중요한지, 무엇을 예고하는지)이 필요한 영역이라 규칙 기반 스크립트로는 불가능하다. `business-trend-briefing`의 `narrative` 작성 단계와 같은 위치. |
| 결과물 형식 | **정적 HTML + Vercel** (PDF/이메일 아님) | 뉴스 브리핑은 매일 갱신되는 "지금 보는" 콘텐츠라 이메일 발송형 PDF보다는 웹페이지가 자연스럽고, 과거 기록도 아카이브 페이지로 계속 열람 가능해야 한다는 요구에 맞다. 배포는 사용자 선택으로 **Vercel**을 사용한다 — Vercel 대시보드에서 이 GitHub 저장소를 한 번 "Import"로 연결해두면(Git Integration), 이후 `main` 브랜치로 `git push`할 때마다 Vercel이 자동으로 재배포한다(`vercel.json`의 `outputDirectory: "docs"`가 정적 산출물 위치를 지정). GitHub Pages 대비 프리뷰 배포·롤백·커스텀 도메인 등 부가 기능이 있고, 이 환경에는 `gh` CLI가 없어 GitHub Pages를 API로 활성화할 수 없었던 반면 Vercel은 대시보드 연결만으로 충분하다. 이메일/Notion 저장 같은 별도 채널이 필요 없어 `business-trend-briefing`보다 구성 요소가 단순하다. |
| 데이터 저장 | **저장소 내 JSON 파일** (`data/`), 별도 DB/Notion 아님 | 매일 상위 10개 기사만 다루는 소규모 데이터라 DB가 필요 없고, 과거 기록은 `docs/archive/`의 정적 HTML 자체가 곧 아카이브 역할을 한다. `data/*.json`은 중간 산출물이라 git에는 포함하지 않는다. |
| 스케줄링 | **Claude Code Routines** (`schedule` 스킬) | `CronCreate`/`/loop` 기반 임시 작업은 일정 기간 후 만료되므로 반영구 매일 자동화에 부적합하다. Routine은 클라우드 인프라에서 영구적으로 cron 트리거(`0 23 * * *`, UTC 기준 매일 08:00 KST)로 실행되며, 저장소를 그대로 연결해 스킬 프롬프트 한 줄로 호출할 수 있다. |
| 이메일 구독자 저장소 | **Supabase**(Postgres, `subscribers` 테이블) | 사용자가 구독자 이메일을 "자신의 데이터"로 누적 보관하고 싶어해, 제3자 서비스(Resend Audiences 등)의 연락처 목록에만 맡기지 않고 직접 쿼리 가능한 테이블에 원본을 저장한다. PostgREST REST API를 SDK 없이 `fetch`/`urllib`로 직접 호출해 Vercel 서버리스 함수와 Python 스크립트 양쪽에서 의존성 추가 없이 접근한다. `service_role` 키로만 접근하고 RLS는 켜둔 채 정책을 두지 않아, 클라이언트에 노출되는 값은 전혀 없다. |
| 이메일 발송 | **Resend** (Contacts/Audiences 아님, 단순 발송 API만) | `business-trend-briefing`에서 이미 검증된 서비스라 계정을 재사용할 수 있다. 구독자 목록의 진실 소스는 Supabase이므로 Resend는 순수 발송 도구로만 쓴다 — 매일 `POST /emails/batch`(최대 100통씩)로 확인된 구독자 전원에게 보낸다. 확인 메일(더블 옵트인)은 `POST /emails`로 단건 발송. 임의 수신자에게 보내려면 샌드박스 발신 주소(`onboarding@resend.dev`)로는 불가능해 **발신 도메인 인증이 필수**다. |
| 구독 확인 방식 | **더블 옵트인(이메일 확인 링크), 별도 저장소 없는 HMAC 서명 토큰** | 사용자가 스팸/오남용 방지를 위해 더블 옵트인을 선택했다. 확인 대기 상태를 별도 테이블/캐시에 저장하는 대신, `email + 만료시각`을 서버 비밀키로 HMAC-SHA256 서명한 토큰을 확인 링크에 담아 보낸다 — 클릭 시 서명을 재계산해 비교하는 것만으로 검증이 끝나 상태 저장이 필요 없다. 구독취소 링크도 같은 방식(만료 없는 서명)을 재사용해 별도 인프라 추가 없이 구현했다. |
| 구독 폼 백엔드 | **Vercel 서버리스 함수** (`api/*.js`, 의존성 없는 순수 `fetch` 호출) | 이미 Vercel에 배포 중이라 별도 서버 호스팅이 필요 없다. `outputDirectory: "docs"` 정적 배포 설정과 무관하게 `api/` 폴더는 Vercel이 자동으로 서버리스 함수로 인식한다. Node 18+ 런타임의 전역 `fetch`만 사용해 `package.json`/`node_modules` 없이 3개 함수(`subscribe`, `confirm`, `unsubscribe`)를 구현했다. |
| 과거 기록 저장 방식 | **원본 digest를 `docs/archive/<날짜>.json`으로 git에 영구 보관** (별도 DB 아님) | `data/*.json`은 매 Routine 실행이 끝나면 사라지는 임시 파일이라, "과거 중복 기사 제외"·"아카이브 검색"·"주간 회고"처럼 여러 날짜에 걸친 데이터가 필요한 기능들이 참조할 영속적인 소스가 없었다. `docs/`는 이미 매일 git에 커밋되므로, 그날의 순수 원본 digest(글로서리 링크화 이전)를 같은 폴더에 `.json`으로 함께 남기면 별도 DB 없이 세 기능이 전부 이 파일들만 읽어서 동작한다. |
| 과거 기사 중복 방지 | **링크 기준 정확 일치 제외** (`fetch_articles.py`가 `docs/archive/*.json` 스캔) | 다른 날짜에 이미 다룬 기사가 recency 기준 후보 목록에 다시 걸릴 수 있어, 링크(URL)가 과거 아카이브에 이미 존재하면 후보 단계에서 아예 제외한다. 기계적으로 판단 가능한 조건이라 스크립트가 처리하고 Claude 판단이 필요 없다. |
| 화제성(교차 출처) 감지 | **제목 키워드 겹침 기반 휴리스틱** (임베딩/NLP 없이 정규식) | "여러 매체가 동시에 다루는 사건"을 우선 노출하고 싶었는데, 임베딩 유사도 같은 정교한 방법은 추가 라이브러리·API 비용이 든다. 대신 제목에서 대문자로 시작하는 고유명사 추정 단어(2글자 이상)와 4자리 이상 숫자(버전·연도)를 뽑아, 서로 다른 출처가 같은 키워드를 공유하면 우선순위를 올리는 가벼운 휴리스틱으로 충분히 효과를 봤다(실제 검증 시 "Gemini 3.6 Flash 출시"가 MarkTechPost·Ars Technica 양쪽에서 잡혀 자연스럽게 상위로 올라옴). |
| 소스 배지(공식 발표/보도/커뮤니티) | **`config/feeds.json`의 `type` 필드를 스크립트가 기계적으로 매핑** | 헤더 미션 문구에 이미 "공식 발표 vs 언론 보도 vs 커뮤니티"를 구분한다고 써놨는데 실제 카드에는 안 드러나던 걸 보완했다. 이 분류는 피드 목록에서 이미 정해지는 사실이라 Claude가 매번 판단할 필요 없이 `generate_site.py`가 `article.source`로 조회만 하면 된다. |
| 아카이브 검색 | **클라이언트 사이드 검색** (`docs/search-index.json`, 서버 없음) | 아카이브가 쌓일수록 "그때 그 기사"를 찾을 방법이 없었다. 정적 사이트라 서버 검색 API를 새로 만들기보다, `docs/archive/*.json` 전체를 합친 가벼운 인덱스 파일 하나를 만들어 브라우저에서 `fetch` 후 JS로 필터링한다. 검색창 포커스 시 지연 로드(lazy load)해서 평소 페이지 로딩에는 영향이 없다. |
| 주간 회고 | **Claude가 매주 일요일 조건부로 종합, 일별 헤드라인 수집은 스크립트** | 매일 브리핑만으로는 "이번 주 전체 흐름"을 놓치기 쉬웠다. `SKILL.md`에 일요일에만 실행되는 조건부 단계를 추가해, 그 주 `docs/archive/*.json`의 `daily_insight`들을 Claude가 다시 종합(사실 나열이 아니라 새로운 판단)하고, 일별 헤드라인 나열 자체는 `generate_weekly_site.py`가 기계적으로 수집한다 — "해석은 Claude, 나열은 스크립트" 원칙을 여기서도 유지. |

## 아키텍처

```
[Claude Code Routine: 매일 08:00 KST]
        │
        ▼
/ai-news-briefing (프로젝트 스킬, 이 저장소에 정의)
        │
        ├─ 1. scripts/fetch_articles.py
        │     - config/feeds.json의 RSS 피드들을 feedparser로 순회
        │     - 최근(기본 12일) 게시된 기사만 필터링
        │     - docs/archive/*.json에 이미 있는 링크(과거에 다룬 기사)는 후보에서 제외
        │     - 제목 키워드가 겹치는(여러 출처가 동시에 다루는) 후보를 우선순위로 올린 뒤,
        │       출처당 최대 3개로 제한하며 상위 10개 선별
        │     - 출력: data/articles_<날짜>.json
        │
        ├─ 2. Claude가 선별된 10개만 WebFetch로 원문을 직접 읽는다
        │     (RSS 요약만으로는 부실 → 전체 피드 원문 fetch는 비효율 →
        │      "이미 선별된 10개만" 정독)
        │
        ├─ 3. Claude가 기사별로 직접 작성 (스크립트로 대체 불가):
        │     - summary: 2~3문장 요약
        │     - implication: 이 기사가 시사하는 점 1~2문장
        │     - daily_insight: 10개를 가로지르는 크로스컷 종합
        │     - glossary: 비개발자가 모를 법한 용어 + 쉬운 설명
        │     → data/digest_<날짜>.json
        │
        ├─ 4. scripts/generate_site.py
        │     - Jinja2로 정적 HTML 렌더링 (제목/출처/날짜/배지 → 요약 → 시사점 순서)
        │     - docs/index.html(오늘자) 생성
        │     - docs/archive/<날짜>.html + <날짜>.json(원본 영구 보관)로 과거 기록 누적
        │     - docs/archive/*.json을 모아 docs/search-index.json(아카이브 검색용) 갱신
        │     - docs/index.html 하단에 지난 아카이브 링크·검색창·주간 회고 목록 추가
        │
        ├─ 5. (일요일에만) Claude가 그 주 docs/archive/*.json의 daily_insight를 다시
        │     종합해 data/weekly_<주차>.json 작성 → scripts/generate_weekly_site.py 실행
        │     → docs/weekly/<주차>.html 생성 (일별 헤드라인 목록은 스크립트가 기계적으로 수집)
        │
        ├─ 6. git add/commit/push → Vercel Git Integration이 main 브랜치를 감지해 자동 재배포
        │     (vercel.json의 outputDirectory: "docs" 기준 정적 배포)
        │
        └─ 7. scripts/send_broadcast.py
              - Supabase subscribers 테이블에서 confirmed_at IS NOT NULL AND
                unsubscribed_at IS NULL 인 이메일만 조회
              - 기사 제목+한 줄 요약+링크로 구성한 가벼운 HTML을 Resend
                POST /emails/batch(최대 100통씩)로 발송 (시사점은 제외, 전체 브리핑
                링크로 유도)
```

이메일 구독(신청/확인/구독취소)은 위 매일 파이프라인과 별개로, 사이트 방문자가 언제든
트리거하는 흐름이다:

```
[방문자가 구독 폼에 이메일 입력]
        │
        ▼
POST /api/subscribe (Vercel 서버리스 함수)
        │
        ├─ Supabase subscribers에 upsert (아직 confirmed_at 없음)
        └─ Resend POST /emails로 확인 링크 발송 (HMAC 서명 토큰, 24시간 유효)
                │
                ▼ (사용자가 메일의 링크 클릭)
        GET /api/confirm?email=&expiry=&token=
                │
                └─ 서명 검증 통과 시 Supabase subscribers.confirmed_at 갱신
                   → 다음날 아침부터 발송 대상에 포함됨

[구독취소] 매일 이메일 하단 링크 → GET /api/unsubscribe?email=&token=
        (만료 없는 서명 토큰) → Supabase subscribers.unsubscribed_at 갱신
```

## 구성 요소

### 1. RSS 피드 목록 (`config/feeds.json`)
검증 완료(2026-07-23, WebFetch/curl로 200 응답 + 유효한 RSS/Atom 구조 + 최근 item 존재
확인): TechCrunch AI, VentureBeat AI, The Verge AI, MarkTechPost, OpenAI News, Google
DeepMind Blog, Google AI Blog, Ars Technica AI, Wired AI, MIT Technology Review AI,
Hacker News(AI 키워드, hnrss.org). 자유롭게 추가/삭제 가능.

**Anthropic 블로그는 제외했다** — `anthropic.com/rss.xml` 등 후보 URL을 모두 검증했으나
2026-07-23 기준 공식 RSS 피드를 제공하지 않는다(전부 404, 페이지 소스에도 `rss`/`feed`
link 태그 없음). 향후 Anthropic이 RSS를 공개하면 `config/feeds.json`에 추가한다.

### 2. digest 스키마 (`data/digest_<날짜>.json`)
`date`, `generated_at`, `articles[]`(title, link, source, published_at,
summary_ko/en, implication_ko/en), 선택 필드 `daily_insight`(headline_ko/en,
paragraphs_ko/en, watch_ko/en), 선택 필드 `glossary[]`(term_ko, term_en, explanation_ko/en).
기사별 요약·시사점, `daily_insight`(10개 기사를 가로질러 읽어 종합한 "오늘의 인사이트"),
`glossary`(꼭 필요한 전문용어와 쉬운 설명)는 모두 Claude가 SKILL.md 3단계에서 직접
작성한다. `daily_insight`가 없는 날은 사이트에서 인사이트 섹션 자체가 렌더링되지 않는다.

**용어 설명(glossary)**: 요약·시사점·인사이트는 전문용어 없이 쉬운 말로 쓰는 게 기본
원칙이고, 도저히 대체할 수 없는 핵심 용어만 `glossary`에 등록한다. `generate_site.py`가
본문에서 그 용어(`term_ko`/`term_en`과 정확히 같은 표기)를 자동으로 찾아 클릭 가능한
버튼으로 바꾸고, 클릭하면 화면 우측에 슬라이드 패널이 열려 쉬운 설명(`explanation_ko/en`)을
보여준다. Claude는 별도 마크업 없이 `glossary`만 채우면 되고, 실제 HTML 삽입(정규식으로
용어를 찾아 이스케이프 후 안전하게 감싸는 처리)은 스크립트가 담당한다.

### 3. 프로젝트 스킬: `.claude/skills/ai-news-briefing/SKILL.md`
전체 워크플로(수집 → 원문 정독 → 요약/시사점 작성 → 사이트 생성 → 배포)를 하나의 스킬로
정의해 Routine 프롬프트가 `/ai-news-briefing` 한 줄만 호출하면 되도록 구성.

### 4. 웹페이지 템플릿 (`templates/site.html.j2` + CSS 3분할)
기사 카드 순서: 제목(원문 링크) + 출처/날짜 → 요약 → 시사점(강조 박스). 라이트/다크 모드
대응. `docs/index.html`과 `docs/archive/<날짜>.html`이 같은 템플릿을 공유하며, 아카이브
페이지에는 "오늘자 브리핑 보기" 링크가 추가된다.

CSS는 PC/모바일 화면별 가독성을 각각 최적화하기 위해 3개 파일로 분리했다:
- `site-base.css`: 색상 변수, 리셋, 화면 크기와 무관한 구조(카드 배경/테두리, 색상 등)
- `site-mobile.css`: `media="(max-width: 767px)"`로 조건부 적용. 본문 16px 이상 유지,
  줄간격 1.75로 넓게, 카드 좌우 여백을 좁혀 화면 폭을 최대한 활용
- `site-desktop.css`: `media="(min-width: 768px)"`로 조건부 적용. 본문 폭을 760px로 제한해
  한 줄이 너무 길어지지 않게 하고, 카드에 hover 반응 추가

`<link>` 태그 3개를 모두 `<head>`에 넣어두면 브라우저가 뷰포트에 맞는 stylesheet만
활성화한다. `generate_site.py`가 세 파일 모두 `docs/`로 복사한다.

### 5. 배포 설정 (`vercel.json`)
빌드 스텝이 없는 순수 정적 사이트이므로 `vercel.json`에 `"outputDirectory": "docs"`만
지정한다. Vercel 프로젝트와 GitHub 저장소를 연결하는 것은 OAuth 기반 대시보드 작업이라
자동화 에이전트가 대신할 수 없는 유일한 수동 단계다 (아래 "사용자가 직접 준비해야 하는 것"
참고). 연결 이후에는 push만으로 100% 무인 배포된다.

### 6. Claude Code Routine 설정
- Repository: 이 `ai-news-briefing` 저장소
- Environment: RSS 수집 자체는 API 키 불필요. 이메일 구독 발송(`send_broadcast.py`)을 쓰려면
  `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `RESEND_API_KEY`, `RESEND_SENDER_EMAIL`,
  `SUBSCRIBE_TOKEN_SECRET`, `SITE_URL` 6개를 Environment에 등록해야 한다. Setup script는
  필요 없다 — `pip install -r requirements.txt`는 저장소 체크아웃 이후 SKILL.md 0단계에서
  Claude가 세션 안에서 직접 실행한다(Setup script는 체크아웃 이전에 돌아 파일이 없어 실패).
- Trigger: Scheduled, 매일 08:00 KST (cron: `0 23 * * *`, UTC 기준)
- Prompt: `/ai-news-briefing`

### 7. Supabase 구독자 테이블 (`supabase/schema.sql`)
`subscribers(id, email unique, created_at, confirmed_at, unsubscribed_at)` 한 테이블로
충분하다. RLS는 켜두되 정책을 추가하지 않아 `service_role` 키를 가진 서버(Vercel 함수,
`send_broadcast.py`)만 접근 가능하고 `anon` 키로는 아무 것도 볼 수 없다.

### 8. Vercel 서버리스 함수 (`api/subscribe.js`, `api/confirm.js`, `api/unsubscribe.js`)
공통 로직은 `api/_lib/`에 모았다: `tokens.js`(HMAC 서명/검증), `supabase.js`(PostgREST
REST 호출), `page.js`(확인/구독취소 결과 안내 페이지). 세 함수 모두 npm 패키지를 쓰지 않고
Node 18+ 전역 `fetch`만으로 Resend·Supabase REST API를 직접 호출한다 — `package.json`이나
`node_modules` 없이 그대로 배포된다.

### 9. 구독 폼 UI 및 이메일 템플릿
사이트 본문 상단(`.subscribe-box`)에 이메일 입력 폼을 두고, 제출 시 `fetch("/api/subscribe")`
로 비동기 요청해 페이지 새로고침 없이 상태 메시지(전송 중/확인 메일 발송됨/오류)를 보여준다.
확인 메일과 매일 다이제스트 메일은 각각 `api/subscribe.js`, `scripts/send_broadcast.py`
안에 인라인 HTML 문자열로 작성했다(별도 이메일 템플릿 엔진 없이 f-string/템플릿 리터럴).

### 10. RSS 소스 타입 (`config/feeds.json`의 `type` 필드)
각 피드에 `primary`(OpenAI News, Google DeepMind Blog, Google AI Blog — 기업 공식 발표),
`press`(TechCrunch, VentureBeat, The Verge, MarkTechPost, Ars Technica, Wired, MIT
Technology Review — 언론·기술 매체 보도), `community`(Hacker News — 커뮤니티 링크 모음)
중 하나를 붙여둔다. `generate_site.py`가 기사의 `source`로 이 값을 조회해 카드에 배지로
표시한다 — 새 피드를 추가할 때 이 값도 함께 정해줘야 배지가 정확하다.

### 11. 아카이브 영구 보관 + 검색 (`docs/archive/<날짜>.json`, `docs/search-index.json`)
`generate_site.py`가 매일 그날의 원본 digest(글로서리 링크화 이전, 순수 텍스트)를
`docs/archive/<날짜>.json`으로 함께 저장한다. `data/*.json`과 달리 `docs/`는 매번 git에
커밋되므로 이 파일들이 유일하게 "여러 날짜에 걸친 데이터"를 담는 영속 저장소 역할을 한다.
같은 스크립트가 `docs/archive/*.json` 전체를 훑어 `docs/search-index.json`(제목+요약+링크
+날짜만 담은 가벼운 배열)도 매번 다시 만든다(항상 archive 폴더 전체에서 재생성하므로
멱등적). 사이트의 검색창은 이 파일을 `fetch`해 브라우저에서 부분 문자열로 필터링한다.

### 12. 과거 기사 중복 방지 + 화제성 감지 (`scripts/fetch_articles.py`)
`load_published_links()`가 `docs/archive/*.json`에서 지금까지 다룬 모든 링크를 모아,
새 후보 중 이미 등장한 링크는 아예 제외한다. `compute_cross_source_counts()`는 제목에서
고유명사 추정 키워드(대문자 시작 단어, 4자리 이상 숫자)를 뽑아 서로 다른 출처가 같은
키워드를 공유하는 후보의 우선순위를 올린다 — 정렬 키를 `(cross_source_count, published_at)`
내림차순으로 바꿔, 여러 매체가 동시에 다루는 사건이 최신순보다 먼저 오도록 한다.

### 13. 주간 회고 (`scripts/generate_weekly_site.py`, `templates/weekly.html.j2`)
매주 일요일에만 `SKILL.md`가 조건부로 실행하는 단계. Claude가 그 주
`docs/archive/*.json`의 `daily_insight`들을 읽고 한 주를 관통하는 흐름을 새로 종합해
`data/weekly_<ISO 주차>.json`(headline/paragraphs만, 예: `2026-W30`)을 작성하면,
스크립트가 그 주 날짜 범위의 일별 헤드라인 목록을 `docs/archive/*.json`에서 기계적으로
모아 `docs/weekly/<주차>.html`을 렌더링한다. `generate_site.py`는 `docs/weekly/*.html`을
스캔해 메인 페이지 하단에 "주간 회고" 링크 목록을 추가한다.

### 14. 주간 회고 어필 강화 (신규 독자 유입 우선 — 공개+공유 방향)
주간 회고를 구독자 전용으로 가둘지(subscriber-gating) 고민했으나, 정적 사이트에는 실제
접근 제어(로그인)가 없어 클라이언트에서 숨기는 방식은 가짜 보안이고, 서버리스+인증을
새로 얹는 것은 이 프로젝트 규모에 비해 과하다고 판단했다. 신규 독자 유입이 우선이라는
판단에 따라 **공개 + 공유 가능**하게 유지하고, 대신 아래 세 가지로 존재감을 강화한다:
- **구독 폼 문구**: `templates/site.html.j2`의 `.subscribe-desc`가 매일 발송뿐 아니라
  "매주 일요일 종합 회고"도 받는다는 점을 명시해, 구독 전환 시점에 주간 회고의 가치를
  같이 어필한다.
- **일요일 이메일 티저**: `scripts/send_broadcast.py`가 `--weekly-input`으로 그 주
  `data/weekly_<주차>.json`을 받으면, 이메일 최상단(일별 인사이트 티저보다 먼저)에
  "이번 주 종합" 헤드라인 + 회고 전체보기 링크를 추가한다(`build_weekly_teaser_block`).
  `SKILL.md` 7단계에서 5단계(주간 회고 생성)를 실행한 날에만 이 옵션을 붙이도록 안내한다.
- **사이트 상단 배너**: `generate_site.py`가 오늘 날짜의 요일을 계산해(`weekday()`),
  일요일·월요일에만(`show_weekly_banner`) `docs/index.html` 상단에 최신 주간 회고로
  연결되는 배너(`.weekly-banner`)를 노출한다. 회고는 일요일 사이트 생성 "이후"에
  만들어지므로 실제로는 다음날(월요일)부터 그 주 회고가 뜨는 것이 의도된 동작이다.
  과거 기록 페이지(`docs/archive/<날짜>.html`)에는 그 시점 기준 배너가 의미 없으므로
  넣지 않는다.
- **SNS 홍보(사용자 직접 수행)**: 주간 회고 페이지 자체를 SNS에 공유해 신규 독자를
  끌어오는 방법은 자동화 대상이 아니라 사용자가 직접 계획해서 실행하는 항목이다 —
  아래 "사용자가 직접 준비해야 하는 것" 6번 참고. 구체적인 홍보 방법(어느 채널에, 어떤
  문구로, 얼마나 자주)은 아직 정해지지 않았고 사용자가 나중에 구체화할 계획이다.

### 15. 발송 신뢰성 — 실패 대응 (2026-07-24 Supabase 발송 장애 이후 추가)
2026-07-24 아침, 파이프라인은 정상 완료됐지만 `send_broadcast.py`만 Supabase
접속이 이 Routine Environment의 네트워크 허용 목록에 없어 403으로 실패했다.
문제 자체(도메인 미등록)는 사람이 직접 고쳐야 했지만, "구독자는 매일 08:00에
이메일이 온다"는 약속을 지키려면 이런 실패가 재발해도 사람이 우연히 로그를 보기
전까지 아무도 모르는 상황은 없어야 한다는 요구가 나왔다. 세 겹의 방어로 대응한다:
- **일시적 오류는 스크립트가 자동 재시도** (`send_broadcast.py`의
  `urlopen_with_retry()`): Supabase/Resend 호출에서 연결 실패·5xx만 최대 3회
  지수 백오프로 재시도한다. 401/403/404 같은 4xx(인증·설정 문제)는 재시도해도
  결과가 안 바뀌므로 즉시 실패 처리한다 — 재시도가 설정 문제를 감추면 안 되기
  때문이다.
- **발송 성공 여부를 영속 기록** (`mark_sent()` → `docs/archive/<날짜>.sent.json`):
  발송이 실제로 끝난 날짜(구독자 0명이었던 날 포함)에만 이 마커가 남는다. 이게
  "그날 이메일이 실제로 나갔는가"의 유일한 진실 소스다 — 구독자 목록은 Supabase에
  있지만 "며칠치가 발송됐는지"는 어디에도 기록이 없었던 게 이번 장애를 늦게
  알아차린 원인 중 하나였다.
- **다음 실행이 자동으로 밀린 발송을 보정** (`SKILL.md` 7-1단계): 매일 실행 시
  오늘을 보내기 전에 최근 2일 이내 `docs/archive/<날짜>.json`은 있는데
  `<날짜>.sent.json`이 없는 날이 있는지 먼저 확인하고, 있으면 `--catchup` 옵션으로
  먼저 보정 발송한다(이메일 상단에 지연 안내 문구 자동 삽입). 3일 넘게 지난 미발송은
  신선도 문제로 자동 발송하지 않고 사람 판단에 맡긴다.
- **모든 단계 실패는 `PushNotification`으로 즉시 알림** (`SKILL.md` 서두 원칙): 특히
  7단계(발송) 실패는 최우선 알림 대상 — 완료 보고 텍스트만으로는 사람이 그날 안에
  못 볼 수 있다.
- **부수 효과 — Routine 중복 발동 방어**: 같은 날 조사하다가 이 Routine이 그날 두 번
  발동한 사실도 발견했다(원인 미상, 재발 시 조사 필요). 세션이 스스로 "오늘자가
  이미 커밋돼 있다"를 보고 파이프라인 재실행/중복 발송을 스스로 막았는데, 이 판단을
  우연에 맡기지 않고 `SKILL.md` 0단계에 "오늘자가 이미 있으면 처음부터 다시 돌리지
  말고 무엇이 빠졌는지만 확인"하는 규칙으로 명문화했다.
- **`docs/archive/`에 `.json`(원본 digest)과 `.sent.json`(발송 마커) 두 종류 파일이
  섞이는 것에 대한 방어**: `generate_weekly_site.py`의 `collect_daily_briefings()`,
  `generate_site.py`의 `build_search_index()`, `fetch_articles.py`의
  `load_published_links()` 모두 `docs/archive/*.json`을 스캔하므로, `.sent.json`을
  명시적으로 건너뛰게 처리했다(특히 `collect_daily_briefings()`는 `f.stem`이
  `"<날짜>.sent"`가 되면서 날짜 범위 비교에 걸려 주간 회고에 헤드라인 없는 빈 항목이
  섞여 들어가는 실제 버그가 있었다 — 수정 후 테스트로 확인).

### 16. SEO/GEO 기술 인프라 (`scripts/seo_utils.py`)
검색엔진(구글/네이버)과 생성형 AI 답변엔진(ChatGPT/Perplexity 등) 양쪽에 노출되기
위한 `robots.txt`/`sitemap.xml`/canonical/`og:image`/JSON-LD 구조화 데이터를 매 실행마다
자동 생성한다. GEO(생성형 AI 검색 최적화)를 SEO보다 우선 강화하기로 한 결정, 리서치
근거, 구글/네이버 등록 체크리스트, 해외(영어권) 커뮤니티 노출 전략은 별도 문서
[`MARKETING.md`](MARKETING.md)에 정리했다 — 이 문서(PLAN.md)는 아키텍처 이유만
간단히 남긴다: (1) 이 사이트는 원문 기사의 저작자가 아니라 큐레이션/분석 주체이므로
JSON-LD에서 원문을 `NewsArticle`로 직접 마크업하지 않고 우리 자체 분석문만
`Article`/`CollectionPage`로 표시하고 원문은 `citation`으로 분리했다. (2) sitemap은
`search-index.json`과 같은 멱등적 전체 재빌드 패턴을 따른다.

### 17. 날짜별 동적 OG 이미지 (`scripts/og_image.py`)
그날 `daily_insight` 헤드라인을 1200×630 이미지에 렌더링해 `docs/og/<날짜>.png`로
저장하고 그 페이지의 `og:image`가 이걸 가리키게 한다. 매일 자동 실행되는 파이프라인에
이미지 렌더링(Pillow)이라는 새 실패 지점이 생기는 것 자체가 우려였는데,
`seo_utils.build_og_image_url()`이 어떤 실패든(Pillow 미설치, 폰트 손상 등) 예외를
전부 삼키고 기존 정적 `og-image.png`로 조용히 대체하도록 설계해 해결했다 — 부가
기능 하나 때문에 그날의 사이트 생성 전체가 막히면 안 된다는 원칙. 한글 렌더링용
폰트(`templates/static/fonts/NotoSerifKR-Variable.ttf`)는 어느 실행 환경에서도
동일하게 렌더링되도록 저장소에 직접 커밋했다(OS에 폰트가 설치돼 있는지에 의존하지
않기 위해) — 전체 CJK 통합 폰트(56MB)가 아니라 한국어 서브셋(23MB)만 받아 용량을
줄였다.

### 18. AI 용어사전 (`docs/glossary.html`, `templates/glossary.html.j2`)
매일 3단계에서 이미 작성하던 glossary 설명을 그날 브리핑에서만 쓰고 버리지 않고,
`docs/archive/*.json`(이번에 `glossary` 필드를 새로 영구 보관하도록 확장)에서 전부
모아 하나의 독립 페이지로 만든다. 검색-인덱스(`build_search_index`)와 같은 성격의
"판단 없이 매번 기계적으로 다시 만드는" 집계라, 주간 회고와 달리 Claude가 매일 따로
결정할 게 없다. 같은 용어가 여러 날 다시 등장하면 파일명(날짜) 순으로 순회해 가장
최근 설명으로 자동 갱신한다(과거 버전은 보존하지 않음 — 용어 설명은 다듬어질수록
좋다고 보고 최신판만 남긴다). `schema.org`의 `DefinedTermSet`/`DefinedTerm`으로
마크업했다(§16의 `Article`/`CollectionPage`보다 정의문 콘텐츠에 더 정확히 맞는
타입). 기사 페이지와는 분리하되(사용자 요청), 상단 유틸리티 바에 상시 링크를 둬서
발견 가능성을 확보했다.

### 19. 영어권 착지 페이지 (`/en/`)
기존엔 한 페이지에서 언어 토글만 지원해서(URL은 하나), 검색결과나 외부 링크로
들어온 영어권 방문자도 한국어 제목·설명을 먼저 보는 문제가 있었다. `docs/en/
index.html`을 같은 digest로 `default_lang="en"`만 다르게 매일 추가 생성해
해결했다 — 이미 두 언어로 쓰는 콘텐츠라 새로 작성할 게 없다. 설계 결정 두 가지:
(1) 아카이브/주간 회고/용어사전까지 전부 `/en/` 아래로 미러링하지 않았다 —
`/en/`에 착지하면 언어 선택을 `localStorage`에 저장해두고, 그 값을 다른
(이미 토글을 지원하는) 페이지들이 그대로 읽어서 자동으로 영어를 유지하기
때문에 필요 없었다. (2) `/`와 `/en/`을 `hreflang` 상호 참조로 연결해 구글에
"같은 콘텐츠의 언어 버전"이라고 명시했다 — 이게 없으면 사실상 내용이 겹치는
두 URL로 오인될 수 있었다. 리서치/전략 배경은 `MARKETING.md` §6 참고.

### 20. UX 개선 (WCAG/WAI-ARIA/Baymard·NNG 리서치 기반)
코드 감사 + 신뢰도 높은 자료 리서치 후 근거 있는 항목만 반영했다: 구독 폼을
"오늘의 인사이트" 아래로 이동(가치를 먼저 보여준 뒤 요청 — 관련 A/B 테스트에서
전환율이 크게 오른 사례 다수), 스킵 링크(WCAG 2.4.1), 인터랙티브 버튼류 공통
`:focus-visible` 스타일, 모바일 터치 타겟을 44px 기준에 가깝게 확대(WCAG
2.5.5/2.5.8, Apple HIG·Material Design), 언어 드롭다운 화살표 키 탐색(WAI-ARIA
Authoring Practices — 옵션이 2개뿐이라 풀 콤보박스 패턴 대신 단순화), 용어
패널에 포커스 트랩+복귀 추가(모달류 공통 원칙 — 열릴 때 포커스 이동, 닫히면
트리거로 복귀), "지난 브리핑"/"주간 회고" 시각적 구분, 아카이브 검색 로딩 상태,
유틸리티 바 좁은 화면 `flex-wrap` 안전장치. 데스크톱 줄 길이 문제(Baymard/NNG —
50~75자가 최적)는 처음엔 문단 요소에만 `max-width: 68ch`를 걸었다가, 사용자가
그 때문에 헤더/구독 박스 컨테이너 폭과 어긋나 보인다고 지적해 문단 레벨 제한을
걷어내고 `.header-inner`/`.content` 컨테이너 자체를 720px로 통일하는 방식으로
바꿨다(이후 커밋에서 반영, 별도 절 없이 여기 기록). 같은 피드백에서 한국어
`word-break: keep-all`(+`overflow-wrap: break-word`) 부재도 지적받아 `body`에
추가 — 한국어 어절이 중간에서 끊기지 않게 한다(영어 등 비-CJK엔 영향 없음).
검토했지만 반영하지 않은 것: `/en/`의 언어 선호 덮어쓰기(의도된 설계, §19),
폰트 파일 `preload`(자체 호스팅 필요해 비용 대비 효과 낮음), 시스템 다크모드
자동 반영(이전에 사용자가 명시적으로 거부).

### 21. 디자인 개선 (NYT 테마 유지, 60-30-10/8pt 그리드/Material 다크모드 리서치 기반)
"UX(접근성)"와는 별개로 순수 시각적 다듬기. Eyebrow(대문자+자간) 라벨의
letter-spacing을 accent 라벨(0.1em)과 무채색 라벨(0.06em) 2단계로 통일, 여백을
8px 그리드로 반올림, `--accent`를 오늘의 인사이트·용어 링크·포커스 링에만
남기고 TOC/아카이브/검색결과 hover·주간 회고 배너·공식발표 배지에서는 제거해
accent가 나올 때 더 도드라지게 함(60-30-10 색상 규칙), `.source-badge`/
`.archive-badge`가 공유하는 `.badge` 베이스 클래스 도입, 다크모드에서 순수
검정 배경 위 검은 그림자가 안 보이던 term-panel/lang-select-list/
archive-search-results를 `--implication-bg`로 한 단계 밝게(Material 다크모드
elevation 가이드), 오늘의 인사이트 첫 문단에만 신문풍 드롭캡(`::first-letter`,
전체 기사에 적용하면 산만해져 하루 하나뿐인 자리에만), 예상 읽기 시간 표시
(한국어는 음절 수, 영어는 단어 수로 따로 계산 — `scripts/generate_site.py`의
`estimate_reading_minutes()`, 글로서리 마크업 섞이기 전 raw_digest 기준).
링크 밑줄 3종(일반/용어/제목)은 의미 있는 구분이라 통일하지 않았고, 전체 폰트
크기의 모듈러 스케일 재계산은 위험 대비 이득이 낮아 보류.

### 22. bfcache 복원 시 테마/언어 재동기화 버그 수정
용어사전에서 언어를 바꾼 뒤 뒤로가기로 기사 페이지에 돌아오면 브라우저가
bfcache(back-forward cache)에서 페이지를 그대로 복원해 head의 인라인
FOUC 방지 스크립트가 재실행되지 않고, 그 결과 테마/언어가 "떠날 때 상태"로
얼어붙는 문제가 있었다. `window.addEventListener("pageshow", ...)`에서
`event.persisted === true`일 때만 쿠키(`theme`)/`localStorage`(`lang`) 값으로
다시 동기화하도록 `site.html.j2`/`weekly.html.j2`/`glossary.html.j2` 3개
템플릿 모두에 추가. 렌더링 후 `node --check`로 12개(3템플릿 × 2스크립트블록 ×
ko/en) 변형 전부 문법 검증 완료.

### 23. 용어사전 연결 그래프 ("용어 지도")
용어사전에 쌓인 개념들 간의 연관관계를 시각화해 달라는 요청. 텍스트 co-occurrence로
자동 추론하는 대신(설명이 1~2문장이라 성기게 나옴), **Claude가 누적된 전체 용어사전을
보고 의미적으로 판단**해 `docs/glossary-relations.json`(`{"edges": [[term_ko_A,
term_ko_B], ...]}`)을 갱신하는 방식을 택함 — 오늘 새 용어가 추가된 날에만 전체를
다시 판단하도록 해 비용을 억제(`.claude/skills/ai-news-briefing/SKILL.md` 4단계에
추가). `generate_site.py`의 `load_glossary_relations()`가 이 파일을 읽어(없거나
손상돼도 빈 배열로 안전 폴백, 사라진 용어를 가리키는 낡은 엣지는 필터링) `docs/
glossary.html`에 `graph_data`/`term_lookup`으로 전달한다.

렌더링은 외부 라이브러리 없이 순수 JS로 구현한 아주 단순한 force-directed 레이아웃
(상호 반발력 + 엣지 스프링 + 중앙 정렬력 + 약한 무작위 흔들림)이며, 노드는 실제
`<button>`이라 클릭/키보드/스크린리더가 그대로 동작한다 — 그래프는 아래 이미 있는
접근성 있는 전체 목록의 시각적 보조 수단일 뿐이라 그래프가 실패하거나 안 보여도
정보 손실이 없다. 클릭 시 기존 `term-panel` 컴포넌트(`site.html.j2`에서 쓰던 것과
동일한 CSS/구조)를 재사용해 설명을 보여준다. `prefers-reduced-motion`이면 계속
흔들리는 애니메이션 대신 150회 반복으로 한 번만 레이아웃을 계산해 정지 상태로
보여준다. 용어가 2개 미만이면 그래프 자체를 렌더링하지 않는다.

용어 8개 기준 부트스트랩 관계는 이번에 직접 판단해 커밋(예: "AI 에이전트"↔"가드레일",
"자본적 지출"↔"잉여현금흐름"). 색상은 60-30-10 규칙(§21)에 맞춰 엣지/기본 노드는
무채색(`--border`/`--text`)으로 두고 accent는 hover/focus에만 준다.

## 사용자가 직접 준비해야 하는 것 (자동화로 대신 못 하는 부분)
1. vercel.com 계정으로 로그인 후 "Add New... → Project"에서 `dhchun1203/ai-news-briefing`
   저장소를 Import (OAuth 기반 GitHub 연동이라 에이전트가 대신할 수 없음). Framework Preset은
   "Other"로 두면 저장소 루트의 `vercel.json`(`outputDirectory: "docs"`)을 그대로 인식한다.
2. Claude Code Routines 기능 접근 권한 확인(플랜에 따라 제공 여부 상이)
3. Supabase 프로젝트 생성 + `supabase/schema.sql` 실행 + `service_role` 키 발급 (계정
   생성이 필요해 에이전트가 대신할 수 없음)
4. Resend 발신 도메인 인증(DNS 레코드 추가) — 임의의 구독자 이메일로 발송하려면 필수이며
   도메인 소유권 증명이 필요해 사람이 직접 해야 한다
5. 위에서 나온 6개 환경변수를 Vercel 프로젝트 설정과 Claude Code Routine Environment
   **양쪽 모두**에 동일하게 등록
6. **주간 회고 SNS 홍보** — 매주 발행되는 `docs/weekly/<주차>.html`을 어느 채널(예: AI
   관련 커뮤니티/영상 댓글, 개인 SNS 계정 등)에 어떤 방식·주기로 공유할지는 사람이
   직접 정하고 실행해야 하는 항목이다 (자동화 파이프라인이 대신 게시할 수 없음). 아직
   구체적인 방법은 미정 — 사용자가 나중에 구체화할 예정.
7. **구글 Search Console / 네이버 서치어드바이저 등록** — 계정 기반 소유권 인증이라
   에이전트가 대신할 수 없다. DNS TXT(구글 권장) 또는 `config/site_verification.json`
   메타태그(네이버) 방식, sitemap 제출까지 상세 체크리스트는 `MARKETING.md` 참고.
8. **영어권 커뮤니티 노출(Product Hunt/Hacker News/Reddit 등)** — 실제 게시는 사람이
   직접 계정으로 해야 하는 항목. 채널별 전략과 포지셔닝 리서치는 `MARKETING.md` 참고.

## 검증 계획
1. RSS 피드 URL 전수 검증 (완료 — 위 "구성 요소 1" 참고)
2. 샘플 데이터로 `fetch_articles.py` 단독 실행 → 출력 JSON 구조 확인
3. Claude가 직접 요약/시사점을 작성해 `digest_<날짜>.json` 생성
4. `generate_site.py` 실행 → `docs/index.html`이 실제로 그럴듯하게 나오는지 로컬에서 확인
5. Vercel 프로젝트 연결(사용자) 후 실제 배포 URL에서 정상 노출되는지 확인
6. Supabase 프로젝트/테이블 생성, Resend 도메인 인증, 환경변수 등록(사용자) 후 실제
   이메일로 구독 신청 → 확인 메일 수신 → 링크 클릭 → `subscribers.confirmed_at` 반영
   확인. Resend/Supabase의 정확한 REST 엔드포인트·필드명은 이 환경에 실제 계정이 없어
   문서 기준으로 구현했으므로, 사용자가 실제 계정으로 이 단계를 검증하며 오류가 나면
   API 응답 메시지를 기준으로 `api/_lib/`와 `scripts/send_broadcast.py`를 조정해야 한다
7. `send_broadcast.py` 수동 실행 → 실제 수신 확인, 이메일 하단 구독취소 링크 동작 확인
8. 위 단계가 모두 통과하면 Claude Code Routine의 스케줄 트리거를 활성화
