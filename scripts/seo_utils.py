#!/usr/bin/env python3
"""SEO/GEO(생성형 AI 검색 최적화) 관련 정적 파일·메타데이터를 만드는 공용 헬퍼.

generate_site.py와 generate_weekly_site.py 양쪽에서 import해서 쓴다. 이 모듈은
날짜별 digest 내용에 의존하지 않는 "부가 산출물"만 다룬다 — robots.txt/sitemap.xml은
매 실행마다 docs/ 전체를 다시 스캔해 재생성하는 멱등적 방식이라(search-index.json과
동일한 패턴), 여러 날짜에 걸쳐 반복 실행해도 항상 현재 상태와 일치한다.
"""
import json
from datetime import date as date_cls
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DEFAULT_SITE_URL = "https://www.dailyaithread.com"

# AI 답변엔진 크롤러는 User-agent별로 가장 구체적인 블록만 따르는 경우가 많아,
# 와일드카드(*) 하나로 뭉뚱그리지 않고 명시적으로 하나씩 허용한다.
AI_CRAWLERS = (
    "GPTBot",
    "ChatGPT-User",
    "ClaudeBot",
    "Claude-User",
    "Claude-SearchBot",
    "Google-Extended",
    "PerplexityBot",
    "CCBot",
    "Bingbot",
)


def get_site_url() -> str:
    import os

    return os.environ.get("SITE_URL", DEFAULT_SITE_URL).rstrip("/")


def write_robots_txt(docs_dir: Path, site_url: str) -> None:
    lines = ["User-agent: *", "Allow: /", ""]
    for ua in AI_CRAWLERS:
        lines += [f"User-agent: {ua}", "Allow: /", ""]
    lines += [
        "Disallow: /archive/*.json",  # 원본 digest JSON은 검색엔진에 노출할 가치가 없다(HTML만 색인 대상)
        "Disallow: /archive/*.sent.json",
        "",
        f"Sitemap: {site_url}/sitemap.xml",
    ]
    (docs_dir / "robots.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _weekly_lastmod(label: str) -> str:
    """'2026-W30' -> 그 ISO 주의 일요일(=end_date) 날짜 문자열."""
    iso_year, iso_week = label.split("-W")
    return date_cls.fromisocalendar(int(iso_year), int(iso_week), 7).isoformat()


def build_sitemap(docs_dir: Path, site_url: str, today: str) -> int:
    """docs/archive/*.html과 docs/weekly/*.html 전체를 매번 다시 스캔해 sitemap.xml을
    재작성한다(전체 재빌드, 멱등적). collect_archive_dates()/collect_weekly_labels()는
    화면 노출용으로 최근 60개까지만 잘라내므로 여기서는 재사용하지 않고 직접 glob한다
    — sitemap은 색인 대상 전체를 담아야 한다."""
    archive_dir = docs_dir / "archive"
    weekly_dir = docs_dir / "weekly"
    urls = [(f"{site_url}/", today)]
    if archive_dir.exists():
        for f in sorted(archive_dir.glob("*.html")):
            urls.append((f"{site_url}/archive/{f.stem}", f.stem))
    if weekly_dir.exists():
        for f in sorted(weekly_dir.glob("*.html")):
            urls.append((f"{site_url}/weekly/{f.stem}", _weekly_lastmod(f.stem)))
    body = "\n".join(
        f"  <url><loc>{escape(loc)}</loc><lastmod>{lastmod}</lastmod></url>" for loc, lastmod in urls
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n</urlset>\n"
    )
    (docs_dir / "sitemap.xml").write_text(xml, encoding="utf-8")
    return len(urls)


def build_og_image_url(site_url: str, docs_dir: Path, identifier: str, headline_ko: str) -> str:
    """날짜(또는 주차)별 동적 OG 이미지를 시도하고, 성공하면 그 URL을, 실패하면
    (Pillow 미설치, 폰트 로딩 실패, 렌더링 오류 등 무엇이 됐든) 기존 정적
    og-image.png URL을 돌려준다. 이 함수는 절대로 예외를 밖으로 던지지 않는다 —
    OG 이미지는 부가 기능이라 이것 때문에 사이트 생성 자체가 멈추면 안 된다."""
    static_fallback = f"{site_url}/og-image.png"
    if not headline_ko:
        return static_fallback
    try:
        import og_image  # 지역 import: Pillow가 없어도 나머지 seo_utils 기능은 안 죽는다

        out_path = docs_dir / "og" / f"{identifier}.png"
        og_image.generate(identifier, headline_ko, out_path)
        return f"{site_url}/og/{identifier}.png"
    except Exception:
        return static_fallback


def load_verification_tags() -> dict:
    """config/site_verification.json에서 구글/네이버 사이트 소유 확인용 메타태그 값을
    읽는다. 값이 비어있으면 None을 돌려줘서 템플릿이 해당 meta 태그를 아예 렌더하지
    않게 한다 — 파일이 없거나 비어있어도 에러 없이 정상 동작한다."""
    path = CONFIG_DIR / "site_verification.json"
    if not path.exists():
        return {"google_site_verification": None, "naver_site_verification": None}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "google_site_verification": data.get("google_site_verification") or None,
        "naver_site_verification": data.get("naver_site_verification") or None,
    }


def _website_org_nodes(site_url: str) -> list:
    """모든 페이지가 공유하는 WebSite/Organization 그래프 노드. 페이지마다 이걸
    JSON-LD @graph에 포함시켜, 크롤러가 페이지 하나만 읽어도 사이트 정체성을
    파악할 수 있게 한다(다른 페이지의 @id를 따라가지 않아도 됨)."""
    return [
        {
            "@type": "WebSite",
            "@id": f"{site_url}/#website",
            "url": f"{site_url}/",
            "name": "AI 뉴스 브리핑 · Daily AI Thread",
            "inLanguage": ["ko", "en"],
            "publisher": {"@id": f"{site_url}/#organization"},
        },
        {
            "@type": "Organization",
            "@id": f"{site_url}/#organization",
            "name": "Daily AI Thread",
            "url": f"{site_url}/",
            "logo": f"{site_url}/og-image.png",
        },
    ]


def build_archive_page_jsonld(site_url, page_url, date, generated_at, articles, daily_insight) -> dict:
    """일별 브리핑(홈/아카이브 공용) 페이지용 JSON-LD. 이 사이트는 원문 기사의
    저작자가 아니라 큐레이션·분석 주체이므로, 우리 자체 요약/시사점만 Article로
    표시하고 원문은 citation으로 분리한다 — NewsArticle을 우리 것처럼 마크업하면
    저작권 오인 신호를 줄 수 있다."""
    items = []
    for i, a in enumerate(articles):
        items.append(
            {
                "@type": "ListItem",
                "position": i + 1,
                "item": {
                    "@type": "Article",
                    "headline": a.get("title", ""),
                    "url": f"{page_url}#article-{i + 1}",
                    "author": {"@type": "Organization", "name": "Daily AI Thread"},
                    "articleSection": a.get("summary_ko", ""),
                    "citation": {
                        "@type": "NewsArticle",
                        "headline": a.get("title", ""),
                        "url": a.get("link", ""),
                        "publisher": {"@type": "Organization", "name": a.get("source", "")},
                    },
                },
            }
        )
    node = {
        "@type": "CollectionPage",
        "@id": f"{page_url}#page",
        "url": page_url,
        "name": f"AI 뉴스 브리핑 — {date}",
        "datePublished": generated_at,
        "dateModified": generated_at,
        "inLanguage": ["ko", "en"],
        "isPartOf": {"@id": f"{site_url}/#website"},
        "publisher": {"@id": f"{site_url}/#organization"},
        "mainEntity": {"@type": "ItemList", "itemListElement": items},
    }
    if daily_insight and daily_insight.get("headline_ko"):
        node["about"] = {
            "@type": "Article",
            "headline": daily_insight["headline_ko"],
            "author": {"@type": "Organization", "name": "Daily AI Thread"},
        }
    return {"@context": "https://schema.org", "@graph": _website_org_nodes(site_url) + [node]}


def build_weekly_page_jsonld(site_url, page_url, headline_ko, end_date, generated_at, paragraphs_ko, daily_briefings) -> dict:
    """주간 회고는 원문 요약이 아니라 그 주 daily_insight들을 Claude가 다시 종합한
    우리 원저작물이므로, 저작권 이슈 없이 순수 Article로 마크업한다."""
    node = {
        "@type": "Article",
        "@id": f"{page_url}#page",
        "url": page_url,
        "headline": headline_ko,
        "datePublished": end_date,
        "dateModified": generated_at,
        "inLanguage": ["ko", "en"],
        "author": {"@type": "Organization", "name": "Daily AI Thread"},
        "publisher": {"@id": f"{site_url}/#organization"},
        "isPartOf": {"@id": f"{site_url}/#website"},
        "articleBody": " ".join(paragraphs_ko or []),
        "mentions": [
            {"@type": "CreativeWork", "url": f"{site_url}/archive/{d['date']}"} for d in (daily_briefings or [])
        ],
    }
    return {"@context": "https://schema.org", "@graph": _website_org_nodes(site_url) + [node]}
