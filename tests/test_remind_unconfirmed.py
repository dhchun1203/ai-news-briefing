"""리마인더가 사람당 정확히 한 번만 나가는지.

이 스크립트에서 틀리면 안 되는 건 하나다 — **같은 사람에게 두 번 보내지 않는 것.**
"미확정"이라는 조건은 그 사람이 확정하기 전까지 매일 참이라, 표시(reminded_at)와
선점 순서가 어긋나는 순간 곧바로 매일 발송이 된다.
"""

import sys
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from remind_unconfirmed import (  # noqa: E402
    MAX_PER_RUN,
    REMINDER_COPY,
    normalize_lang,
    reminder_html,
    build_candidate_query,
    build_claim_query,
    confirm_url,
    remind_all,
)


class FakeDb:
    """subscribers 테이블 흉내. claim은 조건에 맞을 때만 성공한다."""

    def __init__(self, rows):
        self.rows = {r["email"]: dict(r) for r in rows}
        self.claim_calls = []
        self.sent = []
        self.sent_langs = []
        self.send_fails_for = set()

    def claim(self, email):
        self.claim_calls.append(email)
        row = self.rows.get(email)
        if not row:
            return False
        if row.get("reminded_at") or row.get("confirmed_at") or row.get("unsubscribed_at"):
            return False
        row["reminded_at"] = "now"
        return True

    def send(self, email, lang="ko"):
        if email in self.send_fails_for:
            return False
        self.sent.append(email)
        self.sent_langs.append(lang)
        return True

    def candidates(self):
        """실제 질의가 고르는 것과 같은 조건으로 후보를 뽑는다."""
        return [
            {"email": e, "created_at": "x", "lang": r.get("lang", "ko")}
            for e, r in sorted(self.rows.items())
            if not r.get("reminded_at") and not r.get("confirmed_at") and not r.get("unsubscribed_at")
        ]


def pending(email, **over):
    return {
        "email": email,
        "reminded_at": None,
        "confirmed_at": None,
        "unsubscribed_at": None,
        "lang": "ko",
        **over,
    }


class TestExactlyOnce(unittest.TestCase):
    def test_sends_once_on_first_run(self):
        db = FakeDb([pending("a@x.com"), pending("b@x.com")])
        result = remind_all(db.candidates(), db.claim, db.send, log=lambda *_: None)
        self.assertEqual(db.sent, ["a@x.com", "b@x.com"])
        self.assertEqual(result["sent"], ["a@x.com", "b@x.com"])

    def test_second_run_sends_nothing(self):
        """가장 중요한 성질 — 매일 도는 스크립트라 이게 깨지면 매일 발송이 된다."""
        db = FakeDb([pending("a@x.com"), pending("b@x.com")])
        remind_all(db.candidates(), db.claim, db.send, log=lambda *_: None)
        remind_all(db.candidates(), db.claim, db.send, log=lambda *_: None)
        self.assertEqual(db.sent, ["a@x.com", "b@x.com"])

    def test_ten_runs_still_once(self):
        db = FakeDb([pending("a@x.com")])
        for _ in range(10):
            remind_all(db.candidates(), db.claim, db.send, log=lambda *_: None)
        self.assertEqual(db.sent, ["a@x.com"])

    def test_never_sends_when_claim_fails(self):
        """선점 실패는 '이미 처리됨'이라는 뜻이다. 여기서 보내면 중복이 된다."""
        db = FakeDb([pending("a@x.com")])
        stale = [{"email": "a@x.com", "created_at": "x"}]
        db.rows["a@x.com"]["reminded_at"] = "already"  # 조회 후 다른 실행이 선점한 상황
        remind_all(stale, db.claim, db.send, log=lambda *_: None)
        self.assertEqual(db.sent, [])

    def test_claim_happens_before_send(self):
        """발송 후 표시하면 그 사이 크래시가 중복 발송을 만든다."""
        order = []
        rows = [{"email": "a@x.com", "created_at": "x"}]

        def claim(email):
            order.append("claim")
            return True

        def send(email, lang="ko"):
            order.append("send")
            return True

        remind_all(rows, claim, send, log=lambda *_: None)
        self.assertEqual(order, ["claim", "send"])

    def test_send_failure_does_not_release_the_claim(self):
        """되돌리면 '발송은 됐는데 응답만 실패한' 경우에 두 번 보내게 된다."""
        db = FakeDb([pending("a@x.com"), pending("b@x.com")])
        db.send_fails_for = {"a@x.com"}
        remind_all(db.candidates(), db.claim, db.send, log=lambda *_: None)
        self.assertTrue(db.rows["a@x.com"]["reminded_at"])
        # 다시 돌려도 재시도하지 않는다 (한 번도 못 받는 쪽을 택한다)
        db.send_fails_for = set()
        remind_all(db.candidates(), db.claim, db.send, log=lambda *_: None)
        self.assertNotIn("a@x.com", db.sent)

    def test_aborts_on_send_failure(self):
        """Resend가 죽어 있으면 남은 사람까지 선점만 하고 날릴 이유가 없다."""
        db = FakeDb([pending("a@x.com"), pending("b@x.com"), pending("c@x.com")])
        db.send_fails_for = {"a@x.com"}
        result = remind_all(db.candidates(), db.claim, db.send, log=lambda *_: None)
        self.assertTrue(result["aborted"])
        self.assertIsNone(db.rows["b@x.com"]["reminded_at"])
        self.assertIsNone(db.rows["c@x.com"]["reminded_at"])


class TestLanguage(unittest.TestCase):
    """/en/ 에서 구독한 사람에게 한국어 리마인더가 가면 안 된다."""

    def test_sends_in_subscriber_language(self):
        db = FakeDb([pending("ko@x.com"), pending("en@x.com", lang="en")])
        remind_all(db.candidates(), db.claim, db.send, log=lambda *_: None)
        self.assertEqual(dict(zip(db.sent, db.sent_langs)), {"ko@x.com": "ko", "en@x.com": "en"})

    def test_unknown_lang_falls_back_to_korean(self):
        db = FakeDb([pending("x@x.com", lang="fr")])
        remind_all(db.candidates(), db.claim, db.send, log=lambda *_: None)
        self.assertEqual(db.sent_langs, ["ko"])
        self.assertEqual(normalize_lang(None), "ko")

    def test_english_reminder_has_no_korean(self):
        """영어 본문에 한글이 한 글자라도 있으면 분기를 빠뜨린 것이다."""
        body = reminder_html("https://x.test/confirm", "en") + REMINDER_COPY["en"]["subject"]
        hangul = [ch for ch in body if "가" <= ch <= "힣"]
        self.assertEqual(hangul, [], f"영어 리마인더에 한글: {hangul}")

    def test_korean_reminder_is_korean(self):
        body = reminder_html("https://x.test/confirm", "ko")
        self.assertTrue(any("가" <= ch <= "힣" for ch in body))

    def test_confirm_link_carries_lang(self):
        from remind_unconfirmed import confirm_url

        self.assertIn("lang=en", confirm_url("https://x.test", "s", "a@x.com", lang="en"))
        self.assertIn("lang=ko", confirm_url("https://x.test", "s", "a@x.com", lang="ko"))

    def test_every_copy_key_exists_in_both_languages(self):
        self.assertEqual(set(REMINDER_COPY["ko"]), set(REMINDER_COPY["en"]))
        for lang, copy in REMINDER_COPY.items():
            for key, value in copy.items():
                self.assertTrue(value.strip(), f"{lang}.{key} 비어 있음")


class TestTargetSelection(unittest.TestCase):
    def parsed(self, **kw):
        return dict(urllib.parse.parse_qsl(build_candidate_query(**kw)))

    def test_requires_all_four_conditions(self):
        q = self.parsed(after_days=2)
        self.assertEqual(q.get("reminded_at"), "is.null")
        self.assertEqual(q.get("confirmed_at"), "is.null")
        self.assertEqual(q.get("unsubscribed_at"), "is.null")
        self.assertTrue(q.get("created_at", "").startswith("lt."))

    def test_capped_per_run(self):
        self.assertEqual(self.parsed(after_days=2)["limit"], str(MAX_PER_RUN))

    def test_cutoff_is_in_the_past(self):
        now = datetime(2026, 8, 5, tzinfo=timezone.utc)
        cutoff = datetime.fromisoformat(self.parsed(after_days=2, now=now)["created_at"][3:])
        self.assertEqual(cutoff, now - timedelta(days=2))

    def test_claim_query_rechecks_every_condition(self):
        """조회와 선점 사이에 상태가 바뀔 수 있다. 선점이 마지막 방어선이다."""
        q = dict(urllib.parse.parse_qsl(build_claim_query("a@x.com")))
        self.assertEqual(q.get("email"), "eq.a@x.com")
        self.assertEqual(q.get("reminded_at"), "is.null")
        self.assertEqual(q.get("confirmed_at"), "is.null")
        self.assertEqual(q.get("unsubscribed_at"), "is.null")


class TestConfirmLink(unittest.TestCase):
    def test_link_carries_signed_token_and_expiry(self):
        url = confirm_url("https://x.test/", "s3cret", "a@x.com", now=1_000_000)
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        self.assertEqual(q["email"], "a@x.com")
        self.assertEqual(int(q["expiry"]), 1_000_000 + 60 * 60 * 24 * 7)
        self.assertTrue(q["token"])

    def test_no_double_slash(self):
        self.assertIn("https://x.test/api/confirm", confirm_url("https://x.test/", "s", "a@x.com"))


if __name__ == "__main__":
    unittest.main()
