"""확인을 끝내 하지 않은 구독 신청을 일정 기간 뒤에 지운다.

왜 필요한가
-----------
더블 옵트인이라 ``confirmed_at``이 비어 있는 행에는 브리핑이 나가지 않는다
(``send_broadcast.py``가 ``confirmed_at=not.is.null``로 거른다). 그런데 그 행은
지워지지 않고 영원히 남는다. 남겨두면 두 가지가 나빠진다.

1. 쓰지도 않을 이메일 주소를 무기한 보관하게 된다. 개인정보 최소보관 원칙과 어긋나고,
   유출 시 피해 범위만 넓힌다.
2. 구독자 수 지표가 부풀려진다. 마케팅 카피가 이 숫자를 인용하는데, "구독 N명"에
   한 번도 확정하지 않은 사람이 섞여 있으면 그 숫자로 판단을 내릴 수 없다.

왜 하필 90일인가
----------------
확인 링크 유효기간이 7일이므로 그 뒤로는 스스로 확정할 방법이 사실상 없다(만료
페이지에서 재발송을 받을 수는 있지만 그러려면 원래 메일을 다시 찾아야 한다). 그래도
넉넉히 두는 이유는 되돌릴 수 없는 삭제이기 때문이다 — 지운 뒤 그 사람이 다시
신청하면 처음부터 시작될 뿐이라 피해는 없지만, 서두를 이유도 없다.

무인 운영 원칙
--------------
이 스크립트가 실패해도 발송 파이프라인은 계속돼야 한다. 실패는 0이 아닌 종료 코드가
아니라 경고 메시지로 알리고, 호출부(SKILL.md)는 결과를 무시하고 다음 단계로 간다.
정말 문제가 있으면 며칠 연속으로 완료 보고에 남아 눈에 띈다.

사용법::

    py scripts/prune_unconfirmed.py                # 삭제 대상만 보여준다 (기본)
    py scripts/prune_unconfirmed.py --apply        # 실제로 지운다
    py scripts/prune_unconfirmed.py --days 30 --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

DEFAULT_DAYS = 90
# 무인 실행에서 응답이 없으면 여기서 멈춘다. 예전에 timeout 없는 urlopen 때문에
# 발송이 멈춘 적이 있어, 이 저장소의 모든 네트워크 호출은 timeout을 명시한다.
TIMEOUT_SEC = 15
USER_AGENT = "ai-news-briefing/prune-unconfirmed"


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"[WARN] {name}이(가) 없어 정리를 건너뜁니다.", file=sys.stderr)
        raise SystemExit(0)
    return value


def _request(url: str, key: str, method: str, prefer: str | None = None):
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "User-Agent": USER_AGENT,
    }
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(url, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as res:
        body = res.read().decode("utf-8")
    return json.loads(body) if body.strip() else []


def build_filter(days: int, now: datetime | None = None) -> str:
    """삭제 대상을 고르는 PostgREST 질의 문자열.

    조건 셋을 모두 만족해야 한다 — 하나라도 빠지면 지우면 안 될 행이 걸린다.
    특히 ``unsubscribed_at``까지 보는 이유는, 해지한 사람의 기록을 지우면 그 주소가
    "한 번도 없던 주소"로 돌아가 나중에 다시 담길 수 있기 때문이다.
    """
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    return urllib.parse.urlencode(
        {
            "confirmed_at": "is.null",
            "unsubscribed_at": "is.null",
            "created_at": f"lt.{cutoff.isoformat()}",
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="실제로 삭제한다. 기본은 대상만 출력한다 — 되돌릴 수 없는 작업이라 "
        "실행이 기본값이면 안 된다.",
    )
    args = parser.parse_args()

    if args.days < 7:
        print("[WARN] --days가 7 미만입니다. 확인 링크 유효기간(7일)보다 짧으면 "
              "아직 확정할 수 있는 사람을 지웁니다.", file=sys.stderr)
        return 1

    url = _env("SUPABASE_URL").rstrip("/")
    key = _env("SUPABASE_SERVICE_ROLE_KEY")
    query = build_filter(args.days)
    base = f"{url}/rest/v1/subscribers?{query}"

    try:
        targets = _request(f"{base}&select=email,created_at", key, "GET")
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
        # 부가 기능의 실패가 파이프라인을 멈추면 안 된다. 완료 보고에 남도록 경고만 낸다.
        print(f"[WARN] 미확정 구독 조회 실패 — 정리를 건너뜁니다: {e}", file=sys.stderr)
        return 0

    if not targets:
        print(f"미확정 {args.days}일 초과: 없음")
        return 0

    print(f"미확정 {args.days}일 초과: {len(targets)}건")
    for row in targets:
        print(f"  {row.get('email')}  (가입 {row.get('created_at')})")

    if not args.apply:
        print("\n--apply 를 붙이면 실제로 삭제합니다.")
        return 0

    try:
        _request(base, key, "DELETE", prefer="return=minimal")
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
        print(f"[WARN] 미확정 구독 삭제 실패: {e}", file=sys.stderr)
        return 0

    print(f"{len(targets)}건 삭제했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
