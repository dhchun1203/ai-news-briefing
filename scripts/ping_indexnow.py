#!/usr/bin/env python3
"""그날 바뀐 페이지를 IndexNow로 검색엔진에 통보한다 (Bing 등 참여 엔진).

**반드시 배포(git push → Vercel) 뒤에 실행한다.** IndexNow는 "이 URL이 바뀌었으니
지금 와서 보라"는 신호라서, 배포 전에 부르면 크롤러가 아직 어제 콘텐츠인 페이지를
가져가 버린다. 그래서 이 스크립트는 통보 전에 **오늘자 페이지가 실제로 라이브에
떴는지 먼저 확인**하고, 뜨지 않으면 통보를 건너뛴다(잘못 알리는 것보다 안 알리는
편이 낫다 — 다음 날 실행과 sitemap이 결국 메운다).

구글은 IndexNow에 참여하지 않으므로 sitemap 방식을 그대로 유지한다.
"""
import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

import seo_utils

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DOCS_DIR = ROOT / "docs"

# 배포 전파를 기다리는 상한. Vercel은 보통 30~60초면 끝나지만 여유를 둔다.
DEPLOY_WAIT_SECONDS = 180
DEPLOY_POLL_INTERVAL = 10


def parse_args():
    p = argparse.ArgumentParser(description="바뀐 URL을 IndexNow로 통보한다.")
    p.add_argument("--date", required=True, help="오늘 날짜 (YYYY-MM-DD)")
    p.add_argument("--docs-dir", default=str(DEFAULT_DOCS_DIR))
    p.add_argument(
        "--weekly-label",
        default=None,
        help="그날 주간 회고를 새로 만들었다면 그 라벨(예: 2026-W30) — 함께 통보한다",
    )
    p.add_argument(
        "--skip-wait",
        action="store_true",
        help="배포 확인을 건너뛰고 바로 통보(수동 재실행 등, 이미 배포됐음이 확실할 때)",
    )
    return p.parse_args()


def collect_glossary_slugs(docs_dir: Path, date: str) -> list:
    """그날 digest에 등장한 용어의 슬러그 목록.

    **그날 것만** 고른다. 용어 개별 페이지는 매 실행마다 39개 전부 다시 렌더되지만,
    내용이 실제로 바뀐 건 그날 새로 등록되거나 설명이 갱신된 것뿐이다. 안 바뀐
    페이지까지 매일 밀어 넣으면 엔진이 스팸으로 보고 통보 자체를 무시하기 시작한다.

    슬러그 계산은 generate_site의 것을 그대로 쓴다 — 여기서 다시 구현하면 규칙이
    갈라지는 순간 존재하지 않는 URL을 통보하게 된다.

    파일이 없거나 깨졌어도 예외를 올리지 않는다. 용어 URL 몇 개를 못 붙이는 것이
    통보 전체를 막을 이유는 되지 않는다(무인 실행 원칙)."""
    try:
        import json

        from generate_site import glossary_slug

        data = json.loads((docs_dir / "archive" / f"{date}.json").read_text(encoding="utf-8"))
        slugs = []
        for term in data.get("glossary") or []:
            slug = glossary_slug(term.get("term_en"), term.get("term_ko"))
            if slug and slug not in slugs:
                slugs.append(slug)
        return slugs
    except Exception as e:
        print(f"용어 슬러그 수집 실패(통보는 계속): {type(e).__name__}: {e}", file=sys.stderr)
        return []


def build_changed_urls(site_url: str, date: str, weekly_label: str | None,
                       glossary_slugs: list = None) -> list:
    """그날 실제로 내용이 바뀌는 페이지만 고른다.

    IndexNow는 "바뀐 URL"을 알리는 프로토콜이라 안 바뀐 것까지 매일 밀어 넣으면
    안 된다(엔진이 스팸으로 보고 무시하기 시작한다). 그래서 116개 전체가 아니라
    아래 목록만 보낸다 — 나머지 과거 아카이브는 한 번 만들어지면 변하지 않으므로
    sitemap이 담당한다.

    **용어 개별 페이지를 포함하는 이유**: 2026-07-31에 실측해보니 6일 된
    /archive/2026-07-25는 sitemap에 있는데도 Bing이 "not discovered"였고, 같은 날
    IndexNow로 알린 /archive/2026-07-31만 당일 발견됐다. 신규 도메인은 크롤 예산이
    거의 없어 sitemap만으로는 발견 자체가 안 된다는 뜻이다. 용어 페이지는
    "[용어]는 [정의]다" 구조와 DefinedTerm 마크업을 갖춘 이 사이트 최고의 GEO
    자산인데, 알리지 않으면 그대로 묻힌다.

    두 언어판을 모두 넣는다. /en/ 은 별도 URL 트리라 각각 알려야 색인된다."""
    paths = [
        "/",                      # 오늘자 브리핑으로 교체됨
        "/archive/" + date,       # 그날 새로 생기는 페이지 (가장 중요)
        "/archive",               # 목록에 하루가 추가됨
        "/topics",                # 주제별 개수가 바뀜
        "/glossary",              # 새 용어가 추가됨
    ]
    if weekly_label:
        paths.append(f"/weekly/{weekly_label}")
    for slug in glossary_slugs or []:
        paths.append(f"/glossary/{slug}")

    urls = []
    for p in paths:
        urls.append(f"{site_url}{p}")
        # 영어판: 루트는 /en/, 나머지는 /en 접두사
        urls.append(f"{site_url}/en/" if p == "/" else f"{site_url}/en{p}")
    return urls


def wait_for_deploy(url: str) -> bool:
    """오늘자 페이지가 라이브에 떴는지 확인한다(200이면 배포 완료로 본다)."""
    import time

    deadline = time.monotonic() + DEPLOY_WAIT_SECONDS
    attempt = 0
    while True:
        attempt += 1
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    print(f"배포 확인됨 ({attempt}회 시도): {url}")
                    return True
        except urllib.error.HTTPError as e:
            if e.code == 200:
                return True
        except Exception:
            pass  # 아직 안 올라옴 — 계속 기다린다
        if time.monotonic() >= deadline:
            print(f"배포 확인 실패({DEPLOY_WAIT_SECONDS}초 초과): {url}", file=sys.stderr)
            return False
        time.sleep(DEPLOY_POLL_INTERVAL)


def main():
    args = parse_args()
    site_url = seo_utils.get_site_url()
    cfg = seo_utils.load_indexnow_config()

    if not cfg["enabled"]:
        print("IndexNow 비활성 — 건너뜀 (config/indexnow.json)")
        return 0

    # 키 파일이 라이브에 있어야 소유 증명이 된다. 없으면 통보해도 거부되므로 먼저 본다.
    key_url = f"{site_url}/{cfg['key']}.txt"
    glossary_slugs = collect_glossary_slugs(Path(args.docs_dir), args.date)
    urls = build_changed_urls(site_url, args.date, args.weekly_label, glossary_slugs)

    if not args.skip_wait:
        if not wait_for_deploy(f"{site_url}/archive/{args.date}"):
            print("오늘자 페이지가 아직 라이브에 없어 통보를 생략한다 "
                  "(sitemap과 다음 날 실행이 메운다).", file=sys.stderr)
            return 1
        if not wait_for_deploy(key_url):
            print(f"키 파일이 아직 배포되지 않았다: {key_url}\n"
                  "이번 통보는 생략한다 — 다음 실행부터 정상 동작한다.", file=sys.stderr)
            return 1

    ok, msg = seo_utils.submit_indexnow(site_url, urls)
    if ok:
        print(f"IndexNow 통보 완료: {msg}")
        for u in urls:
            print(f"  - {u}")
        return 0
    print(f"IndexNow 통보 실패: {msg}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
