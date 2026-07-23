#!/usr/bin/env python3
"""data/digest_<날짜>.json을 읽어 docs/index.html과 docs/archive/<날짜>.html을 렌더링한다."""
import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "templates"
DEFAULT_DOCS_DIR = ROOT / "docs"

MAX_ARCHIVE_LINKS = 60


def parse_args():
    p = argparse.ArgumentParser(description="digest JSON으로 정적 사이트를 생성한다.")
    p.add_argument("--input", required=True, help="data/digest_<날짜>.json 경로")
    p.add_argument("--docs-dir", default=str(DEFAULT_DOCS_DIR), help="출력 docs/ 디렉토리")
    return p.parse_args()


def collect_archive_dates(archive_dir: Path, current_date: str):
    dates = set()
    if archive_dir.exists():
        for f in archive_dir.glob("*.html"):
            dates.add(f.stem)
    dates.add(current_date)
    dates.discard(current_date)  # index에는 "지난" 아카이브만 보여준다
    return sorted(dates, reverse=True)[:MAX_ARCHIVE_LINKS]


def main():
    args = parse_args()
    digest = json.loads(Path(args.input).read_text(encoding="utf-8"))

    date = digest["date"]
    articles = digest["articles"]
    generated_at = digest.get("generated_at", datetime.now().isoformat())

    docs_dir = Path(args.docs_dir)
    archive_dir = docs_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    shutil.copyfile(TEMPLATES_DIR / "site.css", docs_dir / "site.css")

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    template = env.get_template("site.html.j2")

    past_archives = collect_archive_dates(archive_dir, date)

    # docs/index.html (오늘자, 항상 최신)
    index_html = template.render(
        date=date,
        generated_at=generated_at,
        articles=articles,
        archives=past_archives,
        archive_link_prefix="archive/",
        home_link=None,
        is_archive=False,
    )
    (docs_dir / "index.html").write_text(index_html, encoding="utf-8")

    # docs/archive/<날짜>.html (누적 보관)
    archive_html = template.render(
        date=date,
        generated_at=generated_at,
        articles=articles,
        archives=past_archives,
        archive_link_prefix="",
        home_link="../index.html",
        is_archive=True,
    )
    (archive_dir / f"{date}.html").write_text(archive_html, encoding="utf-8")

    print(f"생성 완료: {docs_dir / 'index.html'}, {archive_dir / f'{date}.html'}")
    print(f"기사 {len(articles)}건, 지난 아카이브 {len(past_archives)}건")


if __name__ == "__main__":
    main()
