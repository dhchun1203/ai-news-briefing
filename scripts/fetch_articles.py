#!/usr/bin/env python3
"""config/feeds.json의 RSS 피드를 순회해 최근 기사 중 상위 N개를 골라 JSON으로 저장한다."""
import argparse
import json
import re
import socket
import sys
from calendar import timegm
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import feedparser

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FEEDS_PATH = ROOT / "config" / "feeds.json"
DEFAULT_DATA_DIR = ROOT / "data"
KST = ZoneInfo("Asia/Seoul")
DEFAULT_DOCS_DIR = ROOT / "docs"

# 한 출처가 상위 목록을 독점하지 않도록 출처당 최대 채택 개수를 둔다.
MAX_PER_SOURCE = 3

# 피드 하나가 응답하지 않을 때 전체 실행이 멈추지 않도록 거는 소켓 타임아웃(초).
FEED_TIMEOUT_SEC = 20
# Cloudflare 뒤에 있는 매체들이 기본 urllib UA를 봇으로 보고 403으로 막는 일이 있다.
USER_AGENT = "ai-news-briefing-bot/1.0 (+https://www.dailyaithread.com)"

# "죽은 피드"(발행이 사실상 멈춘 매체) 판단 기준은 후보 선정용 --lookback-days와
# 별개로 고정한다. lookback-days를 신선도 때문에 짧게(1~2일) 줄이면, 발행 주기가
# 원래 느린 정상 피드(예: 격일 발행)까지 매번 "죽었다"고 오탐하게 되기 때문이다 —
# 이 값은 "그 매체가 정말 발행을 멈췄는지"만 넉넉하게 판단하는 별도 기준이다.
STALE_FEED_THRESHOLD_DAYS = 14

# 제목에서 고유명사/버전명을 추정하기 위해 제외할 흔한 대문자 시작 단어들
# (문장 맨 앞 단어나 흔한 관사·부사라 "화제성 키워드"로 보기엔 너무 일반적인 것들).
TITLE_STOPWORDS = {
    "The", "This", "That", "With", "From", "After", "Says", "New", "How",
    "Why", "What", "Its", "For", "And", "But", "Are", "Is", "Was", "Will",
    "AI", "Show", "Ask", "Meet", "You", "Your", "Watch", "Inside", "Explore",
}


def parse_args(argv=None):
    """argv=None이면 argparse가 평소처럼 sys.argv를 읽는다 — 테스트에서 실제 CLI
    인자 없이 기본값(예: --lookback-days 기본이 1인지)을 확인할 수 있도록 명시적
    argv를 받는 통로만 열어둔다."""
    p = argparse.ArgumentParser(description="RSS 피드에서 최근 AI 기사를 수집한다.")
    p.add_argument("--feeds", default=str(DEFAULT_FEEDS_PATH), help="feeds.json 경로")
    p.add_argument("--lookback-days", type=int, default=1, help="최근 며칠 이내 기사만 대상으로 할지")
    p.add_argument("--top-n", type=int, default=10, help="최종 선별할 기사 개수")
    p.add_argument("--max-per-source", type=int, default=MAX_PER_SOURCE, help="출처당 최대 채택 개수")
    p.add_argument("--output", default=None, help="출력 파일 경로 (기본: data/articles_<오늘날짜>.json)")
    p.add_argument(
        "--docs-dir",
        default=str(DEFAULT_DOCS_DIR),
        help="과거 브리핑 기록(docs/archive/*.json)이 있는 디렉토리 — 중복 기사 제외에 사용",
    )
    return p.parse_args(argv)


def load_published_links(docs_dir: Path) -> set:
    """과거에 이미 브리핑에 실렸던 기사 링크 전체를 docs/archive/*.json에서 모은다.
    generate_site.py가 매 실행마다 그날의 원본 digest를 이 경로에 영구 보관해두므로,
    여기 있는 링크는 이미 다른 날짜에 다뤄졌다는 뜻이라 다시 후보로 뽑지 않는다."""
    archive_dir = docs_dir / "archive"
    links = set()
    if not archive_dir.exists():
        return links
    for f in archive_dir.glob("*.json"):
        if f.name.endswith(".sent.json"):
            continue  # 발송 완료 마커(send_broadcast.py) — 기사 원본이 아니다
        try:
            day = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for a in day.get("articles", []):
            link = a.get("link")
            if link:
                links.add(link.strip())
    return links


def extract_keywords(title: str) -> set:
    """제목에서 대문자로 시작하는 고유명사 추정 단어(2글자 이상)와 4자리 이상 숫자
    (버전·연도 등)를 뽑는다. 여러 후보 기사가 같은 키워드를 공유하면 같은 사건을
    서로 다른 매체가 동시에 다루고 있다는 신호로 쓴다."""
    words = re.findall(r"[A-Z][A-Za-z0-9\-]{2,}|\d{4,}", title)
    return {w for w in words if w not in TITLE_STOPWORDS}


def compute_cross_source_counts(candidates: list) -> None:
    """후보들의 제목 키워드를 모아, 키워드별로 등장한 서로 다른 출처 집합을 구한 뒤
    각 후보에 '이 기사와 같은 사건을 다루는 것으로 보이는 다른 출처 수'를 매긴다.
    같은 출처가 같은 키워드를 여러 번 언급하는 건 교차 확인이 아니므로 세지 않는다.
    각 후보 dict에 `_cross_source_count`를 직접 채워 넣는다(in-place)."""
    keyword_sources = {}
    for c in candidates:
        for kw in extract_keywords(c["title"]):
            keyword_sources.setdefault(kw, set()).add(c["source"])

    for c in candidates:
        sources = set()
        for kw in extract_keywords(c["title"]):
            sources |= keyword_sources.get(kw, set())
        sources.discard(c["source"])
        c["_cross_source_count"] = len(sources)


SAME_STORY_MAX_DOC_FREQ = 6  # 이보다 많은 서로 다른 제목에 등장하면 "흔한 키워드"로 본다


def build_same_story_clusters(candidates: list) -> list:
    """제목 키워드가 겹치는 후보들을 "같은 사건"으로 묶는다(union-find). 단순히
    키워드 하나만 겹쳐도 묶으면 "OpenAI"처럼 그날 여러 무관한 기사에 두루 등장하는
    흔한 회사명 하나 때문에 완전히 다른 두 사건이 잘못 합쳐진다(예: "OpenAI가 새
    음성 모드 출시"와 "OpenAI 소송 피소"). 그래서 후보 전체에서 각 키워드가 몇 개의
    서로 다른 제목에 등장하는지(document frequency) 먼저 세고, 그날 기준 흔한
    키워드(`SAME_STORY_MAX_DOC_FREQ`개 초과 제목에 등장)는 "사건을 특정하지 못하는
    일반 명사"로 보고 매칭에서 제외한다. 남은 소수의 제목에만 등장하는 키워드
    (제품명·버전·구체적 수치 등, 예: "GPT-6", "AlphaFold")가 하나라도 겹치면 같은
    사건으로 판단한다. `compute_cross_source_counts`(순위 매기기용, 느슨한 기준)와는
    다른 용도라 별도 함수로 둔다 — 이건 "최종 선택에서 하나만 남길지" 판단에 쓰인다."""
    n = len(candidates)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    keyword_sets = [extract_keywords(c["title"]) for c in candidates]
    doc_freq = {}
    for kws in keyword_sets:
        for kw in kws:
            doc_freq[kw] = doc_freq.get(kw, 0) + 1
    specific_sets = [{kw for kw in kws if doc_freq[kw] <= SAME_STORY_MAX_DOC_FREQ} for kws in keyword_sets]

    for i in range(n):
        if not specific_sets[i]:
            continue
        for j in range(i + 1, n):
            if specific_sets[i] & specific_sets[j]:
                union(i, j)

    return [find(i) for i in range(n)]


def entry_published_at(entry):
    for key in ("published_parsed", "updated_parsed"):
        struct = entry.get(key)
        if struct:
            return datetime.fromtimestamp(timegm(struct), tz=timezone.utc)
    return None


def entry_summary(entry):
    if entry.get("summary"):
        return entry["summary"]
    if entry.get("description"):
        return entry["description"]
    return ""


def fetch_feed(name, url):
    # feedparser는 내부적으로 urllib을 쓰는데 기본 소켓 타임아웃이 None(무한)이라,
    # 응답을 끝내 주지 않는 호스트가 하나만 있어도 매일 08:00 무인 실행이 영원히
    # 멈춘다. 전역 소켓 타임아웃으로 상한을 건다(feedparser에 per-call 타임아웃
    # 인자가 없어 이 방법을 쓴다).
    socket.setdefaulttimeout(FEED_TIMEOUT_SEC)
    # 기본 UA(Python-urllib/x.x)는 Cloudflare가 봇으로 보고 403으로 막는 경우가 있다.
    # send_broadcast.py가 같은 이유로 이미 UA를 지정하고 있는데, 정작 Cloudflare 뒤에
    # 있는 피드(Wired, Ars Technica, TechCrunch)를 긁는 이쪽에는 빠져 있었다.
    parsed = feedparser.parse(url, agent=USER_AGENT)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"파싱 실패: {parsed.bozo_exception}")
    return parsed.entries


def main():
    args = parse_args()
    feeds_config = json.loads(Path(args.feeds).read_text(encoding="utf-8"))
    feeds = feeds_config["feeds"]

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.lookback_days)
    stale_cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_FEED_THRESHOLD_DAYS)
    published_links = load_published_links(Path(args.docs_dir))

    candidates = []
    failed_feeds = []
    stale_feeds = []
    skipped_duplicates = 0
    for feed in feeds:
        name, url = feed["name"], feed["url"]
        try:
            entries = fetch_feed(name, url)
        except Exception as exc:  # 피드 하나가 실패해도 나머지는 계속 진행
            print(f"[WARN] {name} 수집 실패: {exc}", file=sys.stderr)
            failed_feeds.append(name)
            continue

        # 피드가 200을 주고 항목도 있는데 전부 STALE_FEED_THRESHOLD_DAYS보다 오래된
        # 경우 = 그 매체가 사실상 발행을 멈춘 상태다. 실패로 잡히지 않아 조용히 0건만
        # 기여하므로, 눈에 띄게 보고해 사람이 피드 교체 여부를 판단할 수 있게 한다.
        # (candidates용 cutoff가 아니라 별도의 넉넉한 기준을 쓴다 — cutoff는 신선도
        # 때문에 1~2일까지 짧아질 수 있는데, 그 기준으로 죽음을 판단하면 며칠에 한 번
        # 발행하는 정상 피드까지 매번 죽었다고 오탐한다.)
        newest = max((d for d in (entry_published_at(e) for e in entries) if d), default=None)
        if entries and (newest is None or newest < stale_cutoff):
            stale_feeds.append(
                {"name": name, "latest": newest.date().isoformat() if newest else None}
            )
            print(
                f"[WARN] {name}: 최근 {STALE_FEED_THRESHOLD_DAYS}일 이내 기사 없음"
                f"(최신 {newest.date().isoformat() if newest else '날짜없음'}) — 피드가 죽었는지 확인 필요",
                file=sys.stderr,
            )

        for entry in entries:
            published_at = entry_published_at(entry)
            if published_at is None or published_at < cutoff:
                continue
            link = entry.get("link")
            title = entry.get("title")
            if not link or not title:
                continue
            link = link.strip()
            if link in published_links:
                # 다른 날짜의 브리핑에 이미 실린 기사는 다시 후보로 뽑지 않는다.
                skipped_duplicates += 1
                continue
            candidates.append(
                {
                    "title": title.strip(),
                    "link": link,
                    "source": name,
                    "published_at": published_at.isoformat(),
                    "rss_summary": entry_summary(entry).strip(),
                }
            )

    # 여러 출처가 동시에 다루는(화제성이 높은) 후보를 먼저 정렬하고, 그 안에서는
    # 최신순으로 정렬한 뒤, 출처 다양성을 지키면서 top-n을 채운다.
    compute_cross_source_counts(candidates)
    for c in candidates:
        c["cross_source_count"] = c.pop("_cross_source_count")
    candidates.sort(key=lambda a: (a["cross_source_count"], a["published_at"]), reverse=True)

    # 같은 사건을 다루는 후보가 여러 개 있어도(=cross_source_count가 높아 순위는
    # 위로 올라오지만) top-10 자리를 여러 개 차지하지 않도록, 사건 클러스터마다
    # 가장 순위 높은 것 하나만 채택한다 — 링크가 달라도 내용이 겹치는 기사가
    # 브리핑에 나란히 실리는 걸 막는 핵심 로직.
    cluster_ids = build_same_story_clusters(candidates)

    selected = []
    per_source_count = {}
    used_clusters = set()
    for article, cid in zip(candidates, cluster_ids):
        if len(selected) >= args.top_n:
            break
        if cid in used_clusters:
            continue
        count = per_source_count.get(article["source"], 0)
        if count >= args.max_per_source:
            continue
        selected.append(article)
        per_source_count[article["source"]] = count + 1
        used_clusters.add(cid)

    # 출처 다양성 제한 때문에 top-n을 못 채웠다면, 이번엔 그 제한만 풀고
    # 사건 클러스터 중복 방지는 유지한 채로 부족분을 채운다.
    if len(selected) < args.top_n:
        chosen_links = {a["link"] for a in selected}
        for article, cid in zip(candidates, cluster_ids):
            if len(selected) >= args.top_n:
                break
            if article["link"] in chosen_links or cid in used_clusters:
                continue
            selected.append(article)
            chosen_links.add(article["link"])
            used_clusters.add(cid)

    # 그래도 못 채웠다면(사건 종류 자체가 top-n보다 적을 만큼 뉴스가 적은 날)
    # 마지막으로 클러스터 중복 방지까지 풀어서 채운다 — 자리를 비워두는 것보다는 낫다.
    if len(selected) < args.top_n:
        chosen_links = {a["link"] for a in selected}
        for article in candidates:
            if len(selected) >= args.top_n:
                break
            if article["link"] in chosen_links:
                continue
            selected.append(article)
            chosen_links.add(article["link"])

    today_label = datetime.now(KST).strftime("%Y-%m-%d")
    output_path = Path(args.output) if args.output else DEFAULT_DATA_DIR / f"articles_{today_label}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = {
        "date": today_label,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": args.lookback_days,
        "feeds_total": len(feeds),
        "feeds_failed": failed_feeds,
        "feeds_stale": stale_feeds,  # 200은 오지만 룩백 기간 내 기사가 없는 = 사실상 죽은 피드
        "candidates_total": len(candidates),
        "skipped_duplicates": skipped_duplicates,
        "articles": selected,
    }
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"수집 완료: 후보 {len(candidates)}개(과거 중복 {skipped_duplicates}개 제외) 중 "
        f"{len(selected)}개 선별 -> {output_path}"
    )
    if failed_feeds:
        print(f"실패한 피드: {', '.join(failed_feeds)}", file=sys.stderr)
    if stale_feeds:
        detail = ", ".join(f"{s['name']}(최신 {s['latest'] or '날짜없음'})" for s in stale_feeds)
        print(f"오래된 피드(최근 기사 없음): {detail}", file=sys.stderr)


if __name__ == "__main__":
    main()
