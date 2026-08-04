#!/usr/bin/env python3
"""data/digest_<날짜>.json을 읽어 docs/index.html과 docs/archive/<날짜>.html을 렌더링한다."""
import argparse
import copy
import html
import json
import re
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

import seo_utils

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "templates"
CONFIG_DIR = ROOT / "config"
DEFAULT_DOCS_DIR = ROOT / "docs"

MAX_ARCHIVE_LINKS = 60
# 검색 인덱스에 담을 최근 일수 상한.
#
# 검색의 정상 경로는 이제 /api/search(Supabase)다. 이 파일은 그 API가 실패했을 때만
# 쓰이는 폴백이라, 예전처럼 넓게 담을 이유가 없어졌다 — 오히려 폴백 상황에서 통째로
# 내려받는 파일이므로 작을수록 낫다(180일이면 2.2MB, 30일이면 약 370KB).
# 전체 기간 검색은 서버가 담당하고, 여기서 잘린 날짜도 아카이브 페이지·sitemap에는
# 그대로 남아 검색엔진 색인에서는 빠지지 않는다.
SEARCH_INDEX_MAX_DAYS = 30

# 토픽 페이지 하나에 실을 기사 수 상한. 검색 인덱스와 달리 브라우저가 통째로 받아가는
# 파일은 아니지만, 상한이 없으면 인기 토픽 페이지가 몇 년 뒤 수천 건짜리 HTML이 된다.
TOPIC_PAGE_MAX_ENTRIES = 100

# 아카이브 인덱스의 영어 월 이름. locale에 의존하면 실행 환경(무인 컨테이너)에 따라
# 결과가 달라지므로 직접 둔다.
MONTH_NAMES_EN = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

# 사이트가 내보내는 언어. 한국어는 루트에, 영어는 /en/ 아래에 같은 구조로 미러링한다.
# 한 페이지에 두 언어를 함께 담던 방식은 검색엔진이 그 페이지의 주언어를 판단하기
# 어렵고 같은 정보가 반복돼 본문 밀도가 떨어진다.
LANGS = ("ko", "en")


def lang_root(docs_dir: Path, lang: str) -> Path:
    """해당 언어의 출력 루트. 영어는 docs/en/ 아래에 한국어와 같은 트리를 만든다."""
    return docs_dir if lang == "ko" else docs_dir / "en"


def lang_site_url(site_url: str, lang: str) -> str:
    """해당 언어의 URL 루트."""
    return site_url if lang == "ko" else f"{site_url}/en"


# 링크 접두사는 **절대경로**다. 상대경로를 쓰면 안 되는 이유가 실측으로 확인됐다:
#
#   /en/   200  (상대경로 기준 = /en/)
#   /en    200  (상대경로 기준 = /  )   ← 같은 파일, 서로 리다이렉트하지 않음
#
# cleanUrls가 켜져 있으면 모든 디렉터리 인덱스가 슬래시 유무 두 형태로 서빙되는데
# 둘의 상대경로 기준이 다르다. 즉 **한 파일이 두 기준으로 열리므로 상대경로로는
# 양쪽을 동시에 맞출 수 없다.** 이 저장소에서 같은 계열 사고가 세 번 났고
# (`/topics` 404, 영어판 언어 누수, /en 홈에서 한국어로 새는 것) 매번 "깊이를 더
# 정확히 계산"으로 고쳤지만 근본 원인이 이것이라 계속 재발했다.
#
# 절대경로는 어느 URL에서 열리든 같은 곳을 가리키므로 이 문제가 원천적으로 없다.
# dir_depth 인자는 호출부를 한꺼번에 고치지 않기 위해 남겨두었을 뿐 쓰이지 않는다.


def up_prefix(lang: str = "ko", dir_depth: int = 0) -> str:
    """**사이트 루트** 접두사 — 두 언어가 공유하는 자산용.

    CSS·JS·favicon·OG 이미지·search-index.json은 docs/ 루트에만 있고 언어별 사본이
    없다. 절대경로라 언어·깊이와 무관하게 항상 "/"다."""
    return "/"


def lang_up_prefix(dir_depth: int = 0, lang: str = "ko") -> str:
    """**언어 루트** 접두사 — 같은 언어판 안의 페이지 링크용.

    up_prefix()와 반드시 구분해야 한다. 페이지 링크에 up_prefix()를 쓰면 영어판이
    /en/ 밖으로 나가 한국어 페이지로 떨어진다.

    언어별로 각각 존재하는 것: index.html, about.html, glossary.html,
    glossary/<슬러그>, topics/, archive/, weekly/, feed.xml
    사이트 루트에만 있는 것(up_prefix 사용): CSS, JS, favicon, og-image, search-index"""
    return "/en/" if lang == "en" else "/"

KO_CHARS_PER_MINUTE = 500  # 한국어는 음절 수 기준(띄어쓰기 단위 "단어"가 불명확해서)
EN_WORDS_PER_MINUTE = 200  # 영어는 공백 기준 단어 수


def estimate_reading_minutes(raw_digest: dict) -> tuple:
    """기사 요약+시사점+오늘의 인사이트 전체 분량으로 예상 읽기 시간을 계산한다.
    글로서리 링크화(HTML 마크업)가 섞이기 전의 raw_digest에서 계산해야 <button>
    태그 같은 마크업이 글자 수에 끼어들지 않는다. 한국어는 음절 수, 영어는
    단어 수로 각각 따로 계산한다(같은 문장이라도 두 언어 분량 체감이 다름)."""
    texts_ko, texts_en = [], []
    for a in raw_digest.get("articles", []):
        texts_ko.append(a.get("summary_ko", "") + a.get("implication_ko", ""))
        texts_en.append(a.get("summary_en", "") + a.get("implication_en", ""))
    insight = raw_digest.get("daily_insight") or {}
    texts_ko.append(insight.get("headline_ko", "") + " ".join(insight.get("paragraphs_ko", [])))
    texts_en.append(insight.get("headline_en", "") + " ".join(insight.get("paragraphs_en", [])))

    ko_chars = sum(len(t) for t in texts_ko)
    en_words = sum(len(t.split()) for t in texts_en)
    if ko_chars == 0 and en_words == 0:
        return 0, 0
    minutes_ko = max(1, round(ko_chars / KO_CHARS_PER_MINUTE))
    minutes_en = max(1, round(en_words / EN_WORDS_PER_MINUTE))
    return minutes_ko, minutes_en


def load_source_types():
    """config/feeds.json의 feed name -> type(primary/press/community) 매핑을 읽는다.
    등록되지 않은 출처는 기본값 'press'로 취급한다."""
    feeds_path = CONFIG_DIR / "feeds.json"
    if not feeds_path.exists():
        return {}
    data = json.loads(feeds_path.read_text(encoding="utf-8"))
    return {f["name"]: f.get("type", "press") for f in data.get("feeds", [])}


def load_topics():
    """config/topics.json의 고정 taxonomy를 순서 그대로 읽는다. slug/label_ko가
    없는 항목은 URL이나 화면 라벨을 만들 수 없으므로 조용히 건너뛴다."""
    path = CONFIG_DIR / "topics.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return [t for t in data.get("topics", []) if t.get("slug") and t.get("label_ko")]


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
            if f.stem == "index":
                continue  # 아카이브 목록 페이지 — 날짜가 아니다
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
                # title_en은 원제가 한국어인 기사에만 있는 선택 필드다. 없을 때 null을
                # 써 넣으면 그것만으로 영속 원본이 바뀌어, 사이트를 재생성할 때마다
                # 과거 아카이브에 diff가 생긴다(실제로 그렇게 만들었다가 잡았다).
                # 그래서 값이 있을 때만 키를 남긴다 — 아래에서 None 항목을 걷어낸다.
                "title_en": a.get("title_en") or None,
                "link": a.get("link"),
                "source": a.get("source"),
                "published_at": a.get("published_at"),
                "summary_ko": a.get("summary_ko"),
                "summary_en": a.get("summary_en"),
                "implication_ko": a.get("implication_ko"),
                "implication_en": a.get("implication_en"),
                # 이 두 필드는 반드시 보존해야 한다 — data/*.json은 커밋되지 않아
                # 실행이 끝나면 사라지므로, 토픽 페이지(topics)와 커버리지 배지
                # (cross_source_count)가 과거 데이터를 읽을 수 있는 유일한 경로다.
                "topics": a.get("topics") or [],
                "cross_source_count": a.get("cross_source_count", 0),
                "related": a.get("related") or [],
            }
            for a in raw_digest.get("articles", [])
        ],
    }
    # 값이 없는 선택 필드는 키째로 뺀다. 이 파일은 영속 원본이라 "재생성해도 안 바뀐다"가
    # 지켜져야 하는데, null 키 하나만 새로 생겨도 매일 전 아카이브에 diff가 난다.
    for a in payload["articles"]:
        if a.get("title_en") is None:
            a.pop("title_en", None)
    (archive_dir / f"{date}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def glossary_slug(term_en: str, term_ko: str = "") -> str:
    """용어 개별 페이지(`/glossary/<slug>`)의 URL 조각을 만든다.

    영어 표기를 쓴다 — 한국어를 그대로 넣으면 URL이 퍼센트 인코딩으로 뭉개져
    사람도 검색엔진도 읽기 어렵다. 괄호 안 약어("Digital Markets Act (DMA)")는
    본명과 함께 남겨 `digital-markets-act-dma`가 되게 한다.

    한 번 정한 슬러그는 URL이므로 바꾸지 않는다 — 용어 설명이 나중에 다듬어져도
    `term_en` 표기만 그대로면 주소가 유지된다."""
    base = (term_en or term_ko or "").strip().lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return base


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
            entry = terms.setdefault(
                term_ko, {"term_ko": term_ko, "first_seen": date, "seen_dates": []})
            entry["term_en"] = g.get("term_en", "")
            entry["explanation_ko"] = g.get("explanation_ko", "")
            entry["explanation_en"] = g.get("explanation_en", "")
            entry["last_seen"] = date
            # 등장한 날짜를 전부 모은다. first/last만 남기면 47개 중 41개(87%)가 두
            # 값이 같아 같은 링크를 두 줄로 반복하게 되고, 여러 번 등장한 용어의
            # 나머지 날짜는 아예 사라진다. 용어 페이지는 검색 유입의 주력 착지점이라
            # 여기서 브리핑으로 건너갈 길이 많을수록 좋다.
            if date not in entry["seen_dates"]:
                entry["seen_dates"].append(date)
    return sorted(terms.values(), key=lambda t: t["term_ko"])


def group_glossary_by_slug(terms: list) -> list:
    """용어를 개별 페이지 단위(슬러그)로 묶는다.

    영어 표기가 같으면 같은 개념이다. 실제로 "정렬"과 "정렬(얼라인먼트)"가 한국어
    표기만 다르게 따로 등록돼 있었는데, 둘 다 `alignment`라 URL이 충돌했다. 이럴 때
    임의로 하나를 버리거나 `-2`를 붙이는 대신 **하나로 합치고 나머지 표기를 별칭으로
    남긴다** — 개념이 같으니 그게 사실에 맞고, 독자가 어느 표기로 찾아와도 같은
    페이지에 닿는다.

    대표 설명은 가장 최근에 등장한 것을 쓴다(collect_glossary_terms와 같은 방침 —
    설명은 시간이 지나며 다듬어질 수 있다)."""
    by_slug = {}
    for t in terms:
        slug = glossary_slug(t.get("term_en", ""), t.get("term_ko", ""))
        if not slug:
            continue
        entry = by_slug.get(slug)
        if entry is None:
            by_slug[slug] = {**t, "slug": slug, "aliases_ko": []}
            continue
        # 표기가 달라도 같은 개념이므로 등장 날짜는 합친다 — 대표 표기를 바꾸면서
        # 밀려난 쪽의 날짜를 버리면 "이 용어가 나온 브리핑"이 실제보다 적어 보인다.
        merged_dates = sorted(set(entry.get("seen_dates") or []) | set(t.get("seen_dates") or []))
        # 더 최근에 등장한 쪽을 대표로 삼고, 밀려난 표기는 별칭으로 보존한다.
        if (t.get("last_seen") or "") > (entry.get("last_seen") or ""):
            entry["aliases_ko"].append(entry["term_ko"])
            entry.update({k: v for k, v in t.items() if k != "aliases_ko"})
        elif t.get("term_ko") and t["term_ko"] != entry["term_ko"]:
            entry["aliases_ko"].append(t["term_ko"])
        entry["seen_dates"] = merged_dates
        entry["first_seen"] = merged_dates[0] if merged_dates else entry.get("first_seen")
        entry["last_seen"] = merged_dates[-1] if merged_dates else entry.get("last_seen")
    return sorted(by_slug.values(), key=lambda t: t["term_ko"])


def build_glossary_term_pages(docs_dir: Path, entries: list, site_url: str, verification: dict,
                              og_image_url: str, nav_counts: dict = None) -> int:
    """용어마다 `docs/glossary/<slug>.html`을 만든다.

    지금까지 용어 30개가 단일 페이지 안에만 있어서 개별 주소가 없었다. "MCP란?",
    "RAG와 파인튜닝 차이" 같은 질문형 검색은 반복적으로 발생하는데, 페이지가 없으면
    검색·인용 대상이 되지 못한다. 설명 텍스트는 이미 매일 작성되는 glossary를 그대로
    쓰므로 새로 쓰는 콘텐츠는 없다(토픽 페이지와 같은 재집계 패턴)."""
    if not entries:
        return 0
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    template = env.get_template("glossary-term.html.j2")
    generated_at = datetime.now().isoformat()

    for lang in LANGS:
        out_dir = lang_root(docs_dir, lang) / "glossary"
        out_dir.mkdir(parents=True, exist_ok=True)
        up, lup = up_prefix(lang), lang_up_prefix(lang=lang)
        for i, term in enumerate(entries):
            ko_url = f"{site_url}/glossary/{term['slug']}"
            en_url = f"{site_url}/en/glossary/{term['slug']}"
            page_url = en_url if lang == "en" else ko_url
            # 앞뒤 용어로 이동할 수 있게 해 페이지들이 서로 고립되지 않게 한다.
            neighbors = [e for e in (entries[i - 1] if i else None,
                                     entries[i + 1] if i + 1 < len(entries) else None) if e]
            (out_dir / f"{term['slug']}.html").write_text(
                template.render(
                    lang=lang,
                    lang_alt_url=(ko_url if lang == "en" else en_url),
                    up=up,
                    lup=lup,
                    term=term,
                    neighbors=neighbors,
                    nav_counts=nav_counts,
                    generated_at=generated_at,
                    canonical_url=page_url,
                    og_image_url=og_image_url,
                    hreflang_ko_url=ko_url,
                    hreflang_en_url=en_url,
                    google_site_verification=verification["google_site_verification"],
                    naver_site_verification=verification["naver_site_verification"],
                    jsonld=seo_utils.build_glossary_term_jsonld(site_url, page_url, term, lang),
                ),
                encoding="utf-8",
            )
    return len(entries)


def build_glossary_page(docs_dir: Path, terms: list, site_url: str, verification: dict, og_image_url: str, nav_counts: dict = None):
    """지금까지 브리핑에 등장한 모든 용어를 모아 docs/glossary.html로 렌더링한다.
    새로 작성하는 콘텐츠가 없다(Claude가 매일 이미 쓰는 glossary를 재활용) —
    generate_weekly_site.py의 '건너뛸 날도 있는' 판단형 단계와 달리, 이건
    search-index.json처럼 매 실행마다 항상 자동으로 다시 만드는 기계적 집계다."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    template = env.get_template("glossary.html.j2")
    term_lookup = {t["term_ko"]: {"ko": t.get("explanation_ko", ""), "en": t.get("explanation_en", "")} for t in terms}
    ko_url = f"{site_url}/glossary"
    en_url = f"{site_url}/en/glossary"
    for lang in LANGS:
        root = lang_root(docs_dir, lang)
        root.mkdir(parents=True, exist_ok=True)
        page_url = en_url if lang == "en" else ko_url
        root.joinpath("glossary.html").write_text(
            template.render(
                lang=lang,
                lang_alt_url=(ko_url if lang == "en" else en_url),
                up=up_prefix(lang),
                lup=lang_up_prefix(lang=lang),
                terms=terms,
                term_lookup=term_lookup,
                nav_counts=nav_counts,
                generated_at=datetime.now().isoformat(),
                canonical_url=page_url,
                og_image_url=og_image_url,
                hreflang_ko_url=ko_url,
                hreflang_en_url=en_url,
                google_site_verification=verification["google_site_verification"],
                naver_site_verification=verification["naver_site_verification"],
                jsonld=seo_utils.build_glossary_page_jsonld(site_url, page_url, terms, lang),
            ),
            encoding="utf-8",
        )
    return len(terms)


def _iter_archive_days(archive_dir: Path, newest_first: bool = True):
    """docs/archive/*.json을 날짜순으로 하나씩 돌려준다(파일명이 YYYY-MM-DD라
    문자열 정렬이 곧 날짜순). 발송 마커(.sent.json)와 깨진 파일은 건너뛴다.
    collect_glossary_terms/build_search_index/토픽 집계가 각자 갖고 있던 같은
    루프를 한 곳으로 모은 것."""
    if not archive_dir.exists():
        return
    for f in sorted(archive_dir.glob("*.json"), reverse=newest_first):
        if f.name.endswith(".sent.json"):
            continue
        try:
            yield json.loads(f.read_text(encoding="utf-8")), f.stem
        except (json.JSONDecodeError, OSError):
            continue


def collect_topic_entries(archive_dir: Path) -> dict:
    """아카이브 전체를 훑어 토픽 슬러그별 기사 목록을 만든다(최신 날짜가 앞).
    collect_glossary_terms와 같은 '매 실행마다 전량 재집계' 패턴이라, 과거 기사에
    나중에 토픽을 채워 넣어도 다음 실행에서 자동으로 반영된다."""
    by_topic = {}
    for day, stem in _iter_archive_days(archive_dir):
        date = day.get("date", stem)
        for a in day.get("articles", []):
            for slug in a.get("topics") or []:
                by_topic.setdefault(slug, []).append(
                    {
                        "date": date,
                        "title": a.get("title", ""),
                        "title_en": a.get("title_en", ""),
                        "link": a.get("link", ""),
                        "source": a.get("source", ""),
                        "summary_ko": a.get("summary_ko", ""),
                        "summary_en": a.get("summary_en", ""),
                    }
                )
    return by_topic


def build_topic_pages(docs_dir: Path, archive_dir: Path, site_url: str, verification: dict, og_image_url: str, nav_counts: dict = None):
    """docs/topics/<slug>.html과 docs/topics/index.html을 생성한다.

    기사가 하나도 없는 토픽은 페이지를 만들지 않는다 — 빈 페이지는 검색엔진에
    thin content 신호를 줄 뿐이고, 목록 페이지에서도 건수 0으로 링크 없이 표시된다.
    build_glossary_page와 마찬가지로 새로 쓰는 콘텐츠 없이 기존 데이터를 다시
    묶기만 하는 기계적 집계다."""
    topics = load_topics()
    if not topics:
        return 0, 0
    by_topic = collect_topic_entries(archive_dir)

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    template = env.get_template("topic.html.j2")
    generated_at = datetime.now().isoformat()
    summary = [dict(t, count=len(by_topic.get(t["slug"], []))) for t in topics]
    page_count = 0

    for lang in LANGS:
        topics_dir = lang_root(docs_dir, lang) / "topics"
        topics_dir.mkdir(parents=True, exist_ok=True)
        # 목록(/topics)은 cleanUrls로 세그먼트 1개가 되어 기준 디렉터리가 언어 루트,
        # 개별(/topics/<slug>)은 한 단계 아래다.
        up_index = up_item = up_prefix(lang)
        lup_index = lup_item = lang_up_prefix(lang=lang)

        for topic in topics:
            entries = by_topic.get(topic["slug"], [])[:TOPIC_PAGE_MAX_ENTRIES]
            if not entries:
                continue
            ko_url = f"{site_url}/topics/{topic['slug']}"
            en_url = f"{site_url}/en/topics/{topic['slug']}"
            page_url = en_url if lang == "en" else ko_url
            (topics_dir / f"{topic['slug']}.html").write_text(
                template.render(
                    lang=lang, lang_alt_url=(ko_url if lang == "en" else en_url),
                    up=up_item, lup=lup_item, tp=lup_item + "topics/",
                    topic=topic, entries=entries, topic_summary=summary, is_index=False,
                    nav_counts=nav_counts, generated_at=generated_at,
                    canonical_url=page_url, og_image_url=og_image_url,
                    hreflang_ko_url=ko_url, hreflang_en_url=en_url,
                    google_site_verification=verification["google_site_verification"],
                    naver_site_verification=verification["naver_site_verification"],
                    jsonld=seo_utils.build_topic_page_jsonld(site_url, page_url, topic, entries, lang),
                ),
                encoding="utf-8",
            )
            if lang == "ko":
                page_count += 1

        ko_index, en_index = f"{site_url}/topics", f"{site_url}/en/topics"
        index_url = en_index if lang == "en" else ko_index
        (topics_dir / "index.html").write_text(
            template.render(
                lang=lang, lang_alt_url=(ko_index if lang == "en" else en_index),
                up=up_index, lup=lup_index, tp=lup_index + "topics/",
                topic=None, entries=[], topic_summary=summary, is_index=True,
                nav_counts=nav_counts, generated_at=generated_at,
                canonical_url=index_url, og_image_url=og_image_url,
                hreflang_ko_url=ko_index, hreflang_en_url=en_index,
                google_site_verification=verification["google_site_verification"],
                naver_site_verification=verification["naver_site_verification"],
                jsonld=seo_utils.build_topic_index_jsonld(site_url, index_url, [t for t in summary if t["count"]], lang),
            ),
            encoding="utf-8",
        )
    return page_count, sum(t["count"] for t in summary)


def build_archive_index(docs_dir: Path, archive_dir: Path, site_url: str, verification: dict,
                        og_image_url: str, nav_counts: dict = None) -> int:
    """지난 브리핑 전체를 월별로 묶은 `docs/archive/index.html`을 만든다.

    홈은 `MAX_ARCHIVE_LINKS`(60일)까지만 링크해서, 그대로 두면 1년 뒤 300일치가
    사람 내비게이션에서 사라진다 — sitemap에는 남지만 크롤러는 링크를 따라가고,
    링크가 끊긴 페이지는 색인 우선순위가 떨어진다. 주간 회고가 그 주 날짜들을
    링크해 부분 경로를 주지만 회고는 건너뛸 수 있어 보장된 경로가 아니다.

    용어사전·토픽 페이지와 같은 "아카이브 전량 재집계" 패턴이라 매 실행마다 전체를
    다시 만든다(멱등)."""
    months = {}
    for day, stem in _iter_archive_days(archive_dir):
        date = day.get("date", stem)
        insight = day.get("daily_insight") or {}
        months.setdefault(date[:7], []).append(
            {
                "date": date,
                "headline_ko": insight.get("headline_ko", ""),
                "headline_en": insight.get("headline_en", ""),
            }
        )

    ordered = []
    for ym in sorted(months, reverse=True):
        year, mon = ym.split("-")
        ordered.append(
            {
                "label_ko": f"{year}년 {int(mon)}월",
                "label_en": f"{MONTH_NAMES_EN[int(mon) - 1]} {year}",
                "days": sorted(months[ym], key=lambda d: d["date"], reverse=True),
            }
        )
    total_days = sum(len(m["days"]) for m in ordered)

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    ko_url, en_url = f"{site_url}/archive", f"{site_url}/en/archive"
    for lang in LANGS:
        out_dir = lang_root(docs_dir, lang) / "archive"
        out_dir.mkdir(parents=True, exist_ok=True)
        page_url = en_url if lang == "en" else ko_url
        (out_dir / "index.html").write_text(
            env.get_template("archive-index.html.j2").render(
                lang=lang,
                lang_alt_url=(ko_url if lang == "en" else en_url),
                up=up_prefix(lang),
                lup=lang_up_prefix(lang=lang),
                months=ordered,
                total_days=total_days,
                nav_counts=nav_counts,
                generated_at=datetime.now().isoformat(),
                canonical_url=page_url,
                og_image_url=og_image_url,
                hreflang_ko_url=ko_url,
                hreflang_en_url=en_url,
                google_site_verification=verification["google_site_verification"],
                naver_site_verification=verification["naver_site_verification"],
                jsonld=seo_utils.build_archive_index_jsonld(site_url, page_url, ordered, lang),
            ),
            encoding="utf-8",
        )
    return total_days


def build_about_page(docs_dir: Path, site_url: str, verification: dict, og_image_url: str,
                     site_stats: dict = None, nav_counts: dict = None) -> bool:
    """`docs/about.html`을 만든다. 내용은 config/about.json 하나에서만 온다 —
    사이트 정체성 문장이 여러 곳에 흩어져 서로 달라지면, 검색엔진과 답변엔진이
    "이 사이트가 무엇인지" 확정하지 못한다."""
    about = seo_utils.load_about()
    if not about:
        return False
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    ko_url = f"{site_url}/about"
    en_url = f"{site_url}/en/about"
    for lang in LANGS:
        root = lang_root(docs_dir, lang)
        root.mkdir(parents=True, exist_ok=True)
        page_url = en_url if lang == "en" else ko_url
        (root / "about.html").write_text(
            env.get_template("about.html.j2").render(
                lang=lang,
                lang_alt_url=(ko_url if lang == "en" else en_url),
                up=up_prefix(lang),
                lup=lang_up_prefix(lang=lang),
                about=about,
                site_stats=site_stats,
                nav_counts=nav_counts,
                generated_at=datetime.now().isoformat(),
                canonical_url=page_url,
                og_image_url=og_image_url,
                hreflang_ko_url=ko_url,
                hreflang_en_url=en_url,
                google_site_verification=verification["google_site_verification"],
                naver_site_verification=verification["naver_site_verification"],
                jsonld=seo_utils.build_about_page_jsonld(site_url, page_url, about, lang),
            ),
            encoding="utf-8",
        )
    return True


def collect_nav_counts(archive_dir: Path) -> dict:
    """상단 내비게이션에 붙일 "뒤에 쌓인 개수". 숫자 자체가 들어갈 이유가 되므로
    (정보 향), 실제로 페이지가 만들어지는 토픽 — 기사 1건 이상 — 만 센다. 12개
    전부를 세면 숫자를 보고 들어온 독자가 빈 주제를 만난다.

    generate_weekly_site.py도 같은 내비를 렌더링하므로 이 함수를 import해서 쓴다."""
    by_topic = collect_topic_entries(archive_dir)
    return {
        "topics": sum(1 for t in load_topics() if by_topic.get(t["slug"])),
        # 슬러그로 합친 뒤의 개수를 센다 — 한국어 표기만 다른 같은 개념은 한 페이지로
        # 묶이므로, 병합 전 숫자를 쓰면 내비의 개수와 실제 페이지 수가 어긋난다.
        "terms": len(group_glossary_by_slug(collect_glossary_terms(archive_dir))),
        "days": sum(1 for _ in _iter_archive_days(archive_dir)),
    }


def _is_unbroken_streak(days: list) -> bool:
    """첫 발행일부터 마지막 발행일까지 하루도 거르지 않았는가.

    화면의 "하루도 빠짐없이"(every day since)는 `days` 숫자와 **다른 주장**이다.
    days는 발행한 날 수라 하루 걸러도 그냥 안 늘 뿐이지만, 저 문구는 결번이 없다고
    단언한다. 둘을 묶어두면 하루 거른 뒤에도 문구가 그대로 나가 거짓말이 된다.

    날짜를 못 읽으면 False를 돌려준다 — 확인할 수 없을 때는 주장하지 않는 쪽이 맞고,
    무인 실행이라 여기서 예외가 나면 그날 사이트 생성이 통째로 멈춘다."""
    if not days:
        return False
    try:
        parsed = sorted(date_cls.fromisoformat(d) for d in days)
    except (ValueError, TypeError):
        return False
    span = (parsed[-1] - parsed[0]).days + 1  # 양끝 포함
    return len(set(parsed)) == span


def collect_site_stats(archive_dir: Path, glossary_count: int) -> dict:
    """랜딩에 띄울 누적 지표(브리핑 일수·기사 수·용어 수·시작일).

    구독자 수는 일부러 넣지 않는다 — 경쟁 뉴스레터들이 소셜 프루프로 쓰는 숫자지만,
    아직 규모가 작을 때 노출하면 오히려 역효과다. 반면 '며칠째 빠짐없이 나왔는가'는
    시작 시점부터 정직하게 쌓이는 신뢰 신호라 처음부터 보여줄 수 있다."""
    days = [stem for _, stem in _iter_archive_days(archive_dir)]
    article_count = sum(len(day.get("articles", [])) for day, _ in _iter_archive_days(archive_dir))
    return {
        # **발행한 날 수**다(아카이브 파일 개수). "시작일로부터 경과일"이 아니라서
        # 하루 거르면 숫자가 정직하게 멈춘다 — 그게 이 지표를 신뢰 신호로 쓰는 이유다.
        "days": len(days),
        "articles": article_count,
        "terms": glossary_count,
        "since": min(days) if days else None,
        "unbroken": _is_unbroken_streak(days),
    }


def build_search_index(archive_dir: Path, docs_dir: Path):
    """docs/archive/*.json을 스캔해 검색용 인덱스 하나(docs/search-index.json)로
    합친다. 매번 archive 폴더에서 다시 만들기 때문에, 이 스크립트를 여러 날짜에
    걸쳐 반복 실행해도 인덱스는 항상 현재 archive 폴더 상태와 일치한다(멱등적).

    최근 SEARCH_INDEX_MAX_DAYS일치까지만 담는다. 이 파일은 검색창에 포커스가 가는
    순간 브라우저가 통째로 내려받으므로 무한정 커지면 안 된다 — 하루 약 14KB씩
    늘어나 상한이 없으면 1년이면 5MB에 이른다. 더 오래된 날짜도 아카이브 페이지와
    sitemap에는 그대로 남아 있어 검색엔진 색인에서 빠지지는 않는다."""
    entries = []
    # .sent.json은 발송 완료 마커(send_broadcast.py)라 검색 대상 원본이 아니다.
    day_files = [f for f in sorted(archive_dir.glob("*.json"), reverse=True) if not f.name.endswith(".sent.json")]
    for f in day_files[:SEARCH_INDEX_MAX_DAYS]:
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


def load_digest(path: Path) -> dict:
    """digest JSON을 읽고 필수 구조를 확인한다.

    이 파일은 매일 Claude가 손으로 쓰는 유일한 입력이라 파이프라인에서 가장 깨지기 쉬운
    지점이다. 검증 없이 바로 digest["date"] 같은 걸 꺼내 쓰면 오타 하나에 KeyError
    스택 트레이스만 남아 "무엇이 잘못됐는지"가 드러나지 않는다 — 무인 실행이라 그
    메시지가 사람이 받는 유일한 단서이므로, 어디가 어떻게 잘못됐는지 짚어준다.

    형식만 본다(내용의 품질은 판단하지 않는다). 선택 필드인 daily_insight/glossary는
    없어도 통과시키되, 있으면 타입은 확인한다."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise SystemExit(f"[ERROR] digest 파일을 읽지 못했습니다: {path} ({e})")
    try:
        digest = json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit(f"[ERROR] digest JSON 문법 오류: {path} {e.lineno}행 {e.colno}열 — {e.msg}")

    problems = []
    if not isinstance(digest, dict):
        raise SystemExit(f"[ERROR] digest 최상위는 객체여야 합니다: {path} (실제: {type(digest).__name__})")

    date = digest.get("date")
    if not isinstance(date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date or ""):
        problems.append(f'"date"가 YYYY-MM-DD 문자열이어야 합니다 (실제: {date!r})')

    articles = digest.get("articles")
    if not isinstance(articles, list) or not articles:
        problems.append(f'"articles"는 비어 있지 않은 배열이어야 합니다 (실제: {type(articles).__name__})')
    else:
        # published_at도 필수다 — 템플릿이 article.published_at[:10]으로 조건 없이
        # 잘라 쓰기 때문에 없으면 렌더링 단계에서 UndefinedError로 죽는다
        # (fetch_articles.py가 항상 채워주므로 실제로 빠지는 건 사람이 직접 digest를
        # 손볼 때뿐이지만, 그때 이유를 알 수 있어야 한다).
        required = (
            "title", "link", "source", "published_at",
            "summary_ko", "summary_en", "implication_ko", "implication_en",
        )
        valid_slugs = {t["slug"] for t in load_topics()}
        for i, a in enumerate(articles):
            if not isinstance(a, dict):
                problems.append(f"articles[{i}]가 객체가 아닙니다")
                continue
            missing = [k for k in required if not str(a.get(k) or "").strip()]
            if missing:
                problems.append(f"articles[{i}] ({a.get('title', '제목없음')!r}) 필드 누락/빈값: {', '.join(missing)}")

            # topics는 선택 필드지만(과거 아카이브에는 없다), 있으면 config/topics.json의
            # 슬러그여야 한다 — 오타 하나를 통과시키면 그 기사만 어느 토픽 페이지에도
            # 안 잡힌 채 조용히 사라진다. 그래서 유효 목록을 붙여 즉시 실패시킨다.
            topics = a.get("topics")
            if topics is not None:
                if not isinstance(topics, list):
                    problems.append(f'articles[{i}]의 "topics"는 배열이어야 합니다 (실제: {type(topics).__name__})')
                else:
                    unknown = [t for t in topics if t not in valid_slugs]
                    if unknown:
                        problems.append(
                            f"articles[{i}]의 topics에 등록되지 않은 슬러그: {', '.join(map(str, unknown))} "
                            f"(config/topics.json에 있는 값: {', '.join(sorted(valid_slugs))})"
                        )

            count = a.get("cross_source_count")
            if count is not None and (not isinstance(count, int) or isinstance(count, bool) or count < 0):
                problems.append(f'articles[{i}]의 "cross_source_count"는 0 이상의 정수여야 합니다 (실제: {count!r})')

            # related도 선택 필드다(과거 아카이브에는 없다). 있으면 링크를 화면에
            # 그대로 렌더하므로 최소한의 모양은 확인한다 — 빠진 필드가 있으면
            # 템플릿에서 빈 링크가 찍힌다.
            related = a.get("related")
            if related is not None:
                if not isinstance(related, list):
                    problems.append(f'articles[{i}]의 "related"는 배열이어야 합니다 (실제: {type(related).__name__})')
                else:
                    for k, r in enumerate(related):
                        if not isinstance(r, dict) or not str(r.get("link") or "").strip() or not str(r.get("title") or "").strip():
                            problems.append(f"articles[{i}].related[{k}]에 title/link가 없습니다")

    insight = digest.get("daily_insight")
    if insight is not None:
        if not isinstance(insight, dict):
            problems.append('"daily_insight"는 객체이거나 아예 없어야 합니다')
        else:
            for k in ("headline_ko", "headline_en"):
                if not (insight.get(k) or "").strip():
                    problems.append(f'daily_insight.{k}가 비어 있습니다 (섹션 전체를 생략하려면 daily_insight 자체를 빼세요)')
            for k in ("paragraphs_ko", "paragraphs_en"):
                if not isinstance(insight.get(k), list):
                    problems.append(f"daily_insight.{k}는 배열이어야 합니다")

    glossary = digest.get("glossary")
    if glossary is not None and not isinstance(glossary, list):
        problems.append('"glossary"는 배열이거나 아예 없어야 합니다')

    if problems:
        raise SystemExit(
            f"[ERROR] digest 형식 오류 ({path}):\n  - " + "\n  - ".join(problems)
        )
    return digest


def main():
    args = parse_args()
    digest = load_digest(Path(args.input))
    raw_digest = copy.deepcopy(digest)  # 글로서리 링크화(HTML 마크업 삽입) 이전의 순수 텍스트본
    reading_minutes_ko, reading_minutes_en = estimate_reading_minutes(raw_digest)

    source_types = load_source_types()
    # 슬러그만으로는 화면에 라벨을 찍을 수 없으므로, source_type과 같은 방식으로
    # 렌더링에 필요한 토픽 정보를 기사에 미리 붙여둔다(템플릿에서 조회 로직 없이 쓰도록).
    topic_lookup = {t["slug"]: t for t in load_topics()}
    for article in digest.get("articles", []):
        article["source_type"] = source_types.get(article.get("source"), "press")
        article["topic_chips"] = [topic_lookup[s] for s in (article.get("topics") or []) if s in topic_lookup]

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

    seo_utils.copy_shared_assets(docs_dir)

    site_url = seo_utils.get_site_url()
    seo_utils.write_robots_txt(docs_dir, site_url)
    # IndexNow 소유 증명용 키 파일. 실제 통보(핑)는 여기서 하지 않는다 — 배포 전에
    # 알리면 크롤러가 옛 콘텐츠를 가져가므로 배포 뒤 ping_indexnow.py가 맡는다.
    seo_utils.write_indexnow_key_file(docs_dir)
    verification = seo_utils.load_verification_tags()
    # 글로서리 링크화(HTML 마크업)가 섞이기 전의 raw_digest에서 헤드라인을 가져온다 —
    # 이미지에 <button> 태그 같은 마크업이 그대로 찍히면 안 되므로.
    raw_insight = raw_digest.get("daily_insight") or {}
    # 언어별로 카드를 따로 그린다. 예전엔 한국어 이미지 하나를 두 언어판이 공유해서,
    # /en/ 링크를 공유하면 영어 제목 옆에 한국어 문장이 박힌 카드가 떴다.
    og_image_urls = {
        lang: seo_utils.build_og_image_url(
            site_url, docs_dir, date, raw_insight.get(f"headline_{lang}", ""), lang)
        for lang in LANGS
    }

    glossary_terms = collect_glossary_terms(archive_dir)
    generic_og_image_url = f"{site_url}/og-image.png"  # 용어사전·토픽은 날짜성 콘텐츠가 아니라 범용 카드 재사용
    # 내비 개수는 어떤 페이지를 그리든 같아야 하므로 렌더링보다 먼저 한 번만 구한다.
    nav_counts = collect_nav_counts(archive_dir)
    glossary_entries = group_glossary_by_slug(glossary_terms)
    glossary_count = build_glossary_page(docs_dir, glossary_entries, site_url, verification, generic_og_image_url, nav_counts)
    term_page_count = build_glossary_term_pages(docs_dir, glossary_entries, site_url, verification, generic_og_image_url, nav_counts)
    topic_page_count, tagged_count = build_topic_pages(docs_dir, archive_dir, site_url, verification, generic_og_image_url, nav_counts)
    archive_index_days = build_archive_index(docs_dir, archive_dir, site_url, verification, generic_og_image_url, nav_counts)
    site_stats = collect_site_stats(archive_dir, glossary_count)
    build_about_page(docs_dir, site_url, verification, generic_og_image_url, site_stats, nav_counts)
    faq = seo_utils.load_faq()

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

    # 한국어는 루트에, 영어는 /en/ 아래 같은 구조로 각각 **한 언어만 담아** 내보낸다.
    # 예전에는 한 HTML에 두 언어를 다 넣고 CSS로 숨겼는데, 그러면 검색엔진이 그 페이지의
    # 주언어를 판단하기 어렵고 같은 정보가 두 벌 들어가 본문 밀도가 떨어진다.
    # 경로 접두사는 반드시 up_prefix()로만 계산한다(`/topics` 404 사고의 원인).
    ko_index_url = f"{site_url}/"
    en_index_url = f"{site_url}/en/"

    for lang in LANGS:
        root = lang_root(docs_dir, lang)
        root.mkdir(parents=True, exist_ok=True)
        # 자산(CSS·JS·favicon)은 사이트 루트에만 있고, 페이지는 언어별로 있다.
        # 둘을 같은 접두사로 쓰면 영어판 내비가 한국어 페이지로 떨어진다.
        up = up_archive = up_prefix(lang)
        lup = lup_archive = lang_up_prefix(lang=lang)
        this_index_url = en_index_url if lang == "en" else ko_index_url
        alt_index_url = ko_index_url if lang == "en" else en_index_url

        # 오늘자 홈
        (root / "index.html").write_text(
            template.render(
                lang=lang,
                lang_alt_url=alt_index_url,
                date=date,
                generated_at=generated_at,
                articles=articles,
                daily_insight=daily_insight,
                reading_minutes_ko=reading_minutes_ko,
                reading_minutes_en=reading_minutes_en,
                glossary=glossary_lookup,
                archives=past_archives,
                weekly_labels=weekly_labels,
                show_weekly_banner=show_weekly_banner,
                archive_link_prefix=lup + "archive/",
                weekly_link_prefix=lup + "weekly/",
                topic_link_prefix=lup + "topics/",
                feed_href=lup + "feed.xml",
                css_prefix=up,
                lang_prefix=lup,
                nav_current="",
                home_link=None,
                is_archive=False,
                site_stats=site_stats,
                nav_counts=nav_counts,
                faq=faq,
                canonical_url=this_index_url,
                og_image_url=og_image_urls[lang],
                google_site_verification=verification["google_site_verification"],
                naver_site_verification=verification["naver_site_verification"],
                hreflang_ko_url=ko_index_url,
                hreflang_en_url=en_index_url,
                jsonld=seo_utils.build_archive_page_jsonld(
                    site_url, this_index_url, date, generated_at, articles, daily_insight, faq, lang),
            ),
            encoding="utf-8",
        )

        # 그날의 아카이브 페이지 (배너는 "오늘자" 홈에만 — 과거 기록엔 의미가 없다)
        lang_archive_dir = root / "archive"
        lang_archive_dir.mkdir(parents=True, exist_ok=True)
        ko_archive_url = f"{site_url}/archive/{date}"
        en_archive_url = f"{site_url}/en/archive/{date}"
        (lang_archive_dir / f"{date}.html").write_text(
            template.render(
                lang=lang,
                lang_alt_url=(ko_archive_url if lang == "en" else en_archive_url),
                date=date,
                generated_at=generated_at,
                articles=articles,
                daily_insight=daily_insight,
                reading_minutes_ko=reading_minutes_ko,
                reading_minutes_en=reading_minutes_en,
                glossary=glossary_lookup,
                archives=past_archives,
                weekly_labels=weekly_labels,
                show_weekly_banner=False,
                # 절대경로라 형제 페이지도 언어 루트부터 적는다. 예전에는 같은
                # 디렉터리라 빈 문자열이었는데, /en/archive/<날짜>가 슬래시 없는
                # 형태로도 열리면 그 기준이 /en/이 아니라 /en이 된다.
                archive_link_prefix=lup_archive + "archive/",
                weekly_link_prefix=lup_archive + "weekly/",
                topic_link_prefix=lup_archive + "topics/",
                feed_href=lup_archive + "feed.xml",
                css_prefix=up_archive,
                lang_prefix=lup_archive,
                nav_current="archive",
                home_link=lup_archive + "index.html",
                is_archive=True,
                site_stats=site_stats,
                nav_counts=nav_counts,
                # FAQ는 홈에만 — 아카이브 페이지마다 같은 문답이 반복되면 중복 콘텐츠이고,
                # 매일 늘어나는 페이지 전부에 FAQPage 마크업이 붙는 것도 바람직하지 않다.
                faq=None,
                canonical_url=(en_archive_url if lang == "en" else ko_archive_url),
                og_image_url=og_image_urls[lang],
                google_site_verification=verification["google_site_verification"],
                naver_site_verification=verification["naver_site_verification"],
                hreflang_ko_url=ko_archive_url,
                hreflang_en_url=en_archive_url,
                jsonld=seo_utils.build_archive_page_jsonld(
                    site_url, (en_archive_url if lang == "en" else ko_archive_url),
                    date, generated_at, articles, daily_insight, None, lang),
            ),
            encoding="utf-8",
        )

    # sitemap보다 먼저 부를 이유는 없지만, 피드도 아카이브 전량 재스캔이라 이 날짜의
    # archive JSON이 이미 저장된 뒤여야 오늘자가 첫 항목으로 들어간다.
    feed_count = seo_utils.build_rss_feed(docs_dir, site_url, "ko")
    seo_utils.build_rss_feed(docs_dir, site_url, "en")
    sitemap_count = seo_utils.build_sitemap(docs_dir, site_url, date)

    print(f"생성 완료: {docs_dir / 'index.html'}, {archive_dir / f'{date}.html'}")
    print(
        f"기사 {len(articles)}건, 지난 아카이브 {len(past_archives)}건, 검색 인덱스 {indexed_count}건, "
        f"용어사전 {glossary_count}건, 토픽 페이지 {topic_page_count}개(분류된 기사 {tagged_count}건), "
        f"아카이브 목록 {archive_index_days}일, 피드 {feed_count}건, sitemap {sitemap_count}건"
    )


if __name__ == "__main__":
    main()
