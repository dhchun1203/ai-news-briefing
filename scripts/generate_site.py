#!/usr/bin/env python3
"""data/digest_<날짜>.json을 읽어 docs/index.html과 docs/archive/<날짜>.html을 렌더링한다."""
import argparse
import copy
import html
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

import seo_utils

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = TEMPLATES_DIR / "static"
CONFIG_DIR = ROOT / "config"
DEFAULT_DOCS_DIR = ROOT / "docs"

MAX_ARCHIVE_LINKS = 60
MAX_SEARCH_RESULTS_SOURCE_FILES = None  # 제한 없음 — 검색 인덱스는 archive 폴더 전체를 스캔


def load_source_types():
    """config/feeds.json의 feed name -> type(primary/press/community) 매핑을 읽는다.
    등록되지 않은 출처는 기본값 'press'로 취급한다."""
    feeds_path = CONFIG_DIR / "feeds.json"
    if not feeds_path.exists():
        return {}
    data = json.loads(feeds_path.read_text(encoding="utf-8"))
    return {f["name"]: f.get("type", "press") for f in data.get("feeds", [])}


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


def collect_weekly_labels(docs_dir: Path):
    weekly_dir = docs_dir / "weekly"
    if not weekly_dir.exists():
        return []
    return sorted((f.stem for f in weekly_dir.glob("*.html")), reverse=True)[:MAX_ARCHIVE_LINKS]


def save_archive_json(archive_dir: Path, raw_digest: dict):
    """이 날짜의 원본 digest(글로서리 링크화로 마크업이 섞이기 전의 순수 텍스트)를
    docs/archive/<날짜>.json으로 영구 보관한다. data/*.json은 git에 커밋되지 않아
    실행이 끝나면 사라지므로, 검색·주간 회고·용어사전 기능이 과거 데이터를 읽을 수
    있는 유일한 경로가 이 파일이다."""
    date = raw_digest["date"]
    payload = {
        "date": date,
        "generated_at": raw_digest.get("generated_at"),
        "daily_insight": raw_digest.get("daily_insight"),
        "glossary": raw_digest.get("glossary") or [],
        "articles": [
            {
                "title": a.get("title"),
                "link": a.get("link"),
                "source": a.get("source"),
                "published_at": a.get("published_at"),
                "summary_ko": a.get("summary_ko"),
                "summary_en": a.get("summary_en"),
                "implication_ko": a.get("implication_ko"),
                "implication_en": a.get("implication_en"),
            }
            for a in raw_digest.get("articles", [])
        ],
    }
    (archive_dir / f"{date}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def collect_glossary_terms(archive_dir: Path) -> list:
    """docs/archive/*.json 전체에서 glossary 배열을 모아 term_ko 기준으로 중복
    제거한다. 같은 용어가 여러 날 다시 등장하면 가장 최근(파일명 날짜 기준) 설명으로
    덮어쓴다 — 용어 설명이 시간이 지나며 더 다듬어질 수 있다고 보고, 과거 버전을
    따로 보존하지는 않는다. 결과는 term_ko 기준 가나다순으로 정렬한다(한글 음절은
    유니코드 코드포인트 순서가 자모 순서와 일치해 별도 정렬 규칙 없이도 가나다순이
    나온다)."""
    terms = {}
    if not archive_dir.exists():
        return []
    for f in sorted(archive_dir.glob("*.json")):  # 파일명이 YYYY-MM-DD라 문자열 정렬 = 날짜순
        if f.name.endswith(".sent.json"):
            continue
        try:
            day = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        date = day.get("date", f.stem)
        for g in day.get("glossary") or []:
            term_ko = g.get("term_ko")
            if not term_ko:
                continue
            entry = terms.setdefault(term_ko, {"term_ko": term_ko, "first_seen": date})
            entry["term_en"] = g.get("term_en", "")
            entry["explanation_ko"] = g.get("explanation_ko", "")
            entry["explanation_en"] = g.get("explanation_en", "")
            entry["last_seen"] = date
    return sorted(terms.values(), key=lambda t: t["term_ko"])


def build_glossary_page(docs_dir: Path, terms: list, site_url: str, verification: dict, og_image_url: str):
    """지금까지 브리핑에 등장한 모든 용어를 모아 docs/glossary.html로 렌더링한다.
    새로 작성하는 콘텐츠가 없다(Claude가 매일 이미 쓰는 glossary를 재활용) —
    generate_weekly_site.py의 '건너뛸 날도 있는' 판단형 단계와 달리, 이건
    search-index.json처럼 매 실행마다 항상 자동으로 다시 만드는 기계적 집계다."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    template = env.get_template("glossary.html.j2")
    page_url = f"{site_url}/glossary"
    html_out = template.render(
        terms=terms,
        generated_at=datetime.now().isoformat(),
        canonical_url=page_url,
        og_image_url=og_image_url,
        google_site_verification=verification["google_site_verification"],
        naver_site_verification=verification["naver_site_verification"],
        jsonld=seo_utils.build_glossary_page_jsonld(site_url, page_url, terms),
    )
    (docs_dir / "glossary.html").write_text(html_out, encoding="utf-8")
    return len(terms)


def build_search_index(archive_dir: Path, docs_dir: Path):
    """docs/archive/*.json 전체를 스캔해 검색용 인덱스 하나(docs/search-index.json)로
    합친다. 매번 archive 폴더 전체에서 다시 만들기 때문에, 이 스크립트를 여러 날짜에
    걸쳐 반복 실행해도 인덱스는 항상 현재 archive 폴더 상태와 일치한다(멱등적)."""
    entries = []
    for f in sorted(archive_dir.glob("*.json"), reverse=True):
        if f.name.endswith(".sent.json"):
            continue  # 발송 완료 마커(send_broadcast.py) — 검색 대상 원본이 아니다
        try:
            day = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for a in day.get("articles", []):
            entries.append(
                {
                    "date": day.get("date", f.stem),
                    "title": a.get("title", ""),
                    "link": a.get("link", ""),
                    "source": a.get("source", ""),
                    "summary_ko": a.get("summary_ko", ""),
                    "summary_en": a.get("summary_en", ""),
                }
            )
    (docs_dir / "search-index.json").write_text(
        json.dumps(entries, ensure_ascii=False), encoding="utf-8"
    )
    return len(entries)


def main():
    args = parse_args()
    digest = json.loads(Path(args.input).read_text(encoding="utf-8"))
    raw_digest = copy.deepcopy(digest)  # 글로서리 링크화(HTML 마크업 삽입) 이전의 순수 텍스트본

    source_types = load_source_types()
    for article in digest.get("articles", []):
        article["source_type"] = source_types.get(article.get("source"), "press")

    glossary_lookup = apply_glossary(digest)  # articles/daily_insight의 텍스트를 in-place로 치환

    date = digest["date"]
    articles = digest["articles"]
    generated_at = digest.get("generated_at", datetime.now().isoformat())
    daily_insight = digest.get("daily_insight")  # 선택 필드: 없으면 섹션 자체가 렌더링 안 됨

    docs_dir = Path(args.docs_dir)
    archive_dir = docs_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    save_archive_json(archive_dir, raw_digest)
    indexed_count = build_search_index(archive_dir, docs_dir)

    for css_name in ("site-base.css", "site-mobile.css", "site-desktop.css"):
        shutil.copyfile(TEMPLATES_DIR / css_name, docs_dir / css_name)
    for asset_name in ("favicon.svg", "og-image.png"):
        shutil.copyfile(STATIC_DIR / asset_name, docs_dir / asset_name)

    site_url = seo_utils.get_site_url()
    seo_utils.write_robots_txt(docs_dir, site_url)
    verification = seo_utils.load_verification_tags()
    # 글로서리 링크화(HTML 마크업)가 섞이기 전의 raw_digest에서 헤드라인을 가져온다 —
    # 이미지에 <button> 태그 같은 마크업이 그대로 찍히면 안 되므로.
    raw_headline_ko = (raw_digest.get("daily_insight") or {}).get("headline_ko", "")
    og_image_url = seo_utils.build_og_image_url(site_url, docs_dir, date, raw_headline_ko)

    glossary_terms = collect_glossary_terms(archive_dir)
    glossary_og_image_url = f"{site_url}/og-image.png"  # 용어사전은 날짜성 콘텐츠가 아니라 범용 카드 재사용
    glossary_count = build_glossary_page(docs_dir, glossary_terms, site_url, verification, glossary_og_image_url)

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    template = env.get_template("site.html.j2")

    past_archives = collect_archive_dates(archive_dir, date)
    weekly_labels = collect_weekly_labels(docs_dir)
    # 월/일요일에만 최신 주간 회고를 상단 배너로 노출한다(그 외 요일엔 하단 목록에서만 보임).
    # 회고는 일요일 실행 순서상 이 날짜의 사이트 생성 "이후"에 만들어지므로, 당일이 아니라
    # 다음날(월요일)부터 그 주 회고가 배너에 뜬다 — 의도된 동작.
    weekday = datetime.strptime(date, "%Y-%m-%d").weekday()  # 0=월요일 ... 6=일요일
    show_weekly_banner = weekday in (0, 6)

    index_url = f"{site_url}/"
    archive_url = f"{site_url}/archive/{date}"

    # docs/index.html (오늘자, 항상 최신)
    index_html = template.render(
        date=date,
        generated_at=generated_at,
        articles=articles,
        daily_insight=daily_insight,
        glossary=glossary_lookup,
        archives=past_archives,
        weekly_labels=weekly_labels,
        show_weekly_banner=show_weekly_banner,
        archive_link_prefix="archive/",
        weekly_link_prefix="weekly/",
        css_prefix="",
        home_link=None,
        is_archive=False,
        canonical_url=index_url,
        og_image_url=og_image_url,
        google_site_verification=verification["google_site_verification"],
        naver_site_verification=verification["naver_site_verification"],
        jsonld=seo_utils.build_archive_page_jsonld(site_url, index_url, date, generated_at, articles, daily_insight),
    )
    (docs_dir / "index.html").write_text(index_html, encoding="utf-8")

    # docs/archive/<날짜>.html (누적 보관) — 배너는 "오늘자" 사이트에만 노출하고
    # 과거 기록 페이지에는 넣지 않는다(그 날짜 시점 기준 배너라 의미가 없음).
    archive_html = template.render(
        date=date,
        generated_at=generated_at,
        articles=articles,
        daily_insight=daily_insight,
        glossary=glossary_lookup,
        archives=past_archives,
        weekly_labels=weekly_labels,
        show_weekly_banner=False,
        archive_link_prefix="",
        weekly_link_prefix="../weekly/",
        css_prefix="../",
        home_link="../index.html",
        is_archive=True,
        canonical_url=archive_url,
        og_image_url=og_image_url,
        google_site_verification=verification["google_site_verification"],
        naver_site_verification=verification["naver_site_verification"],
        jsonld=seo_utils.build_archive_page_jsonld(site_url, archive_url, date, generated_at, articles, daily_insight),
    )
    (archive_dir / f"{date}.html").write_text(archive_html, encoding="utf-8")

    sitemap_count = seo_utils.build_sitemap(docs_dir, site_url, date)

    print(f"생성 완료: {docs_dir / 'index.html'}, {archive_dir / f'{date}.html'}")
    print(
        f"기사 {len(articles)}건, 지난 아카이브 {len(past_archives)}건, 검색 인덱스 {indexed_count}건, "
        f"용어사전 {glossary_count}건, sitemap {sitemap_count}건"
    )


if __name__ == "__main__":
    main()
