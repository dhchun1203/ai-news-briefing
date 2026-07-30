#!/usr/bin/env python3
"""SEO/GEO(생성형 AI 검색 최적화) 관련 정적 파일·메타데이터를 만드는 공용 헬퍼.

generate_site.py와 generate_weekly_site.py 양쪽에서 import해서 쓴다. 이 모듈은
날짜별 digest 내용에 의존하지 않는 "부가 산출물"만 다룬다 — robots.txt/sitemap.xml은
매 실행마다 docs/ 전체를 다시 스캔해 재생성하는 멱등적 방식이라(search-index.json과
동일한 패턴), 여러 날짜에 걸쳐 반복 실행해도 항상 현재 상태와 일치한다.
"""
import json
import shutil
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = TEMPLATES_DIR / "static"
DEFAULT_SITE_URL = "https://www.dailyaithread.com"

# 모든 페이지가 공유하는 정적 자산. generate_site.py와 generate_weekly_site.py가 각각
# 똑같은 복사 루프를 갖고 있었는데, 새 자산(site.js)을 추가할 때 한쪽만 고치면 그
# 페이지에서만 조용히 404가 나므로 목록과 복사를 여기 한 곳으로 모았다.
SHARED_ASSETS = (
    TEMPLATES_DIR / "site-base.css",
    TEMPLATES_DIR / "site-mobile.css",
    TEMPLATES_DIR / "site-desktop.css",
    STATIC_DIR / "site.js",
    STATIC_DIR / "favicon.svg",
    STATIC_DIR / "og-image.png",
)


def copy_shared_assets(docs_dir: Path) -> None:
    """CSS/JS/아이콘 등 페이지 공용 자산을 docs/ 루트로 복사한다."""
    for src in SHARED_ASSETS:
        shutil.copyfile(src, docs_dir / src.name)

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
    # Disallow는 반드시 User-agent 그룹 "안"에 있어야 한다 — 빈 줄이 그룹을 끝내므로,
    # 마지막 그룹 뒤에 떼어 놓으면 robots.txt 규격상 어느 그룹에도 속하지 않아 통째로
    # 무시된다(예전에 그렇게 작성돼 있어서 원본 JSON 색인 금지가 전혀 걸리지 않았다).
    # `*.json`이 `*.sent.json`도 포함하므로 별도 줄은 두지 않는다.
    lines = ["User-agent: *", "Allow: /", "Disallow: /archive/*.json", ""]
    for ua in AI_CRAWLERS:
        lines += [f"User-agent: {ua}", "Allow: /", "Disallow: /archive/*.json", ""]
    lines.append(f"Sitemap: {site_url}/sitemap.xml")
    (docs_dir / "robots.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _weekly_lastmod(label: str, fallback: str) -> str:
    """'2026-W30' -> 그 ISO 주의 일요일(=end_date) 날짜 문자열.

    이 함수는 주간 빌드뿐 아니라 **매일 도는 일간 빌드에서도** build_sitemap을 통해
    호출된다. 따라서 docs/weekly/에 예상 못 한 이름의 파일이 하나라도 생기면
    (`split`/`int`/`fromisocalendar` 어디서든) 예외가 나면서 그날 사이트 생성 전체가
    죽는다 — sitemap의 lastmod 하나 때문에 파이프라인을 멈출 이유는 없으므로,
    해석에 실패하면 조용히 fallback(대개 오늘 날짜)을 쓴다."""
    try:
        iso_year, iso_week = label.split("-W")
        return date_cls.fromisocalendar(int(iso_year), int(iso_week), 7).isoformat()
    except (ValueError, TypeError):
        return fallback


def _lang_urls(docs_dir: Path, site_url: str, today: str) -> list:
    """한 언어 트리(docs/ 또는 docs/en/)가 내보내는 URL 목록.

    build_sitemap이 한국어와 영어 트리에 각각 이 함수를 적용한다 — 언어별로 URL이
    분리돼 있으므로 sitemap에도 둘 다 들어가야 색인된다. 트레일링 슬래시는 붙이지
    않는다(cleanUrls가 실제로 서빙하는 정규 형태가 슬래시 없는 쪽이다)."""
    urls = [(f"{site_url}/", today)]
    archive_dir = docs_dir / "archive"
    if (archive_dir / "index.html").exists():
        urls.append((f"{site_url}/archive", today))
    if archive_dir.exists():
        for f in sorted(archive_dir.glob("*.html")):
            if f.stem == "index":
                continue
            urls.append((f"{site_url}/archive/{f.stem}", f.stem))
    weekly_dir = docs_dir / "weekly"
    if weekly_dir.exists():
        for f in sorted(weekly_dir.glob("*.html")):
            urls.append((f"{site_url}/weekly/{f.stem}", _weekly_lastmod(f.stem, today)))
    topics_dir = docs_dir / "topics"
    if (topics_dir / "index.html").exists():
        urls.append((f"{site_url}/topics", today))
    if topics_dir.exists():
        for f in sorted(topics_dir.glob("*.html")):
            if f.stem == "index":
                continue
            urls.append((f"{site_url}/topics/{f.stem}", today))
    if (docs_dir / "about.html").exists():
        urls.append((f"{site_url}/about", today))
    if (docs_dir / "glossary.html").exists():
        urls.append((f"{site_url}/glossary", today))
    glossary_dir = docs_dir / "glossary"
    if glossary_dir.exists():
        for f in sorted(glossary_dir.glob("*.html")):
            urls.append((f"{site_url}/glossary/{f.stem}", today))
    return urls


def build_sitemap(docs_dir: Path, site_url: str, today: str) -> int:
    """docs/archive/*.html과 docs/weekly/*.html 전체를 매번 다시 스캔해 sitemap.xml을
    재작성한다(전체 재빌드, 멱등적). collect_archive_dates()/collect_weekly_labels()는
    화면 노출용으로 최근 60개까지만 잘라내므로 여기서는 재사용하지 않고 직접 glob한다
    — sitemap은 색인 대상 전체를 담아야 한다."""
    # 한국어(루트)와 영어(/en/) 트리를 각각 훑는다. 언어별 URL이 분리돼 있어
    # 둘 다 sitemap에 있어야 각 언어판이 색인된다.
    urls = _lang_urls(docs_dir, site_url, today)
    en_dir = docs_dir / "en"
    if en_dir.exists():
        urls += _lang_urls(en_dir, f"{site_url}/en", today)

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


# 피드에 담을 최근 일수. 피드 리더는 새 항목만 가져가므로 전체 아카이브를 실을 이유가
# 없고(첫 구독 시 30일치가 한꺼번에 미읽음으로 쌓이면 오히려 방해다), sitemap과 달리
# 색인 완전성 요구도 없다.
RSS_MAX_ITEMS = 30
KST_TZ = timezone(timedelta(hours=9))


def _rss_pubdate(generated_at: str, date_str: str) -> str:
    """digest의 generated_at(ISO8601)을 RSS가 요구하는 RFC 822 형식으로 바꾼다.

    generated_at은 `datetime.now().isoformat()`이라 타임존이 없는 경우가 대부분이다.
    피드 리더는 타임존 없는 날짜를 각자 다르게(대개 UTC로) 해석해서 발행 시각이
    9시간씩 어긋나 보이므로, 타임존이 없으면 KST로 간주해 명시적으로 붙인다.
    파싱 자체가 실패하면 그 날짜의 08:00 KST(정기 발행 시각)로 대체한다 — 피드
    항목 하나의 시각 때문에 생성이 멈추면 안 된다."""
    try:
        dt = datetime.fromisoformat(generated_at)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(f"{date_str}T08:00:00")
        except (TypeError, ValueError):
            dt = datetime.now(KST_TZ)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST_TZ)
    return format_datetime(dt)


def _feed_item_description(day: dict, lang: str) -> str:
    """피드 항목 본문. 그날 인사이트 첫 문단 + 기사 10건의 제목·한 줄 요약.

    HTML을 CDATA로 감싸지 않고 통째로 이스케이프해서 텍스트 노드로 넣는다 — CDATA는
    본문에 `]]>`가 섞이면 조용히 깨지는데, 요약문은 사람이 아니라 매일 새로 생성되는
    텍스트라 그런 문자열이 들어올지 미리 보장할 수 없다."""
    insight = day.get("daily_insight") or {}
    paragraphs = insight.get("paragraphs_en" if lang == "en" else "paragraphs_ko") or []
    summary_key = "summary_en" if lang == "en" else "summary_ko"
    parts = []
    if paragraphs:
        parts.append(f"<p>{escape(paragraphs[0])}</p>")
    items = []
    for a in day.get("articles", []):
        title = escape(a.get("title") or "")
        link = escape(a.get("link") or "")
        summary = escape(a.get(summary_key) or "")
        items.append(f'<li><a href="{link}">{title}</a> — {summary}</li>')
    if items:
        parts.append("<ul>" + "".join(items) + "</ul>")
    return "".join(parts)


def build_rss_feed(docs_dir: Path, site_url: str, lang: str = "ko") -> int:
    """docs/archive/*.json을 다시 스캔해 RSS 2.0 피드를 통째로 재작성한다
    (build_sitemap과 같은 멱등 패턴).

    항목 단위는 기사가 아니라 **하루**다 — 이 사이트의 편집 단위가 '그날의 브리핑
    10건 + 인사이트'라서, 기사마다 항목을 쪼개면 피드 리더에서 하루에 10줄이 쏟아지고
    가장 중요한 크로스컷 인사이트가 어디에도 담기지 않는다.

    lang='ko'는 docs/feed.xml, 'en'은 docs/en/feed.xml로 나간다."""
    archive_dir = docs_dir / "archive"
    is_en = lang == "en"
    out_dir = docs_dir / "en" if is_en else docs_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    feed_path = f"{site_url}/en/feed.xml" if is_en else f"{site_url}/feed.xml"
    home_url = f"{site_url}/en/" if is_en else f"{site_url}/"

    if is_en:
        channel_title = "AI News Briefing · Daily AI Thread"
        channel_desc = "Ten AI stories a day, summarized with a take on why each one matters."
    else:
        channel_title = "AI 뉴스 브리핑 · Daily AI Thread"
        channel_desc = "매일 아침 AI 기사 10건의 요약과 시사점, 그리고 그날을 관통하는 인사이트."

    day_files = [f for f in sorted(archive_dir.glob("*.json"), reverse=True) if not f.name.endswith(".sent.json")] \
        if archive_dir.exists() else []

    items = []
    for f in day_files[:RSS_MAX_ITEMS]:
        try:
            day = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        date = day.get("date", f.stem)
        insight = day.get("daily_insight") or {}
        headline = insight.get("headline_en" if is_en else "headline_ko")
        if not headline:
            headline = f"AI News Briefing — {date}" if is_en else f"AI 뉴스 브리핑 — {date}"
        url = f"{site_url}/archive/{date}"
        items.append(
            "    <item>\n"
            f"      <title>{escape(headline)}</title>\n"
            f"      <link>{escape(url)}</link>\n"
            f'      <guid isPermaLink="true">{escape(url)}</guid>\n'
            f"      <pubDate>{_rss_pubdate(day.get('generated_at'), date)}</pubDate>\n"
            f"      <description>{escape(_feed_item_description(day, lang))}</description>\n"
            "    </item>"
        )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        f"    <title>{escape(channel_title)}</title>\n"
        f"    <link>{escape(home_url)}</link>\n"
        f"    <description>{escape(channel_desc)}</description>\n"
        f"    <language>{'en' if is_en else 'ko'}</language>\n"
        f'    <atom:link href="{escape(feed_path)}" rel="self" type="application/rss+xml"/>\n'
        + ("\n".join(items) + "\n" if items else "")
        + "  </channel>\n</rss>\n"
    )
    (out_dir / "feed.xml").write_text(xml, encoding="utf-8")
    return len(items)


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


# ---------- IndexNow ----------
# 사이트맵은 "여기 목록이 있으니 언제든 와서 보라"는 수동적 신호라 크롤러가 다시 읽어갈
# 때까지 기다려야 한다(실제로 구글은 우리 sitemap이 24개에서 116개로 늘어난 걸 며칠 뒤에도
# 모르고 있었다). IndexNow는 반대로 **바뀐 순간 우리가 먼저 알린다**. Bing이 확실히
# 지원하고, 매일 새 페이지가 하나씩 생기는 이 사이트 성격에 정확히 맞는다.
#
# 소유 증명은 API 키가 아니라 **키 파일**로 한다 — https://<호스트>/<키>.txt 가 그 키를
# 그대로 담고 있으면 그 호스트의 주인으로 인정된다. 그래서 이 키는 비밀이 아니고
# (공개 URL로 배포하는 게 프로토콜 설계 자체다) 저장소에 커밋해도 된다.


INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"


def load_indexnow_config() -> dict:
    """config/indexnow.json에서 키와 사용 여부를 읽는다. 파일이 없거나 키가 비어
    있으면 비활성으로 취급한다 — 설정이 빠졌다고 사이트 생성이 멈추면 안 된다."""
    path = CONFIG_DIR / "indexnow.json"
    if not path.exists():
        return {"key": None, "enabled": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"key": None, "enabled": False}
    key = (data.get("key") or "").strip() or None
    return {"key": key, "enabled": bool(data.get("enabled")) and key is not None}


def write_indexnow_key_file(docs_dir: Path) -> str | None:
    """docs/<키>.txt를 만든다. 내용은 키 문자열 그 자체여야 한다(프로토콜 규정).

    enabled가 false여도 파일은 만든다 — 키 파일이 배포돼 있어야 나중에 켜는 순간
    바로 동작하고, 파일만 있고 핑을 안 보내는 것은 아무 부작용이 없다.

    cleanUrls가 켜져 있어도 .txt는 영향을 받지 않는다(확장자 없는 경로로 308
    리다이렉트되는 것은 .html뿐). robots.txt가 정상 서빙되는 것으로 확인했다 —
    네이버 소유확인 HTML 파일이 이 리다이렉트 때문에 실패했던 것과는 다른 경우다."""
    key = load_indexnow_config()["key"]
    if not key:
        return None
    (docs_dir / f"{key}.txt").write_text(key, encoding="utf-8")
    return key


def submit_indexnow(site_url: str, urls: list, timeout: int = 15) -> tuple:
    """바뀐 URL 목록을 IndexNow에 알린다. (성공여부, 메시지)를 돌려준다.

    호출하는 쪽에서 예외를 신경 쓰지 않아도 되도록 여기서 모두 삼킨다 — 이건
    부가 기능이고, 검색엔진 통보 실패가 그날 파이프라인 전체를 무너뜨리면 안 된다
    (build_og_image_url의 폴백과 같은 태도).

    200(OK)과 202(Accepted) 둘 다 성공이다. 202는 "접수했고 키는 나중에 검증한다"는
    뜻이라, 키 파일이 막 배포된 직후에는 이 응답이 정상적으로 나온다."""
    import urllib.error
    import urllib.request

    cfg = load_indexnow_config()
    if not cfg["enabled"]:
        return False, "IndexNow 비활성(config/indexnow.json)"
    if not urls:
        return False, "알릴 URL이 없음"

    host = site_url.split("://", 1)[-1].split("/", 1)[0]
    payload = json.dumps(
        {
            "host": host,
            "key": cfg["key"],
            "keyLocation": f"{site_url}/{cfg['key']}.txt",
            "urlList": urls,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        INDEXNOW_ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        # timeout을 반드시 준다 — 무인 실행이라 응답 없는 소켓에 매달리면 그날
        # 파이프라인이 통째로 멈춘다(send_broadcast.py에서 같은 사고가 있었다).
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.status
        if code in (200, 202):
            return True, f"HTTP {code}, {len(urls)}건 통보"
        return False, f"예상치 못한 응답 HTTP {code}"
    except urllib.error.HTTPError as e:
        # 422=URL이 호스트와 불일치, 403=키 검증 실패. 원인 파악에 필요하므로 코드를 남긴다.
        return False, f"HTTP {e.code} {e.reason}"
    except Exception as e:  # 네트워크 단절, DNS 실패, 타임아웃 등
        return False, f"{type(e).__name__}: {e}"


def build_breadcrumb(site_url: str, trail: list) -> dict:
    """BreadcrumbList 노드. trail은 [(이름, URL), ...] 순서 그대로 계층을 만든다.
    마지막 항목(현재 페이지)에도 URL을 넣어야 검색엔진이 위치를 확정할 수 있다."""
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": name, "item": url}
            for i, (name, url) in enumerate(trail)
        ],
    }


def load_about() -> dict:
    """config/about.json을 읽는다. 없거나 깨져 있으면 빈 dict를 돌려줘 About 페이지
    생성을 건너뛴다 — 부가 페이지 하나 때문에 매일 도는 사이트 생성이 멈추면 안 된다."""
    path = CONFIG_DIR / "about.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def build_about_page_jsonld(site_url: str, page_url: str, about: dict, lang: str = "ko") -> dict:
    """소개 페이지용 JSON-LD. AboutPage로 표시하고, 이 페이지가 설명하는 대상이
    우리 Organization임을 mainEntity로 명시한다 — "이 사이트가 무엇인가"를 묻는
    질의에 이 페이지가 답으로 잡히게 하는 연결이다."""
    node = {
        "@type": "AboutPage",
        "@id": f"{page_url}#page",
        "url": page_url,
        "name": "소개 — Daily AI Thread" if lang == "ko" else "About — Daily AI Thread",
        "description": about.get("tagline_ko" if lang == "ko" else "tagline_en", ""),
        "inLanguage": lang,
        "isPartOf": {"@id": f"{site_url}/#website"},
        "mainEntity": {"@id": f"{site_url}/#organization"},
    }
    crumb = build_breadcrumb(site_url, [
        ("홈" if lang == "ko" else "Home", f"{site_url}/" if lang == "ko" else f"{site_url}/en/"),
        ("소개" if lang == "ko" else "About", page_url),
    ])
    return {"@context": "https://schema.org", "@graph": _website_org_nodes(site_url, lang) + [node, crumb]}


def build_glossary_term_jsonld(site_url: str, page_url: str, term: dict, lang: str = "ko") -> dict:
    """용어 개별 페이지용 JSON-LD. DefinedTerm은 "[용어]는 [정의]다" 구조를 그대로
    표현하는 타입이라, 질문형 쿼리("MCP란?")에 이 페이지가 답으로 잡히게 하는 데
    가장 직접적인 마크업이다. 용어사전 전체(DefinedTermSet)에 속함을 함께 밝힌다."""
    node = {
        "@type": "DefinedTerm",
        "@id": f"{page_url}#term",
        "url": page_url,
        "name": term.get("term_ko" if lang == "ko" else "term_en", "") or term.get("term_ko", ""),
        "alternateName": [n for n in ([term.get("term_en" if lang == "ko" else "term_ko")]
                                      + list(term.get("aliases_ko") or [])) if n],
        "description": term.get("explanation_ko" if lang == "ko" else "explanation_en", ""),
        "inDefinedTermSet": {
            "@type": "DefinedTermSet",
            "@id": f"{site_url}/glossary#glossary",
            "url": f"{site_url}/glossary",
            "name": "AI 용어사전" if lang == "ko" else "AI Glossary",
        },
        "inLanguage": lang,
        "publisher": {"@id": f"{site_url}/#organization"},
    }
    base = site_url if lang == "ko" else f"{site_url}/en"
    crumb = build_breadcrumb(site_url, [
        ("홈" if lang == "ko" else "Home", f"{base}/"),
        ("용어사전" if lang == "ko" else "Glossary", f"{base}/glossary"),
        (term.get("term_ko" if lang == "ko" else "term_en", "") or term.get("term_ko", ""), page_url),
    ])
    return {"@context": "https://schema.org", "@graph": _website_org_nodes(site_url, lang) + [node, crumb]}


def _website_org_nodes(site_url: str, lang: str = "ko") -> list:
    """모든 페이지가 공유하는 WebSite/Organization 그래프 노드. 페이지마다 이걸
    JSON-LD @graph에 포함시켜, 크롤러가 페이지 하나만 읽어도 사이트 정체성을
    파악할 수 있게 한다(다른 페이지의 @id를 따라가지 않아도 됨)."""
    return [
        {
            "@type": "WebSite",
            "@id": f"{site_url}/#website",
            "url": f"{site_url}/",
            "name": "AI 뉴스 브리핑 · Daily AI Thread" if lang == "ko" else "Daily AI Thread · AI News Briefing",
            "inLanguage": lang,
            "publisher": {"@id": f"{site_url}/#organization"},
            # 사이트 내 검색을 실제로 제공하므로(/api/search) SearchAction을 선언한다.
            # 없는 기능을 선언하면 안 되는 마크업이라, 검색 API가 생긴 뒤에야 넣었다.
            "potentialAction": {
                "@type": "SearchAction",
                "target": {
                    "@type": "EntryPoint",
                    "urlTemplate": f"{site_url}/?q={{search_term_string}}",
                },
                "query-input": "required name=search_term_string",
            },
        },
        {
            "@type": "Organization",
            "@id": f"{site_url}/#organization",
            "name": "Daily AI Thread",
            # 한국어 표기는 공식 이름이 아니라 별칭으로 둔다 — 브랜드명이 채널마다
            # 다르면 검색엔진과 답변엔진이 같은 대상인지 확신하지 못한다.
            "alternateName": ["AI 뉴스 브리핑", "데일리 AI 스레드"],
            "url": f"{site_url}/",
            "logo": f"{site_url}/og-image.png",
            # 사이트 정체성 한 문장. About 페이지·홈 description·RSS 설명과 같은
            # 내용을 유지한다(config/about.json이 유일한 출처).
            "description": load_about().get("tagline_ko" if lang == "ko" else "tagline_en", ""),
        },
    ]


def load_faq() -> list:
    """config/faq.json을 읽는다. 파일이 없거나 깨져 있으면 빈 목록을 돌려줘서
    FAQ 섹션과 FAQPage JSON-LD가 통째로 빠지게 한다 — 부가 섹션 하나 때문에 매일
    도는 사이트 생성이 멈추면 안 된다(load_verification_tags와 같은 태도)."""
    path = CONFIG_DIR / "faq.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return [f for f in data.get("faq", []) if f.get("question_ko") and f.get("answer_ko")]


def build_faq_jsonld_node(faq: list, lang: str = "ko") -> dict:
    """FAQPage 노드. 답변엔진이 질문형 쿼리에 이 답변을 통째로 인용할 수 있게 하는
    조치라, 화면에 실제로 렌더링되는 문장과 같은 텍스트여야 한다(스키마 가이드라인상
    화면에 없는 내용을 FAQPage로 마크업하면 위반)."""
    q_key = "question_en" if lang == "en" else "question_ko"
    a_key = "answer_en" if lang == "en" else "answer_ko"
    return {
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": f.get(q_key) or f.get("question_ko", ""),
                "acceptedAnswer": {"@type": "Answer", "text": f.get(a_key) or f.get("answer_ko", "")},
            }
            for f in faq
        ],
    }


def build_topic_page_jsonld(site_url: str, page_url: str, topic: dict, entries: list, lang: str = "ko") -> dict:
    """토픽별 아카이브 페이지용 JSON-LD. 일별 브리핑 페이지와 같은 이유로
    CollectionPage + ItemList를 쓰고, 원문은 우리 저작물이 아니므로 citation으로
    분리한다(build_archive_page_jsonld 주석 참고)."""
    items = [
        {
            "@type": "ListItem",
            "position": i + 1,
            "item": {
                "@type": "Article",
                "headline": e.get("title", ""),
                "url": f"{site_url}/archive/{e.get('date', '')}",
                "datePublished": e.get("date", ""),
                "author": {"@type": "Organization", "name": "Daily AI Thread"},
                "articleSection": e.get("summary_ko" if lang == "ko" else "summary_en", ""),
                "citation": {
                    "@type": "NewsArticle",
                    "headline": e.get("title", ""),
                    "url": e.get("link", ""),
                    "publisher": {"@type": "Organization", "name": e.get("source", "")},
                },
            },
        }
        for i, e in enumerate(entries)
    ]
    node = {
        "@type": "CollectionPage",
        "@id": f"{page_url}#page",
        "url": page_url,
        "name": (f"{topic.get('label_ko', '')} — AI 뉴스 브리핑" if lang == "ko"
                 else f"{topic.get('label_en', '')} — AI News Briefing"),
        "description": topic.get("description_ko" if lang == "ko" else "description_en", ""),
        "inLanguage": lang,
        "isPartOf": {"@id": f"{site_url}/#website"},
        "publisher": {"@id": f"{site_url}/#organization"},
        "mainEntity": {"@type": "ItemList", "itemListElement": items},
    }
    return {"@context": "https://schema.org", "@graph": _website_org_nodes(site_url, lang) + [node]}


def build_archive_index_jsonld(site_url: str, page_url: str, months: list, lang: str = "ko") -> dict:
    """지난 브리핑 전체 목록 페이지용 JSON-LD. 크롤러가 이 한 페이지만 읽어도
    모든 날짜 페이지를 발견할 수 있게 ItemList로 전부 나열한다 — 홈이 최근 60일만
    링크해서 생기던 고립을 메우는 게 이 페이지의 존재 이유다."""
    base = site_url if lang == "ko" else f"{site_url}/en"
    items = []
    for month in months:
        for d in month.get("days", []):
            items.append(
                {
                    "@type": "ListItem",
                    "position": len(items) + 1,
                    "name": d.get("headline_ko" if lang == "ko" else "headline_en") or d.get("date", ""),
                    "url": f"{base}/archive/{d.get('date', '')}",
                }
            )
    node = {
        "@type": "CollectionPage",
        "@id": f"{page_url}#page",
        "url": page_url,
        "name": "지난 브리핑 전체 — AI 뉴스 브리핑" if lang == "ko" else "All Past Briefings — AI News Briefing",
        "inLanguage": lang,
        "isPartOf": {"@id": f"{site_url}/#website"},
        "publisher": {"@id": f"{site_url}/#organization"},
        "mainEntity": {"@type": "ItemList", "itemListElement": items},
    }
    return {"@context": "https://schema.org", "@graph": _website_org_nodes(site_url, lang) + [node]}


def build_topic_index_jsonld(site_url: str, page_url: str, topics: list, lang: str = "ko") -> dict:
    """토픽 목록 페이지용 JSON-LD. 각 토픽 페이지를 ItemList로 가리켜, 크롤러가
    이 한 페이지만 읽어도 토픽 페이지 전체를 발견할 수 있게 한다."""
    base = site_url if lang == "ko" else f"{site_url}/en"
    items = [
        {
            "@type": "ListItem",
            "position": i + 1,
            "name": t.get("label_ko" if lang == "ko" else "label_en", ""),
            "url": f"{base}/topics/{t.get('slug', '')}",
        }
        for i, t in enumerate(topics)
    ]
    node = {
        "@type": "CollectionPage",
        "@id": f"{page_url}#page",
        "url": page_url,
        "name": "주제별 브리핑 — AI 뉴스 브리핑" if lang == "ko" else "Browse by Topic — AI News Briefing",
        "inLanguage": lang,
        "isPartOf": {"@id": f"{site_url}/#website"},
        "publisher": {"@id": f"{site_url}/#organization"},
        "mainEntity": {"@type": "ItemList", "itemListElement": items},
    }
    return {"@context": "https://schema.org", "@graph": _website_org_nodes(site_url, lang) + [node]}


def build_archive_page_jsonld(site_url, page_url, date, generated_at, articles, daily_insight, faq=None, lang="ko") -> dict:
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
                    "url": f"{page_url}#article-{i + 1}",  # page_url이 이미 언어판 주소다
                    "author": {"@type": "Organization", "name": "Daily AI Thread"},
                    "articleSection": a.get("summary_ko" if lang == "ko" else "summary_en", ""),
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
        "name": (f"AI 뉴스 브리핑 — {date}" if lang == "ko" else f"AI News Briefing — {date}"),
        "datePublished": generated_at,
        "dateModified": generated_at,
        "inLanguage": lang,
        "isPartOf": {"@id": f"{site_url}/#website"},
        "publisher": {"@id": f"{site_url}/#organization"},
        "mainEntity": {"@type": "ItemList", "itemListElement": items},
    }
    insight_headline = (daily_insight or {}).get("headline_ko" if lang == "ko" else "headline_en")
    if insight_headline:
        node["about"] = {
            "@type": "Article",
            "headline": insight_headline,
            "author": {"@type": "Organization", "name": "Daily AI Thread"},
        }
    # FAQ는 홈(/, /en/)에서만 렌더링되므로 그때만 노드를 합류시킨다 — 화면에 없는
    # 내용을 FAQPage로 마크업하면 구조화 데이터 가이드라인 위반이다.
    graph = _website_org_nodes(site_url, lang) + [node]
    if faq:
        graph.append(build_faq_jsonld_node(faq, lang))
    return {"@context": "https://schema.org", "@graph": graph}


def build_weekly_page_jsonld(site_url, page_url, headline_ko, end_date, generated_at, paragraphs_ko, daily_briefings, lang="ko") -> dict:
    """주간 회고는 원문 요약이 아니라 그 주 daily_insight들을 Claude가 다시 종합한
    우리 원저작물이므로, 저작권 이슈 없이 순수 Article로 마크업한다."""
    node = {
        "@type": "Article",
        "@id": f"{page_url}#page",
        "url": page_url,
        "headline": headline_ko,  # 호출부가 언어에 맞는 값을 넘긴다
        "datePublished": end_date,
        "dateModified": generated_at,
        "inLanguage": lang,
        "author": {"@type": "Organization", "name": "Daily AI Thread"},
        "publisher": {"@id": f"{site_url}/#organization"},
        "isPartOf": {"@id": f"{site_url}/#website"},
        "articleBody": " ".join(paragraphs_ko or []),
        "mentions": [
            {"@type": "CreativeWork", "url": f"{site_url}/archive/{d['date']}"} for d in (daily_briefings or [])
        ],
    }
    return {"@context": "https://schema.org", "@graph": _website_org_nodes(site_url, lang) + [node]}


def build_glossary_page_jsonld(site_url: str, page_url: str, terms: list, lang: str = "ko") -> dict:
    """용어사전 페이지용 JSON-LD. schema.org가 정의문 콘텐츠에 딱 맞는 타입
    (DefinedTermSet/DefinedTerm)을 제공해서, 다른 페이지처럼 우회할 필요 없이
    바로 의미에 맞게 마크업할 수 있다 — GEO 관점에서도 "[용어]는 [정의]다" 구조를
    구조화 데이터로 한 번 더 못박아주는 셈이라 유리하다."""
    defined_terms = [
        {
            "@type": "DefinedTerm",
            "name": t["term_ko"] if lang == "ko" else (t.get("term_en") or t["term_ko"]),
            "alternateName": (t.get("term_en") or t["term_ko"]) if lang == "ko" else t["term_ko"],
            "description": t.get("explanation_ko" if lang == "ko" else "explanation_en", ""),
            "inDefinedTermSet": f"{page_url}#glossary",
        }
        for t in terms
    ]
    node = {
        "@type": "DefinedTermSet",
        "@id": f"{page_url}#glossary",
        "url": page_url,
        "name": "AI 용어사전" if lang == "ko" else "AI Glossary",
        "inLanguage": lang,
        "isPartOf": {"@id": f"{site_url}/#website"},
        "publisher": {"@id": f"{site_url}/#organization"},
        "hasDefinedTerm": defined_terms,
    }
    return {"@context": "https://schema.org", "@graph": _website_org_nodes(site_url, lang) + [node]}
