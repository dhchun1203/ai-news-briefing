#!/usr/bin/env python3
"""파이프라인의 순수 함수들에 대한 회귀 테스트.

이 저장소는 의존성을 최소로 유지한다(요청은 urllib, npm 패키지 없음). 그래서 pytest
대신 표준 라이브러리 unittest를 쓴다 — 새 의존성 없이 `python -m unittest`로 돌아간다.

여기 담긴 것들은 전부 "조용히 틀려도 아무도 모르는" 종류라 테스트 가치가 높다:
- 같은 사건 클러스터링: 문턱값을 두 번 잘못 잡았던 이력이 있다(PLAN.md §12).
- KST 날짜 계산: 틀리면 주간 회고가 매주 건너뛰어진다(실제로 그랬다).
- 메일 HTML 이스케이프: 뚫려도 발송 자체는 성공해서 티가 안 난다.
"""
import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import send_broadcast  # noqa: E402
from fetch_articles import (  # noqa: E402
    STALE_FEED_THRESHOLD_DAYS,
    build_same_story_clusters,
    extract_keywords,
    parse_args,
)
from kst_date import kst_date_facts  # noqa: E402
from seo_utils import _weekly_lastmod  # noqa: E402

KST = ZoneInfo("Asia/Seoul")


class TestKstDate(unittest.TestCase):
    """주간 회고가 매주 건너뛰어지던 버그의 회귀 테스트."""

    def facts(self, iso):
        return kst_date_facts(datetime.fromisoformat(iso).replace(tzinfo=KST))

    def test_sunday_is_weekday_7(self):
        # 이 케이스가 바로 버그가 났던 시각이다: 08:00 KST 일요일에 컨테이너(UTC)는
        # 아직 토요일이라 bare `date +%u`가 6을 반환했다.
        self.assertEqual(self.facts("2026-07-26T08:00").get("weekday"), 7)

    def test_week_range_is_monday_to_sunday(self):
        f = self.facts("2026-07-26T08:00")
        self.assertEqual(f["start_date"], "2026-07-20")
        self.assertEqual(f["end_date"], "2026-07-26")
        self.assertEqual(f["week_label"], "2026-W30")

    def test_saturday_just_before_midnight_still_saturday(self):
        self.assertEqual(self.facts("2026-07-25T23:59")["weekday"], 6)

    def test_iso_year_rollover(self):
        # 2026-01-01이 목요일이라 2026년은 ISO 주가 53주다. 2026-W53은 2027-01-03까지
        # 이어지므로, 달력 연도가 아니라 ISO 연도를 써야 라벨이 맞다.
        f = self.facts("2027-01-03T08:00")
        self.assertEqual(f["week_label"], "2026-W53")
        self.assertEqual(f["start_date"], "2026-12-28")
        self.assertEqual(f["end_date"], "2027-01-03")

    def test_first_iso_week_of_next_year(self):
        f = self.facts("2027-01-04T08:00")
        self.assertEqual(f["week_label"], "2027-W01")
        self.assertEqual(f["weekday"], 1)


class TestFreshnessDefaults(unittest.TestCase):
    """2026-07-27: 12일 룩백 때문에 열흘 넘은 기사가 "여러 매체가 동시에 다룬 사건"
    으로 순위가 밀려 올라와 신선도가 떨어지던 문제. 1일로 줄였다 — 이 파이프라인이
    정확히 매일 같은 시각에 도는 일간 주기라, 1일 룩백이면 "지난 실행 이후 새로
    나온 기사 전부"와 정확히 일치한다. 기본값이 실수로 되돌아가는 걸 막는 회귀 테스트."""

    def test_lookback_default_is_one_day(self):
        args = parse_args([])
        self.assertEqual(args.lookback_days, 1)

    def test_stale_feed_threshold_is_independent_of_lookback(self):
        # 죽은 피드 판단 기준(넉넉하게 14일)이 신선도용 --lookback-days(1일)와 같은
        # 값으로 묶여 있으면, 며칠에 한 번 발행하는 정상 피드까지 매번 "죽었다"고
        # 오탐한다 — 실제로 1일로 줄이자마자 이 오탐이 발생해서 분리했다.
        self.assertGreater(STALE_FEED_THRESHOLD_DAYS, 7)


class TestSameStoryClustering(unittest.TestCase):
    """PLAN.md §12: 문턱값을 두 번 잘못 잡은 이력이 있는 로직."""

    def cluster(self, titles):
        candidates = [{"title": t, "source": f"src{i}"} for i, t in enumerate(titles)]
        return build_same_story_clusters(candidates)

    def test_same_event_across_outlets_is_grouped(self):
        ids = self.cluster([
            "Anthropic launches Opus 5",
            "Anthropic releases Opus 5 with new capabilities",
            "Meet the New Claude Opus 5: Agentic Coding",
            "Anthropic's Opus 5 is about token efficiency",
        ])
        self.assertEqual(len(set(ids)), 1, "같은 사건인데 갈라졌다")

    def test_unrelated_events_sharing_only_company_name_stay_separate(self):
        # "OpenAI"만 겹치는 무관한 기사들. 회사명 하나로 묶이면 안 된다.
        titles = [
            "OpenAI Launches GPT-6 With Native Voice",
            "GPT-6 Is Here: OpenAI's Biggest Update",
            "OpenAI unveils GPT-6, its most capable model",
            "OpenAI Sued Over Data Practices in California",
            "OpenAI Hires New CFO",
            "OpenAI Opens Tokyo Office",
            "OpenAI Partners With Retailer On Checkout",
        ]
        ids = self.cluster(titles)
        gpt6 = set(ids[:3])
        self.assertEqual(len(gpt6), 1, "GPT-6 기사 3건은 한 묶음이어야 한다")
        self.assertNotIn(ids[3], gpt6, "소송 기사가 GPT-6 클러스터에 잘못 붙었다")

    def test_completely_unrelated_titles_are_separate(self):
        ids = self.cluster([
            "Google DeepMind Releases AlphaFold 4",
            "Meta Open-Sources A New Speech Model",
        ])
        self.assertEqual(len(set(ids)), 2)

    def test_headline_boilerplate_is_not_a_keyword(self):
        # "Meet"/"Your" 같은 헤드라인 관용구는 대문자로 시작할 뿐 사건을 특정하지 않는다.
        for word in ("Meet", "Your", "You", "Watch", "Inside"):
            self.assertNotIn(word, extract_keywords(f"{word} The New Thing"))


class TestWeeklyLastmodGuard(unittest.TestCase):
    """이 함수는 일간 빌드에서도 불린다 — 여기서 예외가 나면 매일 사이트 생성이 죽는다."""

    def test_valid_label(self):
        self.assertEqual(_weekly_lastmod("2026-W30", "fallback"), "2026-07-26")

    def test_malformed_labels_fall_back_instead_of_raising(self):
        for bad in ("not-a-week-label", "2026-W99", "2026", "", "2026-Wxx"):
            self.assertEqual(_weekly_lastmod(bad, "2026-07-26"), "2026-07-26", bad)


class TestEmailHtmlEscaping(unittest.TestCase):
    """기사 링크는 서드파티 RSS에서 그대로 온다 — 속성 탈출이 실제로 가능했었다."""

    def build(self, link):
        digest = {"date": "2026-07-26", "articles": [{"title": "T", "summary_ko": "S", "link": link}]}
        return send_broadcast.build_html(
            digest, "https://www.dailyaithread.com", "https://www.dailyaithread.com/api/unsubscribe?email=a%40b.com&token=T"
        )

    def test_quote_in_url_cannot_inject_attribute(self):
        html_out = self.build('https://ex.com/a" onmouseover="alert(1)')
        self.assertNotIn('onmouseover="alert', html_out)

    def test_ampersand_in_unsubscribe_link_is_encoded(self):
        html_out = self.build("https://ex.com/a")
        self.assertIn("email=a%40b.com&amp;token=T", html_out)

    def test_normal_url_survives_intact(self):
        html_out = self.build("https://ex.com/a?x=1&y=2")
        self.assertIn("https://ex.com/a?x=1&amp;y=2", html_out)


class TestDigestValidation(unittest.TestCase):
    """digest는 매일 Claude가 손으로 쓰는 유일한 입력 — 파이프라인에서 가장 깨지기 쉽다."""

    GOOD_ARTICLE = {
        "title": "T", "link": "http://x", "source": "S",
        "published_at": "2026-07-26T00:00:00+00:00",
        "summary_ko": "a", "summary_en": "b",
        "implication_ko": "c", "implication_en": "d",
    }

    def load(self, payload, raw=None):
        import json
        import tempfile
        from generate_site import load_digest

        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "d.json"
            f.write_text(raw if raw is not None else json.dumps(payload), encoding="utf-8")
            return load_digest(f)

    def assertRejects(self, payload, needle, raw=None):
        with self.assertRaises(SystemExit) as cm:
            self.load(payload, raw=raw)
        self.assertIn(needle, str(cm.exception))

    def test_valid_digest_passes(self):
        d = self.load({"date": "2026-07-26", "articles": [self.GOOD_ARTICLE]})
        self.assertEqual(d["date"], "2026-07-26")

    def test_malformed_json_reports_position(self):
        self.assertRejects(None, "JSON 문법 오류", raw="{not json")

    def test_missing_date(self):
        self.assertRejects({"articles": [self.GOOD_ARTICLE]}, "date")

    def test_wrong_date_format(self):
        self.assertRejects({"date": "2026/07/26", "articles": [self.GOOD_ARTICLE]}, "YYYY-MM-DD")

    def test_empty_articles(self):
        self.assertRejects({"date": "2026-07-26", "articles": []}, "articles")

    def test_blank_required_field_is_caught(self):
        bad = dict(self.GOOD_ARTICLE, summary_ko="   ")
        self.assertRejects({"date": "2026-07-26", "articles": [bad]}, "summary_ko")

    def test_missing_published_at_is_caught(self):
        # 템플릿이 article.published_at[:10]으로 조건 없이 잘라 써서, 없으면 렌더링
        # 단계에서 UndefinedError로 죽는다 — 검증 단계에서 잡아야 원인이 드러난다.
        bad = {k: v for k, v in self.GOOD_ARTICLE.items() if k != "published_at"}
        self.assertRejects({"date": "2026-07-26", "articles": [bad]}, "published_at")

    def test_daily_insight_may_be_omitted(self):
        d = self.load({"date": "2026-07-26", "articles": [self.GOOD_ARTICLE]})
        self.assertIsNone(d.get("daily_insight"))

    def test_daily_insight_wrong_shape_is_caught(self):
        payload = {
            "date": "2026-07-26",
            "articles": [self.GOOD_ARTICLE],
            "daily_insight": {"headline_ko": "h", "headline_en": "h",
                              "paragraphs_ko": "not a list", "paragraphs_en": []},
        }
        self.assertRejects(payload, "paragraphs_ko")


class TestSentMarker(unittest.TestCase):
    """부분 발송 마커에 구독자 이메일이 새어 들어가면 안 된다 — 공개 저장소에 커밋된다."""

    def test_partial_marker_records_progress_without_pii(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp)
            send_broadcast.mark_sent(docs, "2026-07-26", 2, total_count=5, partial=True)
            marker = json.loads((docs / "archive" / "2026-07-26.sent.json").read_text(encoding="utf-8"))
        self.assertTrue(marker["partial"])
        self.assertEqual(marker["recipient_count"], 2)
        self.assertEqual(marker["total_count"], 5)
        self.assertNotIn("@", json.dumps(marker))

    def test_normal_marker_has_no_partial_flag(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp)
            send_broadcast.mark_sent(docs, "2026-07-26", 5)
            marker = json.loads((docs / "archive" / "2026-07-26.sent.json").read_text(encoding="utf-8"))
        self.assertNotIn("partial", marker)


if __name__ == "__main__":
    unittest.main(verbosity=2)
