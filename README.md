# AI News Briefing

AI 관련 기사를 매일 자동으로 수집해 각 기사의 "요약"과 "이 기사가 시사하는 점"을 정리한
정적 웹페이지를 만들고 Vercel로 자동 배포하는 자동화. 한국어/영어 이중언어, 이메일 구독
기능을 포함한다. 설계 배경과 RSS/배포 방식/구독 아키텍처 선택 근거는 [`PLAN.md`](PLAN.md)를,
SEO/GEO·검색엔진 등록·해외 노출 전략은 [`MARKETING.md`](MARKETING.md)를 참고.

## 폴더 구조
```
config/feeds.json           # RSS 피드 목록 + 소스 타입(primary/press/community)
config/site_verification.json  # 구글/네이버 사이트 소유 확인 메타태그 값(선택)
scripts/fetch_articles.py   # RSS 수집 + 과거 중복 제외 + 화제성 반영 + 상위 10개 선별
scripts/generate_site.py    # 정적 HTML 생성 + 아카이브 JSON/검색 인덱스/SEO 산출물 갱신
scripts/generate_weekly_site.py  # (일요일) 주간 회고 페이지 생성
scripts/send_broadcast.py   # 확인된 이메일 구독자에게 오늘의 다이제스트 발송
scripts/seo_utils.py        # robots.txt/sitemap.xml/JSON-LD 등 SEO/GEO 공용 헬퍼
scripts/og_image.py         # 날짜별 동적 OG 이미지 렌더링(Pillow) — 실패 시 정적 이미지로 자동 대체
scripts/tools/generate_og_image.py  # 1회성 로컬 스크립트(범용 og-image.png 생성용, 파이프라인 미포함)
templates/                  # 웹페이지 템플릿(Jinja2)/CSS
templates/static/           # favicon.svg, og-image.png (정적 이미지 자산)
templates/static/fonts/     # 동적 OG 이미지용 한글 폰트(NotoSerifKR-Variable.ttf)
api/                        # Vercel 서버리스 함수 (구독/확인/구독취소)
supabase/schema.sql         # 구독자 테이블 스키마 (Supabase SQL Editor에서 1회 실행)
.claude/skills/ai-news-briefing/SKILL.md   # 전체 워크플로를 묶는 스킬
vercel.json                 # Vercel 배포 설정 (outputDirectory: docs)
data/                        # 중간 산출물, git에는 포함 안 됨
docs/                        # 배포 대상 — index.html, archive/<날짜>.html·json(영구 보관)·
                            # sent.json(발송 완료 마커), weekly/<주차>.html, search-index.json,
                            # robots.txt, sitemap.xml, favicon.svg, og-image.png, og/<날짜>.png
                            # 전부 커밋 필요
```

## 최초 설정 (사람이 직접 해야 하는 부분)

1. **의존성 설치 (로컬 테스트용)**
   ```
   pip install -r requirements.txt
   ```

2. **Vercel 프로젝트 연결**
   https://vercel.com 에서 로그인 → "Add New... → Project" → 이 GitHub 저장소
   (`dhchun1203/ai-news-briefing`) Import. Framework Preset은 "Other"로 두면 저장소 루트의
   `vercel.json`(`outputDirectory: "docs"`)을 그대로 인식해 별도 빌드 설정 없이 배포된다.
   `api/` 폴더는 outputDirectory 설정과 무관하게 Vercel이 서버리스 함수로 자동 인식한다.
   이 연결은 OAuth 기반 대시보드 작업이라 사람이 한 번은 직접 해야 하고, 이후에는 `main`
   브랜치로 push할 때마다 100% 자동으로 재배포된다.

3. **이메일 구독 기능 설정** (아래 "이메일 구독 설정" 섹션 전체 참고). 이 단계를 건너뛰어도
   웹사이트 자체는 정상 동작하고, 구독 폼만 에러를 반환한다.

## 이메일 구독 설정

구독자 목록의 진실 소스는 **Supabase**(subscribers 테이블)이고, **Resend**는 발송만
담당한다. 더블 옵트인(이메일 확인 링크) 방식이라 실제로 발송 대상이 되려면 사용자가 확인
메일의 링크를 눌러야 한다.

### 1. Supabase 프로젝트 생성
1. https://supabase.com 에서 새 프로젝트 생성.
2. 프로젝트의 SQL Editor에서 [`supabase/schema.sql`](supabase/schema.sql) 전체를 실행해
   `subscribers` 테이블을 만든다.
3. **Project Settings → API**에서 `Project URL`과 `service_role` 키(비밀값, anon 키 아님)를
   복사해둔다.

### 2. Resend 도메인 인증
구독자는 임의의 이메일 주소이므로, 인증 없이 쓸 수 있는 `onboarding@resend.dev` 샌드박스
발신 주소로는 (계정 소유자 본인 메일이 아닌) 임의의 수신자에게 보낼 수 없다. **Resend에서
발신 도메인을 인증**하고(DNS 레코드 추가), 그 도메인의 주소(예: `briefing@yourdomain.com`)를
`RESEND_SENDER_EMAIL`로 사용해야 한다. `RESEND_API_KEY`는 resend.com에서 발급.

### 3. 랜덤 시크릿 생성
확인/구독취소 링크에 서명하는 데 쓰는 임의의 문자열이다(별도 DB 저장 없이 HMAC 서명만으로
링크 위·변조를 막는다). 아래 값을 그대로 써도 되고, 원하면 직접 새로 생성해도 된다
(`python -c "import secrets; print(secrets.token_urlsafe(32))"`):
```
SUBSCRIBE_TOKEN_SECRET=1bblQaRz7FIUjTc9n2XMwLXDm0ovwhW-UphaNS1wzaQ
```

### 4. 환경변수 등록 (두 곳 모두에 동일하게)
| 변수 | 값 | 필요한 곳 |
|---|---|---|
| `SUPABASE_URL` | Supabase 프로젝트 URL | Vercel, Routine |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service_role 키 | Vercel, Routine |
| `RESEND_API_KEY` | Resend API 키 | Vercel, Routine |
| `RESEND_SENDER_EMAIL` | 인증된 도메인의 발신 주소 | Vercel, Routine |
| `SUBSCRIBE_TOKEN_SECRET` | 위에서 생성한 랜덤 문자열 | Vercel, Routine |
| `SITE_URL` | 배포된 사이트 URL (예: `https://ai-news-briefing-taupe.vercel.app`, 뒤 슬래시 없이) | Vercel, Routine |

- **Vercel**: 프로젝트 → Settings → Environment Variables에 위 6개를 모두 추가한다
  (`/api/subscribe`, `/api/confirm`, `/api/unsubscribe`가 사용). 추가 후 재배포해야 반영된다.
- **Claude Code Routine**: claude.ai/code → 이 Routine의 Environment에 동일하게 6개를 모두
  추가한다 (`scripts/send_broadcast.py`가 매일 실행 시 사용).

### 5. 동작 확인
1. 배포된 사이트에서 본인 이메일로 구독 신청 → 확인 메일 수신 → 링크 클릭 →
   "구독 확인 완료" 페이지가 뜨는지 확인.
2. Supabase 테이블 편집기에서 `subscribers` 테이블에 해당 행의 `confirmed_at`이 채워졌는지
   확인.
3. 로컬 또는 Routine에서 `python scripts/send_broadcast.py --input data/digest_<날짜>.json`을
   한 번 수동 실행해 실제로 메일이 오는지, 하단 구독취소 링크가 정상 동작하는지 확인.

## 로컬에서 수동 실행해보기 (Routine 활성화 전 검증)
```
python scripts/fetch_articles.py --lookback-days 12 --top-n 10
```
이후 `data/articles_<날짜>.json`을 보고 Claude가 직접 한국어/영어 요약·시사점을 작성해
`data/digest_<날짜>.json`을 만든다 (`.claude/skills/ai-news-briefing/SKILL.md`의 2~3단계
참고 — 스크립트로 대체 불가능한 해석 영역).
```
python scripts/generate_site.py --input data/digest_<날짜>.json
```
`docs/index.html`을 브라우저로 열어 확인한다. 이메일 구독 환경변수까지 설정했다면:
```
python scripts/send_broadcast.py --input data/digest_<날짜>.json
```

## Claude Code Routine 등록 (스케줄 활성화)
1. claude.ai/code/routines 에서 이 저장소를 연결한 Routine을 생성한다.
2. Environment: RSS 수집 자체는 API 키가 필요 없지만, 이메일 구독 기능을 쓰려면 위
   "이메일 구독 설정 → 4. 환경변수 등록"의 6개 변수를 이 Routine의 Environment에 등록한다.
   Setup script는 필요 없다 — `pip install -r requirements.txt`는 SKILL.md 0단계에서
   Claude가 세션 안에서 직접 실행한다(저장소가 아직 체크아웃되기 전인 Setup script 단계에
   넣으면 파일이 없어 실패한다).
3. Trigger: Scheduled → 매일 08:00, 타임존 KST(Asia/Seoul) (cron: `0 23 * * *`, UTC 기준).
4. Routine 프롬프트: `/ai-news-briefing`
5. 최소 1회는 수동 실행(Run now)으로 전체 파이프라인(수집→사이트 배포→이메일 발송)이
   정상 동작하는지 확인한 뒤 스케줄을 켠다.

## RSS 피드 수정
`config/feeds.json`의 `feeds` 배열에 `{"name": "표시 이름", "url": "RSS URL"}` 형태로
추가/삭제한다. 피드 하나가 실패해도 해당 피드만 건너뛰고 나머지는 정상 진행된다. URL은
매체 개편으로 바뀔 수 있으므로 주기적으로(또는 파이프라인이 계속 실패할 때) WebFetch나
`curl`로 재검증한다.
