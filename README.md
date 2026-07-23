# AI News Briefing

AI 관련 기사를 매일 자동으로 수집해 각 기사의 "요약"과 "이 기사가 시사하는 점"을 정리한
정적 웹페이지를 만들고 Vercel로 자동 배포하는 자동화. 설계 배경과 RSS/배포 방식 선택
근거는 [`PLAN.md`](PLAN.md)를 참고.

## 폴더 구조
```
config/feeds.json          # RSS 피드 목록 (자유롭게 추가/삭제)
scripts/fetch_articles.py  # RSS 수집 + 상위 10개 선별
scripts/generate_site.py   # 정적 HTML 생성
templates/                 # 웹페이지 템플릿(Jinja2)/CSS
.claude/skills/ai-news-briefing/SKILL.md   # 전체 워크플로를 묶는 스킬
vercel.json                 # Vercel 배포 설정 (outputDirectory: docs)
data/, docs/                # 실행 결과물 (docs/는 배포 대상이라 커밋 필요,
                            # data/는 중간 산출물이라 git에는 포함 안 됨)
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
   이 연결은 OAuth 기반 대시보드 작업이라 사람이 한 번은 직접 해야 하고, 이후에는 `main`
   브랜치로 push할 때마다 100% 자동으로 재배포된다.

## 로컬에서 수동 실행해보기 (Routine 활성화 전 검증)
```
python scripts/fetch_articles.py --lookback-days 12 --top-n 10
```
이후 `data/articles_<날짜>.json`을 보고 Claude가 직접 요약/시사점을 작성해
`data/digest_<날짜>.json`을 만든다 (`.claude/skills/ai-news-briefing/SKILL.md`의 2~3단계
참고 — 스크립트로 대체 불가능한 해석 영역).
```
python scripts/generate_site.py --input data/digest_<날짜>.json
```
`docs/index.html`을 브라우저로 열어 확인한다.

## Claude Code Routine 등록 (스케줄 활성화)
1. claude.ai/code/routines 에서 이 저장소를 연결한 Routine을 생성한다.
2. Environment: 별도 API 키가 필요 없다 (RSS는 무인증). Setup script에
   `pip install -r requirements.txt`만 넣으면 된다.
3. Trigger: Scheduled → 매일 08:00, 타임존 KST(Asia/Seoul) (cron: `0 23 * * *`, UTC 기준).
4. Routine 프롬프트: `/ai-news-briefing`
5. 최소 1회는 수동 실행(Run now)으로 전체 파이프라인이 정상 동작하고 Vercel 배포까지
   확인되는지 본 뒤 스케줄을 켠다.

## RSS 피드 수정
`config/feeds.json`의 `feeds` 배열에 `{"name": "표시 이름", "url": "RSS URL"}` 형태로
추가/삭제한다. 피드 하나가 실패해도 해당 피드만 건너뛰고 나머지는 정상 진행된다. URL은
매체 개편으로 바뀔 수 있으므로 주기적으로(또는 파이프라인이 계속 실패할 때) WebFetch나
`curl`로 재검증한다.
