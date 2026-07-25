# AI News Briefing — 프로젝트 개요

`dailyaithread.com` — AI 관련 기사를 매일 자동으로 수집·해석해 정적 웹페이지와 이메일로
전달하는 완전 자동화 파이프라인. 기획 배경부터 개발 과정, 최종 배포 아키텍처까지를
정리한 문서다. 설계 판단의 세부 근거는 [`PLAN.md`](PLAN.md), 운영 방법은
[`README.md`](README.md)를 참고.

## 1. 기획

### 목표
사람 개입 없이 **매일 아침 8시(KST)** 에:
1. AI 뉴스 RSS 피드들을 순회해 출처 다양성을 지키며 상위 10개 기사를 선별하고,
2. 선별된 기사만 Claude가 직접 원문을 읽어 한국어·영어로 요약과 "시사하는 점"을 작성하고,
3. 정적 웹페이지로 발행하고,
4. 이메일 구독자에게 헤드라인 다이제스트를 발송한다.

### 설계 원칙
자매 프로젝트 `business-trend-briefing`에서 이어받은 핵심 철학:

> **수집·생성은 스크립트로 싸게, 해석은 선별된 것만 Claude가 비싸게.**

RSS 수집(수백 건)과 HTML 생성은 결정론적 스크립트가 담당하고, "이 기사가 왜 중요한가"라는
판단이 필요한 부분만 Claude가 개입한다. 전체 피드를 다 원문 fetch하지 않고 스크립트가
10개로 좁혀놓은 뒤에만 Claude가 원문을 정독하는 2단계 구조로 비용을 통제했다.

### 초기 의사결정
| 항목 | 선택 | 이유 |
|---|---|---|
| 기사 수집 | RSS 직접 파싱 | AI 뉴스는 전용 API가 거의 없고 RSS는 무료·무인증 |
| 배포 | GitHub Pages → **Vercel로 전환** | 이 환경에 `gh` CLI가 없어 GitHub Pages를 API로 활성화할 수 없었음. Vercel은 대시보드 연결만으로 충분 |
| 스케줄링 | Claude Code Routines | `/loop`·`CronCreate`는 임시 작업이라 만료됨. Routine은 영구 cron |

## 2. 파이프라인 시각화

### 2-1. 매일 자동 실행되는 콘텐츠 파이프라인

```mermaid
flowchart TD
    A["⏰ Claude Code Routine<br/>매일 08:00 KST (cron 0 23 * * * UTC)"] --> B["fetch_articles.py<br/>RSS 11개 피드 순회"]
    B --> C["출처당 최대 3개 제한<br/>최신순 상위 10개 선별"]
    C --> D["Claude가 WebFetch로<br/>선별된 10건만 원문 정독"]
    D --> E["한국어 + 영어로<br/>요약 · 시사점 직접 작성"]
    E --> F["digest_&lt;날짜&gt;.json"]
    F --> G["generate_site.py<br/>Jinja2 → 정적 HTML"]
    G --> H["docs/index.html<br/>docs/archive/&lt;날짜&gt;.html"]
    H --> I["git commit & push"]
    I --> J["Vercel Git Integration<br/>자동 재배포"]
    J --> K["send_broadcast.py<br/>확인된 구독자에게 발송"]

    style A fill:#4f46e5,color:#fff
    style D fill:#a2201d,color:#fff
    style E fill:#a2201d,color:#fff
    style K fill:#0f766e,color:#fff
```

빨간색 두 단계(원문 정독, 요약·시사점 작성)만 Claude의 판단이 개입하고, 나머지는 전부
결정론적 스크립트/플랫폼 자동화다.

### 2-2. 이메일 구독 흐름 (일일 파이프라인과 별개, 방문자가 언제든 트리거)

```mermaid
sequenceDiagram
    actor V as 방문자
    participant Site as dailyaithread.com
    participant Sub as /api/subscribe
    participant DB as Supabase (subscribers)
    participant Mail as Resend

    V->>Site: 이메일 입력 후 제출
    Site->>Sub: POST {email}
    Sub->>DB: upsert (confirmed_at = null)
    Sub->>Mail: 확인 링크 발송 (HMAC 서명, 24h 유효)
    Mail-->>V: "구독을 확인해주세요" 메일
    V->>Site: 메일의 확인 링크 클릭
    Site->>DB: confirmed_at 갱신
    Note over V,DB: 다음날 08:00 발송 대상에 포함됨

    loop 매일 08:00
        Mail->>V: 헤드라인 + 한줄요약 다이제스트
    end

    V->>Site: 메일 하단 구독취소 링크 클릭
    Site->>DB: unsubscribed_at 갱신
```

확인/구독취소 토큰은 별도 저장소 없이 `email + 만료시각`을 서버 비밀키로 HMAC-SHA256
서명해 링크에 담는다 — 클릭 시 서명을 재계산해 비교하는 것만으로 검증이 끝난다.

### 2-3. 전체 시스템 아키텍처 (관련 서비스)

```mermaid
flowchart LR
    subgraph src["정보원"]
        RSS["RSS 11개 피드<br/>(TechCrunch, VentureBeat, The Verge,<br/>MarkTechPost, OpenAI, DeepMind,<br/>Google AI Blog, Ars Technica,<br/>Wired, MIT Tech Review, HN)"]
    end

    subgraph auto["자동화"]
        Routine["Claude Code Routine<br/>(Anthropic Cloud)"]
    end

    subgraph host["저장소 · 호스팅"]
        GH["GitHub<br/>dhchun1203/ai-news-briefing"]
        Vercel["Vercel<br/>정적 사이트 + 서버리스 함수"]
    end

    subgraph data["구독 데이터 · 발송"]
        Supa[("Supabase<br/>subscribers 테이블")]
        Resend["Resend<br/>mail.dailyaithread.com"]
    end

    RSS --> Routine
    Routine -->|"commit/push"| GH
    GH -->|"Git Integration"| Vercel
    Routine -->|"send_broadcast.py"| Resend
    Vercel <-->|"REST API"| Supa
    Vercel -->|"확인 메일"| Resend
    Resend -->|"발송"| Reader(("구독자"))
    Vercel -->|"HTML"| Visitor(("사이트 방문자"))
```

## 3. 개발 단계

### Phase 1 — 스캐폴딩
- RSS 피드 후보를 WebFetch/curl로 전수 검증 (11개 확정, Anthropic 공식 RSS 부재로 제외)
- `fetch_articles.py`(수집), `generate_site.py`(생성), Jinja2 템플릿, 기본 CSS 작성
- GitHub 저장소 연결, 최초 커밋/푸시
- **Vercel로 배포 전환** — GitHub Pages 대신 선택 (근거는 위 1절 참고)
- Claude Code Routine 최초 등록, 실제 RSS 데이터로 전체 파이프라인 1회 수동 검증

### Phase 2 — 자동화 안정화
- Routine의 클라우드 Environment 네트워크 정책이 뉴스 도메인을 차단 → 전용 Environment
  생성 후 도메인 화이트리스트 등록으로 해결
- Setup script가 저장소 체크아웃 이전에 실행돼 `pip install` 실패 → 의존성 설치를
  SKILL.md 0단계(세션 내부 Bash)로 이동
- Routine "Run now"로 전체 파이프라인(수집 → Claude 해석 → 배포)이 사람 개입 없이
  도는 것을 실측 확인

### Phase 3 — 디자인 반복 개선
1. PC/모바일 화면별 가독성을 위해 CSS를 `site-base` / `site-mobile` / `site-desktop`
   3개로 분리
2. NYT풍 에디토리얼 테마로 전면 개편 (세리프 헤드라인, 얇은 구분선, 흑백 팔레트)
3. 한글 렌더링이 뭉개지는 문제 발견 → 원인은 Georgia 폰트가 한글을 지원하지 않아
   시스템 폰트(Batang)의 가짜 이탤릭으로 폴백된 것 → Noto Serif KR 웹폰트 적용 + 이탤릭 제거
4. 다크모드 토글을 좌우 슬라이딩 스위치로, 시스템 설정과 무관하게 **항상 라이트로
   시작**하고 선택값은 쿠키에 저장하도록 변경
5. 한국어/영어 드롭다운 다국어 지원 (전체 UI + 기사 요약·시사점 이중 작성)
6. 목차(TOC), 헤더 미션 문구(이 브리핑이 왜 이 소스들을 고르는지, 무엇을 전달하려는지)
   추가 및 가독성 개선(왼쪽 정렬, 문장 간 시각적 구분)

### Phase 4 — 이메일 구독 기능
- 아키텍처 결정: **Supabase**(구독자 원본 데이터 소유) + **Resend**(발송 전용) +
  **더블 옵트인**(스팸 방지)
- Vercel 서버리스 함수 3개(`subscribe` / `confirm` / `unsubscribe`)를 외부 패키지 없이
  Node 18+ 전역 `fetch`만으로 구현
- 확인/구독취소 토큰 서명 로직을 Node·Python 양쪽에서 동일하게 구현 후 직접 실행해
  교차 검증 (같은 비밀키로 동일한 서명이 나오는지 확인)
- `scripts/send_broadcast.py` — 확인된 구독자에게 헤드라인+링크 형식으로 일일 배치 발송
- 커스텀 도메인 `dailyaithread.com` 구매, DNS 연결:
  - 웹사이트: apex/www → Vercel
  - 이메일: `mail.dailyaithread.com` 서브도메인 → Resend (SPF/DKIM/DMARC 검증 완료)
- 실제 계정으로 End-to-End 테스트 중 두 가지 실전 이슈 발견 및 해결:
  1. Supabase에 테이블 생성을 빠뜨려 `PGRST205` 에러 → `schema.sql` 실행으로 해결
  2. Python `urllib` 기본 User-Agent가 Cloudflare에 봇으로 차단(`error 1010`) →
     User-Agent 헤더 추가로 해결
- 구독 신청 → 확인 메일 수신 → 링크 클릭 → 구독 확정 → 일일 발송까지 실제 계정으로
  전 과정 검증 완료

### Phase 5 — 콘텐츠 자산 확장
- **아카이브 영구 보관 + 검색**: `docs/archive/<날짜>.json`이 그날 digest의 유일한
  영속 기록이 된다(`data/`는 gitignore). 이 파일들이 이후 중복 제외·검색·주간 회고·
  용어사전의 공통 데이터 원본 역할을 한다.
- **과거 중복 방지 + 화제성 감지**: 이미 다룬 링크는 후보에서 제외하고, 여러 매체가
  동시에 다루는 사건을 상위로 올린다. 이후 "링크는 다르지만 내용이 겹치는 기사"까지
  걸러내는 같은 사건 클러스터링을 추가(문턱값은 실제 피드 데이터로 두 번 보정).
- **주간 회고**: 일요일에만 그 주 `daily_insight`들을 가로질러 한 주의 흐름을 종합.
- **AI 용어사전**: 매일 작성하던 `glossary` 설명을 누적 집계한 별도 페이지. 이어서
  용어 간 연관관계를 Claude가 판단해 기록하고(`docs/glossary-relations.json`) 이를
  힘 기반 레이아웃으로 시각화하는 "용어 지도" 추가.
- **SEO/GEO 인프라**: robots.txt(AI 크롤러 명시 허용), sitemap.xml, canonical,
  JSON-LD 구조화 데이터, 날짜별 동적 OG 이미지(Pillow). 영어권 착지 페이지 `/en/`와
  hreflang 상호 참조.

### Phase 6 — 전면 점검 (신뢰성·보안·접근성)
운영 데이터가 며칠 쌓인 뒤 코드베이스 전체를 감사해 발견한 문제들을 수정. 자세한
내역은 `PLAN.md` §24 참고. 특히 "조용히 실패해서 아무도 모르는" 부류가 많았다:
- **주간 회고가 매주 건너뛰어지고 있었다** — Routine 컨테이너가 UTC라 08:00 KST
  일요일에 셸 `date +%u`가 6(토요일)을 반환. 첫 일요일 실행 직전에 발견.
- **공개 저장소 README에 실사용 HMAC 시크릿이 커밋돼 있었다** — 교체 후 제거.
- 메일 HTML에 서드파티 URL이 이스케이프 없이 들어가 속성 인젝션이 가능했다.
- 부분 발송 실패 시 마커가 안 남아 이미 받은 사람에게 재발송될 수 있었다.
- `/api/subscribe`에 레이트 리밋이 전혀 없어 메일 폭탄 증폭기로 쓰일 수 있었다.
- 구독취소가 GET이라 메일 스캐너가 사용자를 대신 해지시키고 있었다.
- 3개 템플릿에 복붙된 클라이언트 JS를 공용 `site.js`로 추출(사본 간 드리프트 해소).
- **테스트/CI 도입** — 그전까지 자동 검증이 전무했다. Python 단위 테스트, API 핸들러
  테스트, Python↔Node HMAC 동등성 테스트, jsdom 브라우저 스모크 테스트 + GitHub Actions.

## 4. 최종 기술 스택

| 영역 | 기술 | 역할 |
|---|---|---|
| 기사 수집 | Python + `feedparser` | RSS 11개 피드 파싱, 같은 사건 중복 제거 후 상위 10개 선별 |
| 콘텐츠 해석 | Claude (WebFetch) | 원문 정독, 한/영 요약·시사점 작성 — 유일하게 사람(AI)의 판단이 필요한 단계 |
| 사이트 생성 | Python + Jinja2 | 정적 HTML/CSS 렌더링 |
| 배포 | Vercel | 정적 사이트 + 서버리스 함수(API), GitHub Git Integration으로 push 시 자동 재배포 |
| 도메인 | `dailyaithread.com` (가비아) | 웹사이트(apex/www) + 이메일 발신(`mail.` 서브도메인) 분리 |
| 구독자 DB | Supabase (Postgres) | 구독자 원본 데이터의 유일한 진실 소스, RLS로 `service_role` 키만 접근 허용 |
| 이메일 발송 | Resend | 확인 메일(단건) + 일일 다이제스트(배치, 최대 100통) 발송 전담 |
| 인증 토큰 | HMAC-SHA256 (자체 구현) | 별도 저장소 없이 확인/구독취소 링크 서명·검증 |
| 스케줄링 | Claude Code Routines | 매일 08:00 KST 영구 cron 트리거로 전체 파이프라인 실행 |
| 테스트/CI | `unittest` + `node --check` + jsdom, GitHub Actions | 파이프라인이 실제 구독자를 상대로 돌기 전에 잡는 유일한 자동 게이트 |

## 5. 회고 — 반복된 검증 패턴

이 프로젝트 전반에 걸쳐 반복된 작업 방식:

1. **가정하지 않고 직접 검증**: RSS 피드 URL, Resend/Supabase API 스펙(WebFetch로 공식
   문서 확인), HMAC 토큰 호환성(Node/Python 양쪽 직접 실행) 모두 추측 대신 실행해서 확인
2. **자동화 전 최소 1회 수동 실행**: Routine 스케줄을 켜기 전에 항상 "Run now"로 전체
   파이프라인을 최소 1회 실제로 돌려 사람 개입 없이 끝까지 도는지 확인한 뒤 신뢰
3. **외부 계정 연동은 사람이, 나머지는 자동화**: GitHub/Vercel/Supabase/Resend/도메인
   등록처럼 OAuth·본인인증·결제가 필요한 단계만 사용자가 직접 수행하고, 그 외 코드·배포·
   스케줄링은 전부 자동화로 처리
