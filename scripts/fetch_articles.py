#!/usr/bin/env python3
"""config/feeds.json의 RSS 피드를 순회해 최근 기사 중 상위 N개를 골라 JSON으로 저장한다."""
import argparse
import json
import re
import sys
from calendar import timegm
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FEEDS_PATH = ROOT / "config" / "feeds.json"
DEFAULT_DATA_DIR = ROOT / "data"
DEFAULT_DOCS_DIR = ROOT / "docs"

# 한 출처가 상위 목록을 독점하지 않도록 출처당 최대 채택 개수를 둔다.
MAX_PER_SOURCE = 3

# 제목에서 고유명사/버전명을 추정하기 위해 제외할 흔한 대문자 시작 단어들
# (문장 맨 앞 단어나 흔한 관사·부사라 "화제성 키워드"로 보기엔 너무 일반적인 것들).
TITLE_STOPWORDS = {
    "The", "This", "That", "With", "From", "After", "Says", "New", "How",
    "Why", "What", "Its", "For", "And", "But", "Are", "Is", "Was", "Will",
    "AI", "Show", "Ask",
}


def parse_args():
    p = argparse.ArgumentParser(description="RSS 피드에서 최근 AI 기사를 수집한다.")
    p.add_argument("--feeds", default=str(DEFAULT_FEEDS_PATH), help="feeds.json 경로")
    p.add_argument("--lookback-days", type=int, default=12, help="최근 며칠 이내 기사만 대상으로 할지")
    p.add_argument("--top-n", type=int, default=10, help="최종 선별할 기사 개수")
    p.add_argument("--max-per-source", type=int, default=MAX_PER_SOURCE, help="출처당 최대 채택 개수")
    p.add_argument("--output", default=None, help="출력 파일 경로 (기본: data/articles_<오늘날짜>.json)")
    p.add_argument(
        "--docs-dir",
        default=str(DEFAULT_DOCS_DIR),
        help="과거 브리핑 기록(docs/archive/*.json)이 있는 디렉토리 — 중복 기사 제외에 사용",
    )
    return p.parse_args()


def load_published_links(docs_dir: Path) -> set:
    """과거에 이미 브리핑에 실렸던 기사 링크 전체를 docs/archive/*.json에서 모은다.
    generate_site.py가 매 실행마다 그날의 원본 digest를 이 경로에 영구 보관해두므로,
    여기 있는 링크는 이미 다른 날짜에 다뤄졌다는 뜻이라 다시 후보로 뽑지 않는다."""
    archive_dir = docs_dir / "archive"
    links = set()
    if not archive_dir.exists():
        return links
    for f in archive_dir.glob("*.json"):
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
    parsed = feedparser.parse(url)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"파싱 실패: {parsed.bozo_exception}")
    return parsed.entries


def main():
    args = parse_args()
    feeds_config = json.loads(Path(args.feeds).read_text(encoding="utf-8"))
    feeds = feeds_config["feeds"]

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.lookback_days)
    published_links = load_published_links(Path(args.docs_dir))

    candidates = []
    failed_feeds = []
    skipped_duplicates = 0
    for feed in feeds:
        name, url = feed["name"], feed["url"]
        try:
            entries = fetch_feed(name, url)
        except Exception as exc:  # 피드 하나가 실패해도 나머지는 계속 진행
            print(f"[WARN] {name} 수집 실패: {exc}", file=sys.stderr)
            failed_feeds.append(name)
            continue

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

    selected = []
    per_source_count = {}
    for article in candidates:
        if len(selected) >= args.top_n:
            break
        count = per_source_count.get(article["source"], 0)
        if count >= args.max_per_source:
            continue
        selected.append(article)
        per_source_count[article["source"]] = count + 1

    # 다양성 제한 때문에 top-n을 못 채웠다면, 남은 후보로 부족분을 채운다.
    if len(selected) < args.top_n:
        chosen_links = {a["link"] for a in selected}
        for article in candidates:
            if len(selected) >= args.top_n:
                break
            if article["link"] in chosen_links:
                continue
            selected.append(article)
            chosen_links.add(article["link"])

    today_label = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    output_path = Path(args.output) if args.output else DEFAULT_DATA_DIR / f"articles_{today_label}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = {
        "date": today_label,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": args.lookback_days,
        "feeds_total": len(feeds),
        "feeds_failed": failed_feeds,
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


if __name__ == "__main__":
    main()
