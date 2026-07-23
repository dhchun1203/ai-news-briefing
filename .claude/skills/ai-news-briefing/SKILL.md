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

## 1. 기사 수집
```
python scripts/fetch_articles.py --lookback-days 12 --top-n 10
```
- `config/feeds.json`의 모든 피드를 순회해 최근 12일 이내 게시된 기사만 후보로 모은다.
- 출처 하나가 상위 목록을 독점하지 않도록 출처당 최대 3개까지만 채택하면서, 최신순으로
  상위 10개를 선별한다 (부족하면 다양성 제한을 풀고 최신순으로 채운다).
- 출력: `data/articles_<날짜>.json` (title, link, source, published_at, rss_summary)
- 피드 하나가 실패해도 stderr에 경고만 남기고 나머지 피드로 계속 진행한다. 실행 후 몇 개
  피드가 실패했는지 요약에 포함한다.

## 2. 원문 정독 (Claude가 직접 WebFetch로 수행)
`rss_summary`만으로는 내용이 부실한 경우가 많다. **선별된 10개 기사에 한해서만** 각 기사의
`link`를 WebFetch로 직접 읽는다. 전체 RSS 피드를 다 원문 fetch하는 것은 비효율적이므로,
이미 1단계에서 상위 10개로 좁혀놓은 뒤에만 원문을 정독하는 것이 핵심이다 (검색은 싸게,
해석은 선별된 것만 비싸게).

## 3. 요약 및 시사점 작성 (Claude가 직접 해석 — 스크립트로 대체 불가)
기사별로 다음을 직접 작성해서 `data/digest_<날짜>.json`에 저장한다:

```json
{
  "date": "YYYY-MM-DD",
  "generated_at": "ISO8601 타임스탬프",
  "articles": [
    {
      "title": "기사 원제 그대로",
      "link": "기사 URL",
      "source": "출처명",
      "published_at": "ISO8601",
      "summary": "2~3문장 요약. 기사 원문 기준으로 핵심 사실만 담는다.",
      "implication": "이 기사가 시사하는 점 1~2문장. 왜 중요한지, 무엇을 예고하는지."
    }
  ]
}
```

작성 원칙:
- `summary`는 RSS 요약을 그대로 옮기지 말고, WebFetch로 읽은 원문을 기준으로 2~3문장으로
  압축한다. 숫자·고유명사 등 핵심 사실은 누락하지 않는다.
- `implication`은 기사 내용을 요약 반복하지 않는다. "이게 왜 중요한가", "다음에 어떤 일이
  예상되는가", "다른 플레이어에게 어떤 영향을 주는가" 중 하나 이상을 담아 판단을 보탠다.
- 기사 배열 순서는 `data/articles_<날짜>.json`의 선별 순서(최신순)를 유지한다.
- 원문 접속이 막혀 WebFetch가 실패하면 `rss_summary`를 기반으로 작성하되, 정보가 부족하다는
  한계를 감안해 단정적인 표현은 피한다.

## 4. 사이트 생성
```
python scripts/generate_site.py --input data/digest_<날짜>.json
```
- Jinja2로 `templates/site.html.j2`를 렌더링해 `docs/index.html`(오늘자, 항상 최신)과
  `docs/archive/<날짜>.html`(과거 기록 누적)을 생성한다.
- `docs/index.html` 하단에는 지난 아카이브 링크 목록이 자동으로 추가된다.
- `templates/site.css`도 `docs/site.css`로 함께 복사된다.

## 5. 배포
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

## 6. 완료 보고
다음을 요약해 보고한다: 수집 후보 수와 선별된 기사 수, 실패한 피드(있다면), 오늘 브리핑에
포함된 기사 제목 10개와 출처, 원문 WebFetch가 실패해 rss_summary로 대체 작성한 기사가
있었는지, 커밋/푸시 결과, `docs/index.html` 경로.
