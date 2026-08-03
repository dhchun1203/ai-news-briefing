#!/usr/bin/env python3
"""data/weekly_<주차>.json을 읽어 docs/weekly/<주차>.html을 렌더링한다.

일별 daily_insight 헤드라인 목록은 docs/archive/<날짜>.json(generate_site.py가 매일
영구 보관해두는 원본 digest)에서 기계적으로 모은다 — Claude는 "이번 주 종합" 판단
(headline/paragraphs)만 작성하면 된다."""
import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

import seo_utils
# 주간 회고 페이지도 일별 페이지와 같은 상단 내비를 그리므로, 개수 계산을 한 곳에서
# 가져온다(두 스크립트가 다른 숫자를 보여주면 페이지를 옮길 때마다 값이 달라진다).
from generate_site import LANGS, collect_nav_counts, lang_root, lang_up_prefix, up_prefix

KST = ZoneInfo("Asia/Seoul")

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
        if f.name.endswith(".sent.json"):
            continue  # 발송 완료 마커(send_broadcast.py) — 일별 브리핑 원본이 아니다
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

    seo_utils.copy_shared_assets(docs_dir)

    week_label = weekly["week_label"]
    daily_briefings = collect_daily_briefings(archive_dir, weekly["start_date"], weekly["end_date"])
    past_weeklies = collect_weekly_labels(weekly_dir, week_label)
    generated_at = weekly.get("generated_at", datetime.now().isoformat())

    site_url = seo_utils.get_site_url()
    verification = seo_utils.load_verification_tags()
    page_url = f"{site_url}/weekly/{week_label}"
    # 일간 페이지와 같은 이유로 언어별 카드를 따로 그린다 — 영어판 공유 시 한국어
    # 문장이 박힌 미리보기가 뜨면 안 된다.
    og_image_urls = {
        lang: seo_utils.build_og_image_url(
            site_url, docs_dir, week_label, weekly.get(f"headline_{lang}", ""), lang)
        for lang in LANGS
    }

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    template = env.get_template("weekly.html.j2")

    ko_url = f"{site_url}/weekly/{week_label}"
    en_url = f"{site_url}/en/weekly/{week_label}"
    nav_counts = collect_nav_counts(archive_dir)
    for lang in LANGS:
        out_dir = lang_root(docs_dir, lang) / "weekly"
        out_dir.mkdir(parents=True, exist_ok=True)
        page_url = en_url if lang == "en" else ko_url
        (out_dir / f"{week_label}.html").write_text(
            template.render(
                lang=lang,
                lang_alt_url=(ko_url if lang == "en" else en_url),
                up=up_prefix(lang),
                lup=lang_up_prefix(lang=lang),
                week_label=week_label,
                start_date=weekly["start_date"],
                end_date=weekly["end_date"],
                headline_ko=weekly.get("headline_ko", ""),
                headline_en=weekly.get("headline_en", ""),
                paragraphs_ko=weekly.get("paragraphs_ko", []),
                paragraphs_en=weekly.get("paragraphs_en", []),
                daily_briefings=daily_briefings,
                past_weeklies=past_weeklies,
                nav_counts=nav_counts,
                generated_at=generated_at,
                canonical_url=page_url,
                og_image_url=og_image_urls[lang],
                hreflang_ko_url=ko_url,
                hreflang_en_url=en_url,
                google_site_verification=verification["google_site_verification"],
                naver_site_verification=verification["naver_site_verification"],
                jsonld=seo_utils.build_weekly_page_jsonld(
                    site_url, page_url,
                    weekly.get("headline_ko" if lang == "ko" else "headline_en", ""),
                    weekly["end_date"], generated_at,
                    weekly.get("paragraphs_ko" if lang == "ko" else "paragraphs_en", []),
                    daily_briefings, lang,
                ),
            ),
            encoding="utf-8",
        )

    # 일요일 당일 새로 생긴 주간 회고 페이지가 그날 배포되는 sitemap.xml에 바로
    # 반영되도록, generate_site.py(항상 먼저 실행됨)와 별개로 여기서도 재빌드한다.
    sitemap_count = seo_utils.build_sitemap(docs_dir, site_url, datetime.now(KST).strftime("%Y-%m-%d"))

    print(f"주간 회고 생성 완료: {weekly_dir / f'{week_label}.html'}")
    print(f"이번 주 일별 브리핑 {len(daily_briefings)}건, 지난 주간 회고 {len(past_weeklies)}건, sitemap {sitemap_count}건")


if __name__ == "__main__":
    main()
