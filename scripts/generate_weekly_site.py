#!/usr/bin/env python3
"""data/weekly_<주차>.json을 읽어 docs/weekly/<주차>.html을 렌더링한다.

일별 daily_insight 헤드라인 목록은 docs/archive/<날짜>.json(generate_site.py가 매일
영구 보관해두는 원본 digest)에서 기계적으로 모은다 — Claude는 "이번 주 종합" 판단
(headline/paragraphs)만 작성하면 된다."""
import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "templates"
DEFAULT_DOCS_DIR = ROOT / "docs"


def parse_args():
    p = argparse.ArgumentParser(description="주간 회고 JSON으로 정적 페이지를 생성한다.")
    p.add_argument("--input", required=True, help="data/weekly_<주차>.json 경로")
    p.add_argument("--docs-dir", default=str(DEFAULT_DOCS_DIR), help="출력 docs/ 디렉토리")
    return p.parse_args()


def collect_daily_briefings(archive_dir: Path, start_date: str, end_date: str):
    """start_date~end_date(둘 다 포함) 범위의 docs/archive/<날짜>.json을 읽어
    (날짜, 그날의 daily_insight 헤드라인) 목록을 날짜순으로 만든다."""
    results = []
    if not archive_dir.exists():
        return results
    for f in archive_dir.glob("*.json"):
        date = f.stem
        if not (start_date <= date <= end_date):
            continue
        try:
            day = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        insight = day.get("daily_insight") or {}
        results.append(
            {
                "date": date,
                "headline_ko": insight.get("headline_ko", ""),
                "headline_en": insight.get("headline_en", ""),
            }
        )
    results.sort(key=lambda r: r["date"])
    return results


def collect_weekly_labels(weekly_dir: Path, current_label: str):
    labels = set()
    if weekly_dir.exists():
        for f in weekly_dir.glob("*.html"):
            labels.add(f.stem)
    labels.discard(current_label)
    return sorted(labels, reverse=True)


def main():
    args = parse_args()
    weekly = json.loads(Path(args.input).read_text(encoding="utf-8"))

    docs_dir = Path(args.docs_dir)
    weekly_dir = docs_dir / "weekly"
    weekly_dir.mkdir(parents=True, exist_ok=True)
    archive_dir = docs_dir / "archive"

    for css_name in ("site-base.css", "site-mobile.css", "site-desktop.css"):
        shutil.copyfile(TEMPLATES_DIR / css_name, docs_dir / css_name)

    week_label = weekly["week_label"]
    daily_briefings = collect_daily_briefings(archive_dir, weekly["start_date"], weekly["end_date"])
    past_weeklies = collect_weekly_labels(weekly_dir, week_label)

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    template = env.get_template("weekly.html.j2")

    html_out = template.render(
        week_label=week_label,
        start_date=weekly["start_date"],
        end_date=weekly["end_date"],
        headline_ko=weekly.get("headline_ko", ""),
        headline_en=weekly.get("headline_en", ""),
        paragraphs_ko=weekly.get("paragraphs_ko", []),
        paragraphs_en=weekly.get("paragraphs_en", []),
        daily_briefings=daily_briefings,
        past_weeklies=past_weeklies,
        generated_at=weekly.get("generated_at", datetime.now().isoformat()),
    )
    (weekly_dir / f"{week_label}.html").write_text(html_out, encoding="utf-8")

    print(f"주간 회고 생성 완료: {weekly_dir / f'{week_label}.html'}")
    print(f"이번 주 일별 브리핑 {len(daily_briefings)}건, 지난 주간 회고 {len(past_weeklies)}건")


if __name__ == "__main__":
    main()
