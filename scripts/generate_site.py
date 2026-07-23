#!/usr/bin/env python3
"""data/digest_<날짜>.json을 읽어 docs/index.html과 docs/archive/<날짜>.html을 렌더링한다."""
import argparse
import html
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "templates"
DEFAULT_DOCS_DIR = ROOT / "docs"

MAX_ARCHIVE_LINKS = 60


def build_glossary_maps(glossary):
    """glossary(list of {term_ko, term_en, explanation_ko, explanation_en})에서
    언어별 용어 목록과, 클릭 시 보여줄 설명을 찾기 위한 조회 테이블을 만든다."""
    terms_ko, terms_en, lookup = [], [], {}
    for g in glossary or []:
        entry = {"ko": g.get("explanation_ko", ""), "en": g.get("explanation_en", "")}
        term_ko = g.get("term_ko")
        term_en = g.get("term_en")
        if term_ko:
            terms_ko.append(term_ko)
            lookup[term_ko] = entry
        if term_en:
            terms_en.append(term_en)
            lookup[term_en] = entry
    return terms_ko, terms_en, lookup


def linkify_terms(text, terms, used):
    """텍스트를 HTML 이스케이프한 뒤, glossary에 등록된 용어와 정확히 일치하는 부분만
    클릭 가능한 버튼으로 감싼다. 겹치는 용어가 있을 때 더 긴 용어가 먼저 매칭되도록
    길이 내림차순으로 정렬해 하나의 정규식으로 한 번에 치환한다(중복 래핑 방지).

    `used`는 호출하는 쪽(기사 하나, 인사이트 섹션 하나)이 공유하는 set이다 — 이미 그
    안에서 한 번 링크된 용어는 두 번째부터는 평문으로 그대로 둬서, 같은 기사/섹션 안에서
    같은 용어가 여러 번 클릭 가능한 링크로 반복되지 않게 한다."""
    escaped = html.escape(text or "")
    unique_terms = sorted({t for t in terms if t}, key=len, reverse=True)
    if not unique_terms:
        return escaped
    escaped_terms = [html.escape(t) for t in unique_terms]
    pattern = re.compile("|".join(re.escape(t) for t in escaped_terms))

    def repl(m):
        matched = m.group(0)
        if matched in used:
            return matched
        used.add(matched)
        return f'<button type="button" class="term-link" data-term="{matched}">{matched}</button>'

    return pattern.sub(repl, escaped)


def apply_glossary(digest):
    """articles와 daily_insight의 텍스트 필드에 linkify_terms를 적용하고,
    이미 안전하게 이스케이프+마크업된 HTML 문자열로 그 자리에서 교체한다
    (템플릿에서는 |safe로 그대로 출력). 기사 하나(요약+시사점), 인사이트 섹션 하나마다
    언어별로 별도의 `used` 집합을 둬서, 그 범위 안에서는 같은 용어를 한 번만 링크한다."""
    glossary = digest.get("glossary") or []
    terms_ko, terms_en, lookup = build_glossary_maps(glossary)

    for article in digest.get("articles", []):
        used_ko, used_en = set(), set()
        article["summary_ko"] = linkify_terms(article.get("summary_ko", ""), terms_ko, used_ko)
        article["implication_ko"] = linkify_terms(article.get("implication_ko", ""), terms_ko, used_ko)
        article["summary_en"] = linkify_terms(article.get("summary_en", ""), terms_en, used_en)
        article["implication_en"] = linkify_terms(article.get("implication_en", ""), terms_en, used_en)

    insight = digest.get("daily_insight")
    if insight:
        used_ko, used_en = set(), set()
        insight["headline_ko"] = linkify_terms(insight.get("headline_ko", ""), terms_ko, used_ko)
        insight["paragraphs_ko"] = [linkify_terms(p, terms_ko, used_ko) for p in insight.get("paragraphs_ko", [])]
        insight["headline_en"] = linkify_terms(insight.get("headline_en", ""), terms_en, used_en)
        insight["paragraphs_en"] = [linkify_terms(p, terms_en, used_en) for p in insight.get("paragraphs_en", [])]
        if insight.get("watch_ko"):
            insight["watch_ko"] = linkify_terms(insight["watch_ko"], terms_ko, used_ko)
        if insight.get("watch_en"):
            insight["watch_en"] = linkify_terms(insight["watch_en"], terms_en, used_en)

    return lookup


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

    glossary_lookup = apply_glossary(digest)  # articles/daily_insight의 텍스트를 in-place로 치환

    date = digest["date"]
    articles = digest["articles"]
    generated_at = digest.get("generated_at", datetime.now().isoformat())
    daily_insight = digest.get("daily_insight")  # 선택 필드: 없으면 섹션 자체가 렌더링 안 됨

    docs_dir = Path(args.docs_dir)
    archive_dir = docs_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    for css_name in ("site-base.css", "site-mobile.css", "site-desktop.css"):
        shutil.copyfile(TEMPLATES_DIR / css_name, docs_dir / css_name)

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
        daily_insight=daily_insight,
        glossary=glossary_lookup,
        archives=past_archives,
        archive_link_prefix="archive/",
        css_prefix="",
        home_link=None,
        is_archive=False,
    )
    (docs_dir / "index.html").write_text(index_html, encoding="utf-8")

    # docs/archive/<날짜>.html (누적 보관)
    archive_html = template.render(
        date=date,
        generated_at=generated_at,
        articles=articles,
        daily_insight=daily_insight,
        glossary=glossary_lookup,
        archives=past_archives,
        archive_link_prefix="",
        css_prefix="../",
        home_link="../index.html",
        is_archive=True,
    )
    (archive_dir / f"{date}.html").write_text(archive_html, encoding="utf-8")

    print(f"생성 완료: {docs_dir / 'index.html'}, {archive_dir / f'{date}.html'}")
    print(f"기사 {len(articles)}건, 지난 아카이브 {len(past_archives)}건")


if __name__ == "__main__":
    main()
