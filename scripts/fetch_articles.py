#!/usr/bin/env python3
"""config/feeds.json의 RSS 피드를 순회해 최근 기사 중 상위 N개를 골라 JSON으로 저장한다."""
import argparse
import json
import sys
from calendar import timegm
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FEEDS_PATH = ROOT / "config" / "feeds.json"
DEFAULT_DATA_DIR = ROOT / "data"

# 한 출처가 상위 목록을 독점하지 않도록 출처당 최대 채택 개수를 둔다.
MAX_PER_SOURCE = 3


def parse_args():
    p = argparse.ArgumentParser(description="RSS 피드에서 최근 AI 기사를 수집한다.")
    p.add_argument("--feeds", default=str(DEFAULT_FEEDS_PATH), help="feeds.json 경로")
    p.add_argument("--lookback-days", type=int, default=12, help="최근 며칠 이내 기사만 대상으로 할지")
    p.add_argument("--top-n", type=int, default=10, help="최종 선별할 기사 개수")
    p.add_argument("--max-per-source", type=int, default=MAX_PER_SOURCE, help="출처당 최대 채택 개수")
    p.add_argument("--output", default=None, help="출력 파일 경로 (기본: data/articles_<오늘날짜>.json)")
    return p.parse_args()


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

    candidates = []
    failed_feeds = []
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
            candidates.append(
                {
                    "title": title.strip(),
                    "link": link.strip(),
                    "source": name,
                    "published_at": published_at.isoformat(),
                    "rss_summary": entry_summary(entry).strip(),
                }
            )

    # 최신순 정렬 후, 출처 다양성을 지키면서 top-n을 채운다.
    candidates.sort(key=lambda a: a["published_at"], reverse=True)

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
        "articles": selected,
    }
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"수집 완료: 후보 {len(candidates)}개 중 {len(selected)}개 선별 -> {output_path}")
    if failed_feeds:
        print(f"실패한 피드: {', '.join(failed_feeds)}", file=sys.stderr)


if __name__ == "__main__":
    main()
