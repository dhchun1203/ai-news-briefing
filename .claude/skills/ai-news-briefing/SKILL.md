---
name: ai-news-briefing
description: AI 관련 기사를 RSS로 매일 수집해 각 기사의 요약과 "이 기사가 시사하는 점"을 정리한 정적 웹페이지를 만들고 Vercel로 배포한다. Claude Code Routine이 매일 오전 8시 KST에 이 스킬을 호출한다.
---

# AI 뉴스 브리핑

이 스킬은 저장소 루트(`ai-news-briefing/`)를 기준으로 동작한다. 순서대로 실행하고,
각 단계가 실패하면 다음 단계로 넘어가지 말고 오류 내용을 그대로 보고한다.

대상 소스: `config/feeds.json`에 등록된 RSS 피드들(TechCrunch AI, VentureBeat AI, The Verge AI,
MarkTechPost, OpenAI News, Google DeepMind Blog, Google AI Blog, Ars Technica AI, Wired AI,
MIT Technology Review AI, Hacker News AI 등). 특정 매체를 고정 편애하지 않고, 최근 게시된
기사 중 출처 다양성을 지키면서 상위 10개만 매번 새로 선별한다.

## 0. 사전 점검
- `python -m pip install -r requirements.txt` 로 의존성(feedparser, Jinja2, python-dateutil)이
  설치되어 있는지 확인한다 (Routine Environment의 setup script에서 이미 설치되어 있다면 생략 가능).
- `config/feeds.json`의 피드 URL이 최근에 검증된 적이 있는지 확인한다. 반년 이상 검증 이력이
  없거나 실행 중 특정 피드가 계속 실패한다면, WebFetch나 `curl`로 URL이 여전히 유효한 RSS/Atom을
  반환하는지 재검증하고 필요하면 대체 URL로 교체한다.
- 이메일 구독 발송(7단계)에 필요한 환경변수(`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
  `RESEND_API_KEY`, `RESEND_SENDER_EMAIL`, `SUBSCRIBE_TOKEN_SECRET`, `SITE_URL`)가 이 Routine의
  Environment에 등록되어 있는지 확인한다. 아직 등록 전이라면(`README.md`의 "이메일 구독
  설정" 참고) 7단계는 건너뛰고 나머지 단계는 정상 진행한 뒤, 완료 보고에 "이메일 구독
  환경변수 미설정으로 발송 생략"이라고 명시한다.

## 1. 기사 수집
```
python scripts/fetch_articles.py --lookback-days 12 --top-n 10
```
- `config/feeds.json`의 모든 피드를 순회해 최근 12일 이내 게시된 기사만 후보로 모은다.
- **과거 중복 제외**: `docs/archive/*.json`(지금까지 매일 영구 보관된 원본 digest)에 이미
  등장한 링크는 후보에서 아예 제외한다 — 다른 날짜의 브리핑에 실렸던 기사가 다시 뽑히는
  일이 없다.
- **화제성 우선**: 제목에서 고유명사·버전명으로 추정되는 키워드를 뽑아, 서로 다른 출처가
  같은 키워드를 공유하는(=여러 매체가 동시에 다루는) 후보일수록 우선순위를 높인다. 그다음
  최신순으로 정렬하고, 출처 하나가 상위 목록을 독점하지 않도록 출처당 최대 3개까지만
  채택하면서 상위 10개를 선별한다 (부족하면 다양성 제한을 풀고 채운다).
- 출력: `data/articles_<날짜>.json` (title, link, source, published_at, rss_summary,
  cross_source_count)
- 피드 하나가 실패해도 stderr에 경고만 남기고 나머지 피드로 계속 진행한다. 실행 후 몇 개
  피드가 실패했는지, 과거 중복으로 몇 개가 제외됐는지 요약에 포함한다.

## 2. 원문 정독 (Claude가 직접 WebFetch로 수행)
`rss_summary`만으로는 내용이 부실한 경우가 많다. **선별된 10개 기사에 한해서만** 각 기사의
`link`를 WebFetch로 직접 읽는다. 전체 RSS 피드를 다 원문 fetch하는 것은 비효율적이므로,
이미 1단계에서 상위 10개로 좁혀놓은 뒤에만 원문을 정독하는 것이 핵심이다 (검색은 싸게,
해석은 선별된 것만 비싸게).

## 3. 요약 및 시사점 작성 (Claude가 직접 해석 — 스크립트로 대체 불가)
사이트가 한국어/영어 두 언어를 모두 지원하므로(우측 상단 언어 토글), 기사별로 요약과
시사점을 **두 언어 모두** 직접 작성해서 `data/digest_<날짜>.json`에 저장한다. 영어판은
한국어판을 기계적으로 번역기에 돌리지 말고, 같은 원문을 기준으로 자연스러운 영어 기사
요약처럼 직접 작성한다:

```json
{
  "date": "YYYY-MM-DD",
  "generated_at": "ISO8601 타임스탬프",
  "glossary": [
    {
      "term_ko": "본문에 실제로 등장하는 한국어 용어 표기 그대로",
      "term_en": "본문에 실제로 등장하는 영어 용어 표기 그대로",
      "explanation_ko": "전문용어를 안 쓰고 처음 듣는 사람도 이해할 수 있게 쓴 한국어 설명 1~2문장.",
      "explanation_en": "같은 설명의 자연스러운 영어 1~2문장."
    }
  ],
  "daily_insight": {
    "headline_ko": "오늘 10개 기사를 관통하는 가장 큰 메시지 한 문장 (한국어)",
    "headline_en": "같은 메시지의 자연스러운 영어 한 문장",
    "paragraphs_ko": ["종합 분석 문단 1", "문단 2", "문단 3 (2~4개, 각 2~4문장)"],
    "paragraphs_en": ["같은 분석의 영어 문단 1", "문단 2", "문단 3"],
    "watch_ko": "앞으로 며칠 안에 지켜볼 신호 한 문장 (한국어, 선택)",
    "watch_en": "같은 신호의 영어 한 문장 (선택)"
  },
  "articles": [
    {
      "title": "기사 원제 그대로 (번역하지 않음)",
      "link": "기사 URL",
      "source": "출처명",
      "published_at": "ISO8601",
      "summary_ko": "한국어 2~3문장 요약. 기사 원문 기준으로 핵심 사실만 담는다.",
      "summary_en": "같은 내용의 자연스러운 영어 2~3문장 요약.",
      "implication_ko": "이 기사가 시사하는 점, 한국어 1~2문장. 왜 중요한지, 무엇을 예고하는지.",
      "implication_en": "같은 내용의 자연스러운 영어 1~2문장 시사점."
    }
  ]
}
```

작성 원칙:
- **가독성 최우선**: `summary`/`implication`/`daily_insight` 모두, 전문용어를 잘 모르는
  일반 독자도 편하게 읽을 수 있는 쉬운 말로 쓴다. "그로킹", "RLHF", "MoE" 같은 업계 용어를
  설명 없이 그냥 쓰지 않는다 — 가능하면 쉬운 말로 풀어 쓰고, 도저히 대체하기 어려운 핵심
  용어라면 아래 "용어 사용 원칙"대로 `glossary`에 등록한다.
- `summary_ko`/`summary_en`은 RSS 요약을 그대로 옮기지 말고, WebFetch로 읽은 원문을 기준으로
  압축한다. 숫자·고유명사 등 핵심 사실은 누락하지 않는다. 두 언어가 같은 사실을 담되, 각각
  해당 언어로 자연스럽게 읽히도록 쓴다(직역이 아니라 재작성).
- `implication_ko`/`implication_en`은 기사 내용을 요약 반복하지 않는다. "이게 왜 중요한가",
  "다음에 어떤 일이 예상되는가", "다른 플레이어에게 어떤 영향을 주는가" 중 하나 이상을 담아
  판단을 보탠다.
- `daily_insight`는 개별 기사 요약을 나열하는 게 아니라, **10개 기사를 가로질러 읽어 유의미한
  주제·긴장·패턴을 종합**하는 크로스컷 분석이다 (사이트 상단 "오늘의 인사이트" 섹션에 노출).
  기사들을 의미상 묶이는 2~4개 테마로 그룹핑하고, 서로 다른 기사가 어떻게 같은 큰 흐름의
  다른 단면인지 짚는다. `headline`은 그날 전체를 한 문장으로 요약하는 판단이고, `watch`는
  다음 며칠 안에 확인될 신호 하나를 고른다(마땅한 게 없으면 `watch_ko`/`watch_en`은 생략 가능 —
  생략하면 섹션에서 자동으로 빠진다). 기사가 서로 무관해 종합할 주제가 없는 날이면
  `daily_insight` 전체를 생략해도 되고(그러면 섹션이 렌더링되지 않음), 억지로 엮지 않는다.
- `title`은 번역하지 않고 원문 그대로 둔다 (실제 기사의 이름이므로).
- 기사 배열 순서는 `data/articles_<날짜>.json`의 선별 순서(최신순)를 유지한다.

**용어 사용 원칙 (glossary)**: `generate_site.py`가 `glossary`에 등록된 단어를 본문(요약·
시사점·인사이트) 안에서 자동으로 찾아 클릭 가능한 버튼으로 바꿔준다. 클릭하면 우측에서
패널이 열리며 설명이 뜬다 — Claude는 마크업을 직접 넣을 필요 없이, **아래만 지키면 된다**:
1. `glossary[].term_ko`/`term_en`에 적은 단어를, 그 언어의 본문(`summary_ko`,
   `implication_ko`, `daily_insight`의 한국어 필드 등)에 **정확히 같은 표기**로 등장시킨다
   (예: `term_ko`를 "오픈웨이트"로 적었으면 본문에도 "오픈웨이트"라고 써야 자동으로
   연결된다. "오픈 웨이트"처럼 띄어쓰기가 다르면 연결되지 않는다).
2. **등록 기준은 넓게, 적극적으로 잡는다.** 판단 기준은 "개발자나 AI 업계 종사자가 아니면
   모를 법한 용어인가"이다 — 이 기준에 걸리면 웬만하면 등록한다. 업계 약어(RAG, MoE, RLHF,
   파인튜닝 등), 규제·법률 용어(Entity List 등), 보안 용어(제로데이 취약점, 권한 상승,
   횡적 이동 등), AI 인프라 단위(토큰, GPU, 파라미터 등)처럼 뉴스를 이해하는 데 필요하지만
   비개발자 독자는 설명 없이 넘어가기 어려운 단어는 놓치지 말고 잡는다. "등록을 아끼는 것"
   보다 "잡아서 손해볼 것 없다"는 쪽으로
   판단한다. 다만 같은 용어가 그날 다른 기사에서 이미 등록됐다면 중복 등록하지 않는다.
3. `explanation_ko`/`explanation_en`도 쉬운 말로 쓴다 — 용어를 다른 전문용어로 설명하지
   않는다.
- 원문 접속이 막혀 WebFetch가 실패하면 `rss_summary`를 기반으로 두 언어 모두 작성하되,
  정보가 부족하다는 한계를 감안해 단정적인 표현은 피한다.

## 4. 사이트 생성
```
python scripts/generate_site.py --input data/digest_<날짜>.json
```
- Jinja2로 `templates/site.html.j2`를 렌더링해 `docs/index.html`(오늘자, 항상 최신)과
  `docs/archive/<날짜>.html`(과거 기록 누적)을 생성한다.
- 같은 digest의 원본(글로서리 링크화 이전 순수 텍스트)을 `docs/archive/<날짜>.json`으로도
  영구 보관하고, `docs/archive/*.json` 전체를 모아 `docs/search-index.json`(아카이브 검색용)을
  다시 만든다 — 1단계의 "과거 중복 제외"와 5단계의 "주간 회고"가 이 파일들을 읽는다.
- `config/feeds.json`의 `type`(primary/press/community)을 기준으로 기사 카드에 "공식
  발표"/"보도"/"커뮤니티" 배지가 자동으로 붙는다 — Claude가 따로 지정할 필요 없다.
- `docs/index.html` 하단에는 지난 아카이브 링크 목록과 검색창, 주간 회고 목록이 자동으로
  추가된다. 오늘이 일요일이나 월요일이면(신규 독자 유입을 노린 홍보) 최신 주간 회고로
  연결되는 배너가 본문 상단에도 추가로 노출된다 — 날짜만 보고 자동 계산하므로 Claude가
  따로 지정할 필요 없다.
- `templates/site-base.css`(공통), `site-mobile.css`(≤767px), `site-desktop.css`(≥768px)도
  `docs/`로 함께 복사된다. PC와 모바일은 서로 다른 CSS 파일이 `media` 속성으로 조건부
  적용되며 화면별로 가독성(글자 크기, 여백, 줄 간격)을 따로 튜닝한다.
- 페이지 우측 상단에 다크모드 토글과 한국어/영어 언어 토글 버튼이 있다. 두 언어 콘텐츠는
  모두 같은 HTML에 렌더링되고 클라이언트 JS가 `data-lang` 속성으로 표시/숨김만 전환하므로,
  `digest_<날짜>.json`에 `summary_ko`/`summary_en`/`implication_ko`/`implication_en`이
  모두 채워져 있어야 두 언어 모두 정상적으로 보인다.
- `glossary`에 등록된 단어는 `generate_site.py`가 본문에서 자동으로 찾아 클릭 가능한
  버튼으로 바꾸고, 클릭 시 우측에 슬라이드 패널로 설명을 보여준다. Claude가 할 일은
  위 3단계처럼 `glossary`를 채우고 본문에 같은 표기로 쓰는 것뿐이다.

## 5. (일요일에만) 주간 회고 작성
오늘이 KST 기준 **일요일**인지 먼저 확인한다 (`date +%u` — 7이면 일요일). 일요일이 아니면
이 단계 전체를 건너뛰고 다음 단계(배포)로 넘어간다.

일요일이면, 이번 주(월~일)의 날짜 범위와 ISO 주차 라벨을 계산한다:
```
date +%G-W%V              # 이번 주 라벨, 예: 2026-W30
date -d 'last monday' +%Y-%m-%d   # 이번 주 월요일(start_date)
date +%Y-%m-%d             # 오늘 = 이번 주 일요일(end_date)
```
그다음 `docs/archive/<날짜>.json` 중 이번 주(start_date~end_date, 오늘 포함) 범위에 있는
파일들을 읽어(Read 도구로 직접 열어도 되고, `ls docs/archive/`로 목록 확인 후 필요한 것만
읽어도 된다) 그 주의 `daily_insight`들을 모아 **한 주를 관통하는 흐름**을 종합한다. 개별
`daily_insight`를 나열하지 말고, 그 주에 반복된 주제·긴장·패턴을 새로 판단해서 짧고
명료한 종합을 만든다:

```json
{
  "week_label": "2026-W30",
  "start_date": "2026-07-20",
  "end_date": "2026-07-26",
  "generated_at": "ISO8601 타임스탬프",
  "headline_ko": "이번 주 전체를 관통하는 메시지 한 문장 (한국어)",
  "headline_en": "같은 메시지의 자연스러운 영어 한 문장",
  "paragraphs_ko": ["종합 문단 1", "문단 2 (1~3개, 각 2~4문장)"],
  "paragraphs_en": ["같은 분석의 영어 문단 1", "문단 2"]
}
```
`data/weekly_<week_label>.json`로 저장한 뒤 실행한다:
```
python scripts/generate_weekly_site.py --input data/weekly_<week_label>.json
```
- `docs/weekly/<week_label>.html`을 생성한다. 그 주 각 날짜의 `daily_insight` 헤드라인
  목록(일별 브리핑으로 링크)은 스크립트가 `docs/archive/*.json`에서 기계적으로 가져오므로
  Claude가 따로 나열할 필요 없다 — 위 JSON에는 종합 판단(headline/paragraphs)만 담는다.
- `docs/index.html`에도 "주간 회고" 링크 목록이 자동으로 추가된다(다음 4단계를 다시 실행할
  필요 없이, 이미 생성된 오늘자 `docs/index.html`을 이 스크립트가 갱신하지는 않으므로, 이
  단계를 4단계보다 먼저 실행했다면 4단계를 한 번 더 실행해 인덱스에 반영한다. 아래 순서
  그대로 따르면 이미 4단계 다음에 실행하므로 별도 재실행이 필요 없다).
- 그 주에 종합할 만한 뚜렷한 흐름이 없다면 억지로 만들지 않고 이 단계 자체를 건너뛰어도
  된다 — 완료 보고에 "이번 주는 종합할 만한 뚜렷한 흐름이 없어 주간 회고를 생략함"이라고
  적는다.

## 6. 배포
```
git add data docs
git commit -m "AI 뉴스 브리핑 <날짜>"
git push
```
Vercel Git Integration이 `main` 브랜치 push를 감지해 `vercel.json`의
`outputDirectory: "docs"` 기준으로 자동 재배포한다. push 후 별도 대기 없이 완료로 간주한다
(Vercel 배포는 비동기로 처리됨). 저장소가 아직 Vercel 프로젝트와 연결되지 않았다면 이
단계는 커밋/푸시까지만 수행되고 배포는 되지 않으니, 사용자에게 vercel.com에서 저장소를
Import해야 한다고 안내한다.

## 7. 이메일 구독자에게 발송
```
python scripts/send_broadcast.py --input data/digest_<날짜>.json
```
- (5단계에서 그 주 주간 회고를 생성했다면) `--weekly-input data/weekly_<week_label>.json`을
  추가로 넘긴다. 그러면 이메일 최상단에 "이번 주 종합" 티저(주간 회고 헤드라인 + 전체 보기
  링크)가 daily insight 티저보다 먼저 추가된다 — 신규 구독 전환과 주간 회고 노출을 함께
  노린다. 5단계를 건너뛰었으면(그 주 흐름이 없어 생략) 이 옵션도 생략한다.
- Supabase `subscribers` 테이블에서 `confirmed_at`이 있고 `unsubscribed_at`이 없는(=더블
  옵트인을 마친) 이메일만 조회해, 기사 제목+한 줄 요약(`summary_ko`)+원문 링크로 구성된
  가벼운 HTML 이메일을 Resend 배치 발송(`/emails/batch`, 최대 100통씩)으로 보낸다.
- 웹사이트에는 있는 "시사하는 점"은 이메일에는 넣지 않는다 — 전체 브리핑 링크로 유도한다.
- 필요한 환경변수: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `RESEND_API_KEY`,
  `RESEND_SENDER_EMAIL`, `SUBSCRIBE_TOKEN_SECRET`, `SITE_URL`. 하나라도 없으면 스크립트가
  에러 메시지와 함께 종료하니 그대로 보고한다 (Routine Environment에 등록되어 있어야 함).
- 구독자가 0명이면 "발송 대상 구독자가 없습니다"만 출력하고 정상 종료한다 — 실패가 아니다.

## 8. 완료 보고
다음을 요약해 보고한다: 수집 후보 수와 선별된 기사 수(과거 중복으로 제외된 기사 수 포함),
실패한 피드(있다면), 오늘 브리핑에 포함된 기사 제목 10개와 출처, 원문 WebFetch가 실패해
rss_summary로 대체 작성한 기사가 있었는지, 커밋/푸시 결과, `docs/index.html` 경로, 이메일
발송 대상 인원 수, (일요일이었다면) 주간 회고 생성 여부와 경로.
