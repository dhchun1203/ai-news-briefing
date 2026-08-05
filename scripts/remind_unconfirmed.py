"""확인을 마치지 않은 구독 신청자에게 리마인더를 **사람당 정확히 한 번** 보낸다.

왜 필요한가
-----------
더블 옵트인이라 ``confirmed_at``이 비어 있으면 브리핑이 나가지 않는다. 구독 폼까지
채운 사람이 확인 메일 한 통을 놓쳐서 영영 못 받게 되는 건 아깝다.

왜 "한 번"이 어려운가
---------------------
"미확정"이라는 조건은 그 사람이 확정하기 전까지 **매일 참**이다. 그래서 조건만 보고
보내면 같은 사람에게 매일 메일이 나간다. 그건 스팸 신고를 부르고, 발신 도메인 평판을
깎고, 결국 이미 확정한 구독자에게 가는 브리핑까지 스팸함으로 보낸다 — 더블 옵트인을
유지하는 이유를 스스로 무너뜨리는 셈이다.

그래서 ``reminded_at`` 컬럼을 표시로 쓰고, **발송 전에 선점**한다.

    UPDATE subscribers SET reminded_at = now()
     WHERE email = ? AND reminded_at IS NULL AND confirmed_at IS NULL AND unsubscribed_at IS NULL

이 UPDATE가 행을 돌려줬을 때만 메일을 보낸다. Postgres에서 같은 행에 동시 UPDATE가
들어오면 뒤엣것은 잠금이 풀린 뒤 조건을 다시 평가하므로, 두 프로세스가 같은 사람을
동시에 선점할 수 없다. 실행이 겹쳐도, 중간에 죽어도, 다시 돌려도 **두 번은 안 나간다.**

반대 방향은 열어둔다: 선점한 뒤 발송이 실패하면 그 사람은 리마인더를 못 받고 끝난다.
두 번 보내는 것보다 한 번도 안 보내는 쪽이 낫다는 판단이다. 손실을 줄이려고 한 명씩
선점→발송하고, 발송이 한 번 실패하면 그 자리에서 멈춘다(Resend가 죽어 있으면 남은
사람까지 선점만 하고 다 날릴 이유가 없다).

사용법::

    py scripts/remind_unconfirmed.py             # 대상만 보여준다 (기본, 아무것도 안 바꾼다)
    py scripts/remind_unconfirmed.py --apply     # 실제로 선점하고 보낸다
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

# 가입 후 이만큼 지나도 확인이 없으면 리마인더 대상. 너무 짧으면 "지금 메일함 보고
# 있는데 재촉당하는" 꼴이고, 너무 길면 그 사이 관심이 식는다.
DEFAULT_AFTER_DAYS = 2

# 한 번 실행에서 보낼 최대 인원. 버그나 데이터 이상으로 대상이 폭증했을 때 피해를
# 한 번에 다 내지 않기 위한 안전핀이다. 잘리면 조용히 넘어가지 않고 반드시 출력한다.
MAX_PER_RUN = 50

# api/_lib/tokens.js의 CONFIRM_TTL_SECONDS와 **같아야 한다**. 여기서 만든 링크를
# 검증하는 건 Node 쪽이라, 어긋나면 리마인더의 링크만 조용히 일찍 죽는다.
# tests/hmac_parity.test.js가 두 값과 서명 방식을 함께 검사한다.
CONFIRM_TTL_SECONDS = 60 * 60 * 24 * 7

TIMEOUT_SEC = 15
USER_AGENT = "ai-news-briefing/remind-unconfirmed"

REQUIRED_ENV = (
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "RESEND_API_KEY",
    "RESEND_SENDER_EMAIL",
    "SUBSCRIBE_TOKEN_SECRET",
    "SITE_URL",
)


def sign(secret: str, payload: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


LANGS = ("ko", "en")


def normalize_lang(value) -> str:
    lang = str(value or "").strip().lower()
    return lang if lang in LANGS else "ko"


def confirm_url(site_url: str, secret: str, email: str, now: float | None = None, lang: str = "ko") -> str:
    """확인 링크. lang을 실어 보내야 클릭 후 뜨는 결과 페이지가 같은 언어로 나온다."""
    expiry = int(now if now is not None else time.time()) + CONFIRM_TTL_SECONDS
    token = sign(secret, f"confirm|{email}|{expiry}")
    return (
        f"{site_url.rstrip('/')}/api/confirm"
        f"?email={urllib.parse.quote(email)}&expiry={expiry}&token={token}"
        f"&lang={normalize_lang(lang)}"
    )


def build_candidate_query(after_days: int, now: datetime | None = None, limit: int = MAX_PER_RUN) -> str:
    """리마인더 후보를 고르는 질의.

    네 조건이 **모두** 있어야 한다. 하나라도 빠지면 보내면 안 될 사람에게 나간다:
      reminded_at     없으면 -> 이미 받은 사람에게 또 간다 (이 스크립트의 존재 이유가 무너진다)
      confirmed_at    없으면 -> 이미 확정한 구독자에게 "확인하세요" 메일이 간다
      unsubscribed_at 없으면 -> 해지한 사람에게 다시 메일이 간다
      created_at      없으면 -> 방금 가입해 확인 메일을 받은 사람에게 곧바로 또 간다
    """
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=after_days)
    return urllib.parse.urlencode(
        {
            "reminded_at": "is.null",
            "confirmed_at": "is.null",
            "unsubscribed_at": "is.null",
            "created_at": f"lt.{cutoff.isoformat()}",
            "select": "email,created_at,lang",
            "order": "created_at.asc",
            "limit": str(limit),
        }
    )


def build_claim_query(email: str) -> str:
    """한 사람을 선점하는 질의.

    후보 조회 때 이미 걸렀더라도 여기서 조건을 **다시** 건다. 조회와 선점 사이에
    그 사람이 확인했거나 해지했을 수 있고, 다른 실행이 먼저 선점했을 수도 있다.
    """
    return urllib.parse.urlencode(
        {
            "email": f"eq.{email}",
            "reminded_at": "is.null",
            "confirmed_at": "is.null",
            "unsubscribed_at": "is.null",
        }
    )


def _request(url: str, key: str, method: str, payload=None, prefer: str | None = None):
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "User-Agent": USER_AGENT,
    }
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(url, headers=headers, method=method, data=data)
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as res:
        body = res.read().decode("utf-8")
    return json.loads(body) if body.strip() else []


REMINDER_COPY = {
    "ko": {
        "subject": "[AI 뉴스 브리핑] 구독 확인이 아직 남아 있어요",
        "hello": "안녕하세요. AI 뉴스 브리핑입니다.",
        "body": "구독 신청은 해주셨는데 확인 절차가 아직 남아 있어서 브리핑을 보내드리지 "
                "못하고 있어요. 아래 링크를 눌러주시면 다음 날 아침부터 받아보실 수 "
                "있습니다 (7일 이내 유효).",
        "cta": "구독 확인하기",
        "note": "이 안내는 한 번만 보내드립니다. 확인하지 않으시면 더 이상 메일을 보내지 "
                "않으니 그냥 두셔도 괜찮아요. 본인이 신청하지 않았다면 무시하셔도 됩니다.",
    },
    "en": {
        "subject": "[AI News Briefing] Your subscription still needs confirming",
        "hello": "Hello from the AI News Briefing.",
        "body": "You signed up, but the confirmation step is still outstanding, so we haven't "
                "been able to send you anything. Press the link below and you'll start "
                "receiving it from the next issue. The link is valid for 7 days.",
        "cta": "Confirm subscription",
        "note": "This is the only reminder we'll send. If you don't confirm, we won't email "
                "you again — you can simply ignore this. If you didn't sign up, ignore it too.",
    },
}


def reminder_html(confirm_link: str, lang: str = "ko") -> str:
    c = REMINDER_COPY[normalize_lang(lang)]
    return f"""
      <p>{c["hello"]}</p>
      <p>{c["body"]}</p>
      <p><a href="{confirm_link}">{c["cta"]}</a></p>
      <p style="color:#888;font-size:12px;">{c["note"]}</p>
    """


def send_reminder(email: str, site_url: str, secret: str, sender: str, api_key: str,
                  lang: str = "ko") -> bool:
    lang = normalize_lang(lang)
    payload = {
        "from": sender,
        # 수신자는 언제나 이 한 주소뿐이다. 배열이나 bcc를 쓰지 않는다 — 리마인더가
        # 여러 명에게 나갈 수 있는 형태가 되면 사고가 조용히 커진다.
        "to": email,
        "subject": REMINDER_COPY[lang]["subject"],
        "html": reminder_html(confirm_url(site_url, secret, email, lang=lang), lang),
    }
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=TIMEOUT_SEC).read()
        return True
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
        print(f"[WARN] 리마인더 발송 실패({email}): {e}", file=sys.stderr)
        return False


def remind_all(candidates, claim, send, log=print) -> dict:
    """선점 → 발송 순서를 강제하는 조율부.

    ``claim(email)``은 선점에 성공하면 True를 돌려준다. **False면 절대 보내지 않는다** —
    이미 보냈거나, 그 사이 확정/해지했다는 뜻이다.
    """
    sent, skipped = [], []
    for row in candidates:
        email = row["email"]
        lang = normalize_lang(row.get("lang"))
        if not claim(email):
            # 조회와 선점 사이에 상태가 바뀌었다. 보내지 않는 게 정답이다.
            skipped.append(email)
            log(f"  건너뜀(이미 처리됨): {email}")
            continue
        if not send(email, lang):
            # 선점은 이미 됐으므로 이 사람은 리마인더를 못 받고 끝난다. 되돌리지
            # 않는다 — 되돌리면 다음 실행에서 다시 시도하다가 "발송은 됐는데 응답만
            # 실패한" 경우에 두 번 보내게 된다.
            log(f"  발송 실패 — 여기서 중단합니다: {email}")
            return {"sent": sent, "skipped": skipped, "aborted": True}
        sent.append(email)
        log(f"  발송: {email}")
    return {"sent": sent, "skipped": skipped, "aborted": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--after-days", type=int, default=DEFAULT_AFTER_DAYS)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="실제로 선점하고 발송한다. 기본은 대상만 출력한다.",
    )
    args = parser.parse_args()

    if args.after_days < 1:
        print("[WARN] --after-days는 1 이상이어야 합니다. 가입 직후 확인 메일을 받은 "
              "사람에게 곧바로 리마인더가 갑니다.", file=sys.stderr)
        return 1

    missing = [name for name in REQUIRED_ENV if not os.environ.get(name, "").strip()]
    if missing:
        print(f"[WARN] 환경변수 누락({', '.join(missing)}) — 리마인더를 건너뜁니다.", file=sys.stderr)
        return 0

    url = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    site_url = os.environ["SITE_URL"]
    secret = os.environ["SUBSCRIBE_TOKEN_SECRET"]
    sender = os.environ["RESEND_SENDER_EMAIL"]
    api_key = os.environ["RESEND_API_KEY"]

    try:
        rows = _request(
            f"{url}/rest/v1/subscribers?{build_candidate_query(args.after_days)}", key, "GET"
        )
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
        # 부가 기능의 실패가 파이프라인을 멈추면 안 된다.
        print(f"[WARN] 리마인더 대상 조회 실패 — 건너뜁니다: {e}", file=sys.stderr)
        return 0

    if not rows:
        print(f"리마인더 대상(미확정 {args.after_days}일 초과, 미발송): 없음")
        return 0

    print(f"리마인더 대상: {len(rows)}건")
    for row in rows:
        print(f"  {row['email']}  (가입 {row['created_at']})")
    if len(rows) >= MAX_PER_RUN:
        # 잘린 걸 조용히 넘어가면 "전부 처리했다"로 읽힌다.
        print(f"[주의] 한 번에 최대 {MAX_PER_RUN}명까지만 처리합니다. 남은 대상은 다음 실행에서.")

    if not args.apply:
        print("\n--apply 를 붙이면 실제로 발송합니다.")
        return 0

    def claim(email: str) -> bool:
        try:
            claimed = _request(
                f"{url}/rest/v1/subscribers?{build_claim_query(email)}",
                key,
                "PATCH",
                payload={"reminded_at": datetime.now(timezone.utc).isoformat()},
                prefer="return=representation",
            )
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
            print(f"[WARN] 선점 실패({email}): {e}", file=sys.stderr)
            return False
        # 조건에 맞는 행이 없었으면 빈 배열이 온다 = 이미 누군가 선점했거나 상태가 바뀌었다.
        return bool(claimed)

    result = remind_all(
        rows,
        claim,
        lambda email, lang: send_reminder(email, site_url, secret, sender, api_key, lang),
    )
    print(f"\n발송 {len(result['sent'])}건, 건너뜀 {len(result['skipped'])}건"
          + (" (발송 실패로 중단)" if result["aborted"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
