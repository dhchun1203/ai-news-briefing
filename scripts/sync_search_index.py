#!/usr/bin/env python3
"""docs/archive/*.json의 기사를 Supabase search_articles 테이블로 동기화한다.

검색을 브라우저(정적 JSON 통째 다운로드)에서 서버로 옮기기 위한 적재 단계다.
generate_site.py가 그날 아카이브를 저장한 "뒤에" 실행해야 오늘자가 함께 올라간다.

매번 아카이브 전체를 다시 올린다. 오늘자만 올리는 편이 전송량은 적지만, 동기화가
하루 실패하면 그날 기사가 영영 검색에 안 잡히고 아무도 모른다 — 전량 upsert는
다음 실행이 알아서 빈 구멍을 메우는 자가 치유 속성을 준다(link가 기본키라 멱등).
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DOCS_DIR = ROOT / "docs"

# 한 번에 보내는 행 수. Supabase REST는 요청 본문 크기 제한이 있고, 기사 하나가
# 요약 두 벌을 포함해 1~2KB라 500행이면 대략 1MB 안쪽으로 들어온다.
BATCH_SIZE = 500
TIMEOUT_SEC = 30


class TableMissing(Exception):
    """search_articles 테이블이 아직 없다 = supabase/schema.sql을 실행하지 않은 상태.
    고장이 아니라 설정 미완료라 파이프라인을 멈추지 않고 경고만 남긴다."""


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="아카이브 기사를 Supabase 검색 테이블로 동기화한다.")
    p.add_argument("--docs-dir", default=str(DEFAULT_DOCS_DIR), help="docs/ 디렉토리")
    p.add_argument("--batch-size", type=int, default=BATCH_SIZE, help="한 번에 upsert할 행 수")
    p.add_argument("--dry-run", action="store_true", help="전송하지 않고 대상 건수만 출력한다")
    return p.parse_args(argv)


def collect_rows(archive_dir: Path) -> list:
    """아카이브 전체에서 검색에 필요한 필드만 뽑는다. 같은 link가 여러 날짜에
    걸쳐 있으면 나중(최신) 것이 이긴다 — dict로 모아 자연스럽게 중복이 제거된다."""
    rows = {}
    if not archive_dir.exists():
        return []
    for f in sorted(archive_dir.glob("*.json")):
        if f.name.endswith(".sent.json"):  # 발송 완료 마커는 기사 원본이 아니다
            continue
        try:
            day = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        date = day.get("date", f.stem)
        for a in day.get("articles", []):
            link = (a.get("link") or "").strip()
            title = (a.get("title") or "").strip()
            if not link or not title:
                continue
            rows[link] = {
                "link": link,
                "date": date,
                "title": title,
                "source": a.get("source") or "",
                "summary_ko": a.get("summary_ko") or "",
                "summary_en": a.get("summary_en") or "",
            }
    return list(rows.values())


def upsert(url: str, key: str, rows: list, batch_size: int) -> int:
    """search_articles에 배치로 upsert한다. link 충돌 시 덮어쓴다(요약 문구가
    나중에 다듬어질 수 있으므로 최신 내용이 이기는 게 맞다)."""
    endpoint = f"{url.rstrip('/')}/rest/v1/search_articles?on_conflict=link"
    sent = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(batch, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as res:
                if res.status >= 300:
                    raise SystemExit(f"[ERROR] 검색 인덱스 동기화 실패: HTTP {res.status}")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            # 테이블이 아직 없는 상태(supabase/schema.sql 미실행)는 설정이 덜 끝난
            # 것이지 고장이 아니다. 여기서 실패로 끝내면 스키마를 적용하기 전까지
            # 매일 아침 실패 알림이 울린다 — 검색은 부가 기능이고 이 경우 사이트는
            # 정적 인덱스로 폴백해 정상 동작하므로, 경고만 남기고 통과시킨다.
            # 그 외 오류(인증·제약 위반·네트워크)는 그대로 실패로 올린다.
            if "PGRST205" in body or (e.code == 404 and "search_articles" in body):
                raise TableMissing(body[:200])
            # 본문에 테이블·컬럼명이 담기지만 이건 서버 로그(무인 실행 보고)용이라
            # 그대로 노출해도 된다 — 사용자 브라우저로 나가는 경로가 아니다.
            raise SystemExit(f"[ERROR] 검색 인덱스 동기화 실패: HTTP {e.code} {body[:300]}")
        except urllib.error.URLError as e:
            raise SystemExit(f"[ERROR] 검색 인덱스 동기화 실패: {e.reason}")
        sent += len(batch)
    return sent


def main(argv=None):
    args = parse_args(argv)
    rows = collect_rows(Path(args.docs_dir) / "archive")

    if args.dry_run:
        print(f"[dry-run] 동기화 대상 {len(rows)}건")
        return

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        # 검색은 부가 기능이라 여기서 파이프라인 전체를 죽이지는 않는다. 다만 조용히
        # 넘어가면 검색이 며칠씩 멈춘 걸 아무도 모르므로 실패로 끝내되, 호출하는 쪽
        # (SKILL.md 6단계)에서 사이트 배포는 이미 끝난 뒤에 실행하도록 순서를 잡았다.
        raise SystemExit("[ERROR] SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 환경변수가 없습니다.")

    if not rows:
        print("동기화할 기사가 없습니다.")
        return

    try:
        sent = upsert(url, key, rows, args.batch_size)
    except TableMissing:
        print(
            "[WARN] search_articles 테이블이 없어 검색 인덱스 동기화를 건너뛰었습니다.\n"
            "       Supabase SQL Editor에서 supabase/schema.sql을 한 번 실행하세요.\n"
            "       그때까지 사이트 검색은 정적 인덱스(최근 30일)로 폴백해 계속 동작합니다.",
            file=sys.stderr,
        )
        return
    print(f"검색 인덱스 동기화 완료: {sent}건")


if __name__ == "__main__":
    main()
