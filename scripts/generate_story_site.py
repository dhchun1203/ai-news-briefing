#!/usr/bin/env python3
"""config/stories.json으로 이슈 타임라인 페이지(/story/<slug>)를 만든다.

**generate_site.py와 분리한 이유**: 매일 08:00 무인 파이프라인에 새 실패 지점을
더하지 않기 위해서다. 주간 회고(generate_weekly_site.py)가 이미 같은 구조다 —
별도 스크립트, 별도 실행, 실패해도 일간 발행에 영향 없음.

이슈는 매일 생기지 않으므로(아카이브 17일에서 다중일 이슈는 1건) 이 스크립트는
사람이 손으로 돌린다. 전량 재생성이라 몇 번을 돌려도 결과가 같다.

    py scripts/generate_story_site.py
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seo_utils  # noqa: E402
from generate_site import LANGS, collect_nav_counts, lang_root, lang_up_prefix, up_prefix  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "stories.json"
TEMPLATES_DIR = ROOT / "templates"
DEFAULT_DOCS_DIR = ROOT / "docs"

REQUIRED = ("slug", "title_ko", "title_en", "summary_ko", "summary_en", "events")


def load_stories(path: Path = CONFIG_PATH) -> list:
    """이슈 목록을 읽고 최소한의 형태를 검증한다.

    검증을 여기서 하는 이유: 이 데이터는 손으로 쓰기 때문에 오타가 곧 깨진 페이지가
    된다. 특히 events의 date/article이 틀리면 '그날 브리핑에서 보기' 링크가 404로
    가는데, 그건 이 페이지의 존재 이유(원본으로 되돌아갈 수 있다)를 정면으로 깬다.
    """
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    stories = []
    for s in data.get("stories", []):
        missing = [k for k in REQUIRED if not s.get(k)]
        if missing:
            raise ValueError(f"stories.json: {s.get('slug', '?')}에 {missing}이(가) 없습니다")
        events = sorted(s["events"], key=lambda e: e["date"])  # 시간순이 이 페이지의 전부다
        for e in events:
            if not e.get("date") or not e.get("article"):
                raise ValueError(f"stories.json: {s['slug']}의 event에 date/article이 없습니다")
        stories.append({**s, "events": events,
                        "first_date": events[0]["date"], "last_date": events[-1]["date"]})
    return stories


def verify_links(stories: list, docs_dir: Path) -> list:
    """각 event가 가리키는 아카이브 페이지와 기사 앵커가 실제로 있는지 본다.

    경고만 하고 생성은 계속한다 — 링크 하나 때문에 페이지 전체를 못 만드는 것보다
    만들고 알리는 편이 낫다. 다만 완료 보고에 반드시 남긴다."""
    problems = []
    for s in stories:
        for e in s["events"]:
            page = docs_dir / "archive" / f"{e['date']}.html"
            if not page.exists():
                problems.append(f"{s['slug']}: {e['date']} 아카이브 페이지 없음")
                continue
            anchor = f'id="article-{e["article"]}"'
            if anchor not in page.read_text(encoding="utf-8"):
                problems.append(f"{s['slug']}: {e['date']}에 article-{e['article']} 앵커 없음")
    return problems


def main():
    parser = argparse.ArgumentParser(description="이슈 타임라인 페이지를 생성한다.")
    parser.add_argument("--docs-dir", default=str(DEFAULT_DOCS_DIR))
    parser.add_argument("--config", default=str(CONFIG_PATH))
    args = parser.parse_args()

    docs_dir = Path(args.docs_dir)
    stories = load_stories(Path(args.config))
    if not stories:
        print("이슈가 없습니다 — 생성할 것이 없습니다.")
        return

    problems = verify_links(stories, docs_dir)
    site_url = seo_utils.get_site_url()
    verification = seo_utils.load_verification_tags()
    nav_counts = collect_nav_counts(docs_dir / "archive")
    generated_at = datetime.now().isoformat(timespec="seconds")

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    template = env.get_template("story.html.j2")

    for story in stories:
        ko_url = f"{site_url}/story/{story['slug']}"
        en_url = f"{site_url}/en/story/{story['slug']}"
        for lang in LANGS:
            out_dir = lang_root(docs_dir, lang) / "story"
            out_dir.mkdir(parents=True, exist_ok=True)
            page_url = en_url if lang == "en" else ko_url
            (out_dir / f"{story['slug']}.html").write_text(
                template.render(
                    lang=lang,
                    lang_alt_url=(ko_url if lang == "en" else en_url),
                    up=up_prefix(lang),
                    lup=lang_up_prefix(lang=lang),
                    story=story,
                    nav_counts=nav_counts,
                    generated_at=generated_at,
                    canonical_url=page_url,
                    hreflang_ko_url=ko_url,
                    hreflang_en_url=en_url,
                    # 날짜별 카드가 아니라 사이트 공용 카드를 쓴다 — 이슈 페이지는
                    # 특정 날짜의 콘텐츠가 아니다.
                    og_image_url=f"{site_url}/og-image.png",
                    google_site_verification=verification["google_site_verification"],
                    naver_site_verification=verification["naver_site_verification"],
                    jsonld=build_story_jsonld(site_url, page_url, story, lang, generated_at),
                ),
                encoding="utf-8",
            )

    # 목록 페이지 — 내비게이션의 "이슈"가 여기로 온다.
    index_template = env.get_template("stories.html.j2")
    ko_index, en_index = f"{site_url}/stories", f"{site_url}/en/stories"
    # 최근에 움직인 이슈가 위로.
    listed = sorted(stories, key=lambda s: s["last_date"], reverse=True)
    for lang in LANGS:
        page_url = en_index if lang == "en" else ko_index
        (lang_root(docs_dir, lang) / "stories.html").write_text(
            index_template.render(
                lang=lang,
                lang_alt_url=(ko_index if lang == "en" else en_index),
                up=up_prefix(lang),
                lup=lang_up_prefix(lang=lang),
                stories=listed,
                nav_counts=nav_counts,
                generated_at=generated_at,
                canonical_url=page_url,
                hreflang_ko_url=ko_index,
                hreflang_en_url=en_index,
                og_image_url=f"{site_url}/og-image.png",
                google_site_verification=verification["google_site_verification"],
                naver_site_verification=verification["naver_site_verification"],
                jsonld={
                    "@context": "https://schema.org",
                    "@type": "CollectionPage",
                    "name": "이슈 흐름" if lang == "ko" else "Story timelines",
                    "url": page_url,
                    "inLanguage": lang,
                    "hasPart": [
                        {"@type": "Article",
                         "headline": s["title_ko"] if lang == "ko" else s["title_en"],
                         "url": f"{site_url}{'' if lang == 'ko' else '/en'}/story/{s['slug']}"}
                        for s in listed
                    ],
                },
            ),
            encoding="utf-8",
        )

    print(f"이슈 타임라인 {len(stories)}건 생성: " +
          ", ".join(f"/story/{s['slug']}({len(s['events'])}건)" for s in stories))
    if problems:
        print("[WARN] 링크 확인 필요:")
        for p in problems:
            print("  - " + p)
    else:
        print("모든 event의 아카이브 앵커 확인됨")
    # sitemap은 일부러 건드리지 않는다. build_sitemap은 매일 실행이 쓰는 코드라,
    # 일요일 발행 전에 손대지 않는다(발행 후 별도로 연결한다).


def build_story_jsonld(site_url: str, page_url: str, story: dict, lang: str, generated_at: str) -> dict:
    """이슈 페이지의 구조화 데이터. 시간순 사건 목록을 그대로 ItemList로 낸다 —
    답변엔진이 "그 사건 어떻게 됐나"에 이 순서를 인용할 수 있어야 한다."""
    title = story["title_ko"] if lang == "ko" else story["title_en"]
    summary = story["summary_ko"] if lang == "ko" else story["summary_en"]
    return {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": summary,
        "inLanguage": lang,
        "url": page_url,
        "datePublished": story["first_date"],
        "dateModified": generated_at,
        "publisher": {"@id": f"{site_url}/#organization"},
        "mainEntity": {
            "@type": "ItemList",
            # 화면과 같은 순서여야 한다 — 답변엔진이 인용할 때 사람이 보는 순서와
            # 다르면 "최신 상황"으로 옛 항목을 집는다.
            "itemListOrder": "https://schema.org/ItemListOrderDescending",
            "numberOfItems": len(story["events"]),
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": i,
                    "name": e["date"],
                    "description": e["line_ko"] if lang == "ko" else e["line_en"],
                    "url": f"{site_url}{'' if lang == 'ko' else '/en'}/archive/{e['date']}#article-{e['article']}",
                }
                for i, e in enumerate(reversed(story["events"]), 1)
            ],
        },
    }


if __name__ == "__main__":
    main()
