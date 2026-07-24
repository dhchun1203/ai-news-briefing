#!/usr/bin/env python3
"""오늘의 digest를 확인된(confirmed) 이메일 구독자 전원에게 헤드라인+링크 요약으로 발송한다.

구독자 목록의 진실 소스는 Supabase(subscribers 테이블)이고, Resend는 발송만 담당한다.
확인/구독취소 링크 서명 방식은 api/_lib/tokens.js와 동일한 HMAC-SHA256 + base64url이라
두 구현이 같은 SUBSCRIBE_TOKEN_SECRET을 공유해야 한다.
"""
import argparse
import base64
import hashlib
import hmac
import html
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DOCS_DIR = ROOT / "docs"

RESEND_API = "https://api.resend.com"
BATCH_SIZE = 100
# Resend/Supabase 모두 Cloudflare 뒤에 있어, urllib 기본 User-Agent(Python-urllib/x.x)로
# 요청하면 봇으로 간주돼 403(Cloudflare error 1010)으로 차단된다. 일반적인 UA를 지정해 우회한다.
USER_AGENT = "ai-news-briefing-bot/1.0 (+https://www.dailyaithread.com)"
# 일시적 네트워크 문제(타임아웃, 5xx)에 한해 재시도한다. 인증 오류 등 재시도해도 안 되는
# 4xx는 즉시 실패 처리한다 — 설정 문제(예: allowlist 미등록)를 재시도로 감추지 않기 위해서다.
RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY_SEC = 3


def parse_args():
    p = argparse.ArgumentParser(description="구독자에게 오늘의 다이제스트를 이메일로 발송한다.")
    p.add_argument("--input", required=True, help="data/digest_<날짜>.json 또는 docs/archive/<날짜>.json 경로")
    p.add_argument(
        "--weekly-input",
        default=None,
        help="(일요일에만) data/weekly_<주차>.json 경로 — 있으면 이메일 상단에 주간 회고 티저를 추가한다",
    )
    p.add_argument("--docs-dir", default=str(DEFAULT_DOCS_DIR), help="발송 완료 마커를 기록할 docs/ 디렉토리")
    p.add_argument(
        "--catchup",
        action="store_true",
        help="발송 오류로 놓친 과거 날짜를 뒤늦게 보정 발송하는 경우 — 이메일 상단에 지연 안내 문구가 붙는다",
    )
    return p.parse_args()


def require_env(*names):
    values = {}
    missing = []
    for name in names:
        value = os.environ.get(name)
        if not value:
            missing.append(name)
        values[name] = value
    if missing:
        print(f"[ERROR] 환경변수 누락: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)
    return values


def sign(secret: str, payload: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def unsubscribe_url(site_url: str, secret: str, email: str) -> str:
    token = sign(secret, f"unsubscribe|{email}")
    from urllib.parse import quote

    return f"{site_url}/api/unsubscribe?email={quote(email)}&token={token}"


def urlopen_with_retry(req: urllib.request.Request) -> bytes:
    """일시적 오류(연결 실패, 5xx)에 한해 지수 백오프로 재시도한다. 같은 Request 객체를
    여러 번 재사용해도 안전하다(urlopen이 req를 변형하지 않음). 401/403/404 같은 4xx는
    재시도해도 결과가 바뀌지 않는 설정/권한 문제이므로 즉시 올린다."""
    last_error = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if not (500 <= e.code < 600) or attempt == RETRY_ATTEMPTS:
                raise
            last_error = e
        except urllib.error.URLError as e:
            if attempt == RETRY_ATTEMPTS:
                raise
            last_error = e
        time.sleep(RETRY_BASE_DELAY_SEC * attempt)
    raise last_error  # pragma: no cover — 루프가 항상 return/raise로 끝나 도달하지 않음


def fetch_confirmed_subscribers(supabase_url: str, service_role_key: str) -> list:
    url = (
        f"{supabase_url.rstrip('/')}/rest/v1/subscribers"
        "?select=email&confirmed_at=not.is.null&unsubscribed_at=is.null"
    )
    req = urllib.request.Request(
        url,
        headers={
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        rows = json.loads(urlopen_with_retry(req).decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"[ERROR] Supabase 구독자 조회 실패: {e.code} {e.read().decode('utf-8')}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"[ERROR] Supabase 접속 실패(네트워크/allowlist 문제로 추정): {e.reason}", file=sys.stderr)
        sys.exit(1)
    return [row["email"] for row in rows if row.get("email")]


def build_weekly_teaser_block(weekly: dict, site_url: str) -> str:
    """weekly_<주차>.json이 주어졌을 때(일요일 발송) 이메일 최상단에 넣을 주간 회고
    티저 블록을 만든다. headline이 비어있으면(그 주는 회고를 건너뛴 경우) 빈 문자열을
    반환해 아무것도 추가하지 않는다."""
    headline = (weekly or {}).get("headline_ko", "").strip()
    if not headline:
        return ""
    week_label = weekly.get("week_label", "")
    link = f"{site_url}/weekly/{week_label}.html"
    return (
        '<div style="margin:0 0 20px;padding:16px 18px;background:#f5f4f1;'
        'border-left:3px solid #121212;border-radius:0 4px 4px 0;">'
        '<p style="margin:0 0 6px;font-size:11px;font-weight:700;letter-spacing:0.1em;'
        'text-transform:uppercase;color:#121212;">이번 주 종합</p>'
        f'<p style="margin:0 0 10px;font-size:17px;font-weight:700;line-height:1.5;color:#121212;">'
        f'{html.escape(headline)}</p>'
        f'<a href="{link}" style="font-size:14px;font-weight:700;color:#a2201d;'
        'text-decoration:none;">주간 회고 전체 보기 →</a>'
        "</div>"
    )


def build_catchup_notice(date: str) -> str:
    """--catchup 발송(발송 오류로 놓친 과거 날짜를 뒤늦게 보정 발송)일 때만 이메일 최상단에
    붙는 투명성 안내 — 왜 평소와 다른 시간에, 혹은 두 통이 한꺼번에 왔는지 설명한다."""
    return (
        '<div style="margin:0 0 16px;padding:10px 14px;background:#fff8e6;'
        'border:1px solid #e8c766;border-radius:4px;font-size:13px;color:#6b5a1e;">'
        f"발송 오류로 {date}자 브리핑이 예정보다 늦게 도착했습니다. 불편을 드려 죄송합니다."
        "</div>"
    )


def build_html(digest: dict, site_url: str, unsub_url: str, weekly_block: str = "", catchup: bool = False) -> str:
    date = digest["date"]
    articles = digest["articles"]
    catchup_notice = build_catchup_notice(date) if catchup else ""
    rows = []
    for a in articles:
        title = html.escape(a["title"])
        summary = html.escape(a["summary_ko"])
        rows.append(
            '<tr><td style="padding:14px 0;border-bottom:1px solid #e2e2e2;">'
            f'<a href="{a["link"]}" style="font-size:16px;font-weight:700;color:#121212;'
            f'text-decoration:none;">{title}</a>'
            f'<p style="margin:8px 0 0;color:#444;font-size:14px;line-height:1.6;">{summary}</p>'
            "</td></tr>"
        )
    site_link = f"{site_url}/index.html"

    # 오늘의 인사이트 헤드라인(있는 날만)을 메일 상단에 넣어 열자마자 핵심을 잡게 한다.
    insight = digest.get("daily_insight") or {}
    insight_headline = insight.get("headline_ko", "").strip()
    insight_block = ""
    if insight_headline:
        insight_block = (
            '<div style="margin:16px 0 24px;padding:14px 18px;background:#f5f4f1;'
            'border-left:3px solid #a2201d;border-radius:0 4px 4px 0;">'
            '<p style="margin:0 0 4px;font-size:11px;font-weight:700;letter-spacing:0.1em;'
            'text-transform:uppercase;color:#a2201d;">오늘의 인사이트</p>'
            f'<p style="margin:0;font-size:16px;font-weight:700;line-height:1.5;color:#121212;">'
            f'{html.escape(insight_headline)}</p>'
            "</div>"
        )

    return f"""
    <div style="max-width:600px;margin:0 auto;font-family:-apple-system,Arial,sans-serif;">
      {catchup_notice}
      <h1 style="font-size:22px;margin-bottom:4px;">AI 뉴스 브리핑 — {date}</h1>
      <p style="margin:14px 0 22px;">
        <a href="{site_link}" style="display:inline-block;background-color:#a2201d;
        color:#ffffff;font-size:16px;font-weight:700;text-decoration:none;
        padding:13px 26px;border-radius:6px;">오늘의 전체 브리핑 보기 (요약 + 시사점) →</a>
      </p>
      <p style="color:#666;font-size:13px;margin:0 0 20px;">
        기사 {len(articles)}건의 헤드라인과 한 줄 요약입니다. 각 기사가 시사하는 점과 전체
        인사이트 분석은 위 링크에서 확인하세요.
      </p>
      {weekly_block}
      {insight_block}
      <table style="width:100%;border-collapse:collapse;">{''.join(rows)}</table>
      <p style="margin-top:32px;font-size:12px;color:#999;">
        더 이상 받고 싶지 않다면 <a href="{unsub_url}" style="color:#999;">구독취소</a>를 눌러주세요.
      </p>
    </div>
    """


def send_batch(api_key: str, emails: list, subject: str, html_by_email: dict):
    payload = [
        {"from": os.environ["RESEND_SENDER_EMAIL"], "to": [e], "subject": subject, "html": html_by_email[e]}
        for e in emails
    ]
    req = urllib.request.Request(
        f"{RESEND_API}/emails/batch",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        return json.loads(urlopen_with_retry(req).decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"[ERROR] Resend 배치 발송 실패: {e.code} {e.read().decode('utf-8')}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"[ERROR] Resend 접속 실패(네트워크/allowlist 문제로 추정): {e.reason}", file=sys.stderr)
        sys.exit(1)


def mark_sent(docs_dir: Path, date: str, recipient_count: int):
    """발송이 실제로 끝난(구독자 0명 포함) 날짜에만 docs/archive/<날짜>.sent.json을 남긴다.
    이 파일의 존재 여부가 "그날 발송이 실제로 완료됐는가"의 유일한 영속 기록이다 —
    SKILL.md가 다음 실행 때 이걸 보고 밀린 발송(catch-up)이 있는지 판단한다. 실패 시(즉
    sys.exit로 중간에 죽었을 때)는 이 함수까지 도달하지 않으므로 마커가 안 남고, 그게
    곧 "발송 안 됨" 신호가 된다."""
    archive_dir = docs_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": date,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "recipient_count": recipient_count,
    }
    (archive_dir / f"{date}.sent.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main():
    args = parse_args()
    env = require_env(
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "RESEND_API_KEY",
        "RESEND_SENDER_EMAIL",
        "SUBSCRIBE_TOKEN_SECRET",
        "SITE_URL",
    )
    site_url = env["SITE_URL"].rstrip("/")

    digest = json.loads(Path(args.input).read_text(encoding="utf-8"))
    docs_dir = Path(args.docs_dir)
    subscribers = fetch_confirmed_subscribers(env["SUPABASE_URL"], env["SUPABASE_SERVICE_ROLE_KEY"])

    if not subscribers:
        print("발송 대상 구독자가 없습니다.")
        mark_sent(docs_dir, digest["date"], 0)  # 대상이 없는 것도 "그날 처리는 끝남" 상태다
        return

    weekly_block = ""
    if args.weekly_input:
        weekly_path = Path(args.weekly_input)
        if weekly_path.exists():
            weekly = json.loads(weekly_path.read_text(encoding="utf-8"))
            weekly_block = build_weekly_teaser_block(weekly, site_url)

    subject = f"AI 뉴스 브리핑 — {digest['date']} (기사 {len(digest['articles'])}건)"
    if args.catchup:
        subject = f"[지연 발송] {subject}"
    html_by_email = {
        email: build_html(
            digest,
            site_url,
            unsubscribe_url(site_url, env["SUBSCRIBE_TOKEN_SECRET"], email),
            weekly_block=weekly_block,
            catchup=args.catchup,
        )
        for email in subscribers
    }

    sent_total = 0
    for i in range(0, len(subscribers), BATCH_SIZE):
        chunk = subscribers[i : i + BATCH_SIZE]
        send_batch(env["RESEND_API_KEY"], chunk, subject, html_by_email)
        sent_total += len(chunk)

    mark_sent(docs_dir, digest["date"], sent_total)
    print(f"발송 완료: 구독자 {sent_total}명")


if __name__ == "__main__":
    main()
