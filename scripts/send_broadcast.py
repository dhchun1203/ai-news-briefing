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
import urllib.error
import urllib.request
from pathlib import Path

RESEND_API = "https://api.resend.com"
BATCH_SIZE = 100
# Resend/Supabase 모두 Cloudflare 뒤에 있어, urllib 기본 User-Agent(Python-urllib/x.x)로
# 요청하면 봇으로 간주돼 403(Cloudflare error 1010)으로 차단된다. 일반적인 UA를 지정해 우회한다.
USER_AGENT = "ai-news-briefing-bot/1.0 (+https://www.dailyaithread.com)"


def parse_args():
    p = argparse.ArgumentParser(description="구독자에게 오늘의 다이제스트를 이메일로 발송한다.")
    p.add_argument("--input", required=True, help="data/digest_<날짜>.json 경로")
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
        with urllib.request.urlopen(req) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"[ERROR] Supabase 구독자 조회 실패: {e.code} {e.read().decode('utf-8')}", file=sys.stderr)
        sys.exit(1)
    return [row["email"] for row in rows if row.get("email")]


def build_html(digest: dict, site_url: str, unsub_url: str) -> str:
    date = digest["date"]
    articles = digest["articles"]
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
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"[ERROR] Resend 배치 발송 실패: {e.code} {e.read().decode('utf-8')}", file=sys.stderr)
        sys.exit(1)


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
    subscribers = fetch_confirmed_subscribers(env["SUPABASE_URL"], env["SUPABASE_SERVICE_ROLE_KEY"])

    if not subscribers:
        print("발송 대상 구독자가 없습니다.")
        return

    subject = f"AI 뉴스 브리핑 — {digest['date']} (기사 {len(digest['articles'])}건)"
    html_by_email = {
        email: build_html(digest, site_url, unsubscribe_url(site_url, env["SUBSCRIBE_TOKEN_SECRET"], email))
        for email in subscribers
    }

    sent_total = 0
    for i in range(0, len(subscribers), BATCH_SIZE):
        chunk = subscribers[i : i + BATCH_SIZE]
        send_batch(env["RESEND_API_KEY"], chunk, subject, html_by_email)
        sent_total += len(chunk)

    print(f"발송 완료: 구독자 {sent_total}명")


if __name__ == "__main__":
    main()
