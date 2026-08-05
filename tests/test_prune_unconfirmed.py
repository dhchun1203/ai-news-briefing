"""prune_unconfirmed의 삭제 대상 선정 규칙.

이 스크립트는 PostgREST에 DELETE를 보낸다. **필터가 비면 테이블 전체가 지워진다.**
그래서 검증할 것은 "무엇을 지우는가"가 아니라 "조건이 하나라도 빠지지 않았는가"다.
"""

import sys
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from prune_unconfirmed import build_filter  # noqa: E402


class TestPruneFilter(unittest.TestCase):
    def parsed(self, days=90, now=None):
        return dict(urllib.parse.parse_qsl(build_filter(days, now=now)))

    def test_never_empty(self):
        """필터가 비면 DELETE가 테이블 전체를 지운다."""
        self.assertTrue(build_filter(90).strip())

    def test_requires_all_three_conditions(self):
        q = self.parsed()
        # 셋 중 하나라도 빠지면 지우면 안 될 사람이 걸린다:
        #   confirmed_at    없으면 -> 확정한 구독자가 지워진다
        #   unsubscribed_at 없으면 -> 해지 기록이 사라져 그 주소가 다시 담길 수 있다
        #   created_at      없으면 -> 방금 가입한 사람이 지워진다
        self.assertEqual(q.get("confirmed_at"), "is.null")
        self.assertEqual(q.get("unsubscribed_at"), "is.null")
        self.assertTrue(q.get("created_at", "").startswith("lt."))

    def test_cutoff_is_in_the_past_by_requested_days(self):
        now = datetime(2026, 8, 5, 0, 0, tzinfo=timezone.utc)
        cutoff = datetime.fromisoformat(self.parsed(days=90, now=now)["created_at"][3:])
        self.assertEqual(cutoff, now - timedelta(days=90))

    def test_cutoff_never_reaches_into_the_future(self):
        """미래 컷오프는 전 구독자가 대상이 된다는 뜻이다."""
        now = datetime(2026, 8, 5, 0, 0, tzinfo=timezone.utc)
        for days in (7, 30, 90, 365):
            cutoff = datetime.fromisoformat(self.parsed(days=days, now=now)["created_at"][3:])
            self.assertLess(cutoff, now, f"days={days}")


if __name__ == "__main__":
    unittest.main()
