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
        │     - 출처당 최대 3개로 제한하며 최신순으로 상위 10개 선별
        │     - 출력: data/articles_<날짜>.json
        │
        ├─ 2. Claude가 선별된 10개만 WebFetch로 원문을 직접 읽는다
        │     (RSS 요약만으로는 부실 → 전체 피드 원문 fetch는 비효율 →
        │      "이미 선별된 10개만" 정독)
        │
        ├─ 3. Claude가 기사별로 직접 작성 (스크립트로 대체 불가):
        │     - summary: 2~3문장 요약
        │     - implication: 이 기사가 시사하는 점 1~2문장
        │     → data/digest_<날짜>.json
        │
        ├─ 4. scripts/generate_site.py
        │     - Jinja2로 정적 HTML 렌더링 (제목/출처/날짜 → 요약 → 시사점 순서)
        │     - docs/index.html(오늘자) 생성
        │     - docs/archive/<날짜>.html로 과거 기록 누적 보관
        │     - docs/index.html 하단에 지난 아카이브 링크 목록 추가
        │
        ├─ 5. git add/commit/push → Vercel Git Integration이 main 브랜치를 감지해 자동 재배포
        │     (vercel.json의 outputDirectory: "docs" 기준 정적 배포)
        │
        └─ 6. scripts/send_broadcast.py
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
`date`, `generated_at`, `articles[]`(title, link, source, published_at, summary,
implication). `summary`/`implication`은 Claude가 SKILL.md 3단계에서 직접 작성한다.

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
