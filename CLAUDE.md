# ai-news-briefing 작업 규칙

`dailyaithread.com` — 매일 08:00 KST에 Claude Code Routine이 자동 실행하는 한/영 AI 뉴스
브리핑. 정적 사이트(Python + Jinja2 → `docs/`)를 Vercel에 배포한다.

모델 오케스트레이션·API 제약 등 프로젝트와 무관한 지침은 전역 `~/.claude/CLAUDE.md`에
있다. 이 문서는 **이 저장소에서만 통하는 것**만 다룬다.

## 배포 안전 — 가장 중요

이 저장소는 사람이 손대는 동안에도 **매일 08:00에 무인 파이프라인이 돈다.** 발송과
아카이브 수집을 망가뜨리면 구독자에게 메일이 안 가거나 그날 기록이 유실된다.

푸시 전에 **반드시** 확인한다:

```bash
git status --short docs/archive/ | grep -E "\.json$"   # 아무것도 안 나와야 정상
```

- `docs/archive/<날짜>.sent.json`은 **그날 발송이 끝났다는 유일한 기록**이다. 이게
  바뀌거나 지워지면 이미 받은 사람에게 메일이 다시 나간다.
- `docs/archive/<날짜>.json`은 영속 원본이다. 사이트를 재생성해도 이 파일은 안 바뀌어야
  한다 — 바뀌었다면 생성기가 원본을 덮어쓰고 있다는 뜻이다.
- 사이트 재생성은 `py scripts/generate_site.py --input docs/archive/<날짜>.json`으로
  한다(`data/`는 `.gitignore` 대상이라 중간 산출물이 없을 수 있다).

## 무인 운영 원칙

**부가 기능의 실패가 파이프라인 전체를 멈추면 안 된다.** 새 외부 의존을 추가할 때는
반드시 이 패턴을 따른다:

- 예외를 호출부에서 삼키고 폴백을 돌려준다 (`seo_utils.build_og_image_url`,
  `submit_indexnow`가 선례 — Pillow가 없어도, 망이 끊겨도 사이트 생성은 끝난다).
- 네트워크 호출에는 **반드시 timeout**을 준다. 예전에 `urlopen` timeout이 없어 발송이
  멈춘 적이 있다.
- 실패는 조용히 넘어가되 **완료 보고에는 적는다** — 며칠 이어지면 설정 문제다.

### 새 도메인을 만지면 allowlist부터 — 두 번 당했다

Routine은 **네트워크 allowlist가 걸린 클라우드 Environment**에서 돈다. 로컬에는 그런
제한이 없어서, 여기서 잘 되던 코드가 배포 후 조용히 실패한다.

- 2026-07-24: `send_broadcast.py`가 Supabase에 403. allowlist에 RSS 11개 도메인만 있고
  Supabase·Resend가 없었다.
- 2026-07-30: `ping_indexnow.py`를 추가하면서 `api.indexnow.org`와
  **`www.dailyaithread.com`**(배포 확인용 HEAD)이 빠질 뻔했다. 자기 사이트라고 안심하면
  안 된다 — 그동안 자기 사이트에 접속하는 스크립트가 없었으니 목록에도 없었다.

**스크립트에 새 URL을 추가할 때마다 이 질문을 먼저 한다:** 이 도메인이
`claude.ai/code` → Environments → `ai-news-briefing` → Custom network access에 있는가?
없으면 사용자에게 추가를 요청한다(계정 안이라 대행 불가). 변경은 **새 세션부터** 적용되므로
다음 Routine 실행부터 반영된다.

Routine 실행이 "당연히 닿아야 할 도메인"에 403이나 connection refused로 실패하면,
대상 서비스를 의심하기 전에 allowlist부터 본다.

## 개발 환경 (Windows)

- **`python`이 아니라 `py`를 쓴다.** `python`은 Microsoft Store 스텁이라 버전 출력도 없이
  실패한다.
- **콘솔이 cp949다.** 한국어를 stdout으로 내보내면 깨지거나 `UnicodeEncodeError`가 난다.
  스크립트로 한국어를 확인할 때는 파일에 `encoding="utf-8"`로 쓰고 Read로 읽는다.
- 파일을 읽고 쓸 때 `encoding="utf-8"`를 **항상 명시**한다. 생략하면 cp949로 열려 실패한다.
- 런타임 의존성 없음(`package.json` 없음). Node 테스트용 jsdom은 `--no-save`로 설치돼 있다.

## 테스트

```bash
bash tests/run_all.sh    # Python 문법·단위 + Node 문법·API·HMAC·DOM 스모크
```

푸시 전 항상 전체를 돌린다. 개별 실행은 `py -m unittest discover -s tests -p "test_*.py"`,
`node tests/dom_smoke.test.js`.

**회귀 테스트를 실제로 실패시켜 확인한다.** 버그를 고치면 고친 코드를 일부러 되돌려
넣어 테스트가 그 버그를 잡는지 본 뒤 복원한다. 통과만 확인한 테스트는 아무것도 지키지
않을 수 있다.

## 이 저장소에서 반복해서 사고가 난 곳

### 1. 상대경로 접두사 두 종류

`scripts/generate_site.py`에 함수가 둘 있고, 섞으면 반드시 버그가 난다:

| 함수 | 도달점 | 용도 |
|---|---|---|
| `up_prefix(lang, depth)` | **사이트** 루트 | CSS·JS·favicon·og-image·search-index (양 언어 공유) |
| `lang_up_prefix(depth)` | **언어** 루트 | index·about·glossary·topics·archive·weekly·feed.xml |

페이지 링크에 `up_prefix`를 쓰면 영어판이 `/en/` 밖으로 새서 한국어 페이지로 떨어진다.
템플릿에서는 `up`/`css_prefix`(자산)와 `lup`/`lang_prefix`(페이지)로 나뉜다.
`tests/dom_smoke.test.js`의 `checkNoLanguageLeak`가 회귀를 막는다.

### 2. `cleanUrls`가 상대경로 기준을 바꾼다

`vercel.json`의 `cleanUrls: true`가 `/topics/index.html`을 **`/topics`(슬래시 없음)** 로
308 리다이렉트한다. 그래서 그 페이지의 상대경로 기준은 `/topics/`가 아니라 **`/`** 다.
깊이를 손으로 계산하지 말고 위 두 함수만 쓴다. `checkCleanUrlLinks`가 실제 서빙 URL
기준으로 검사한다.

부수 효과: **네이버 소유확인 HTML 파일 업로드 방식을 쓸 수 없다**(`.html`이 확장자 없는
경로로 리다이렉트돼 인증 실패). 메타태그 방식(`config/site_verification.json`)을 쓴다.
`.txt`·`.xml`은 영향받지 않는다.

### 3. sitemap·canonical의 트레일링 슬래시

정규 형태는 **슬래시 없는 쪽**이다. `/topics/`로 보내면 형제 링크가 깨진다.

## 커밋

- **한국어로 쓰고, "무엇을"보다 "왜"를 담는다.** 무엇을 바꿨는지는 diff에 있다. 어떤
  증상이었고 원인이 무엇이었고 왜 이 방법을 골랐는지를 남긴다.
- 사용자가 요청할 때만 커밋·푸시한다.
- 끝에 붙인다: `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`

## 문서 역할 분담

| 문서 | 다루는 것 |
|---|---|
| `.claude/skills/ai-news-briefing/SKILL.md` | 매일 08:00 파이프라인의 실행 절차 |
| `PLAN.md` | 이 기능을 왜 이렇게 만들었나 |
| `MARKETING.md` | 독자를 어떻게 늘리나 (SEO/GEO, 검색엔진 등록, 런칭 카피) |
| `PRODUCT.md` | 어떻게 돈이 되게 하나 (수익 모델, 지표 게이트) |

결정을 내리면 **배제한 선택지와 그 이유까지** 해당 문서에 남긴다 — 나중에 같은 논의를
반복하지 않기 위해서다.
