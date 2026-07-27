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
    RESERVE_COUNT,
    STALE_FEED_THRESHOLD_DAYS,
    build_same_story_clusters,
    extract_keywords,
    is_self_promo_post,
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


class TestSelfPromoFilter(unittest.TestCase):
    """HN의 Show/Ask/Tell/Launch HN 글은 뉴스가 아니라 자기홍보·토론이다.
    실제로 하루 후보 20건 중 4건이 이런 글이었고, Show HN은 원문이 제품
    랜딩페이지라 요약할 기사 본문 자체가 없어 부실 항목의 원인이 됐다."""

    def test_hn_self_promo_prefixes_are_filtered(self):
        for title in (
            "Show HN: Rainslice – AI Employees for Home Services Businesses",
            "Ask HN: 1950's Chip industry undermined unions how is AI not doing the same",
            "Tell HN: something about AI",
            "Launch HN: Acme (YC W26) – AI for lawyers",
        ):
            with self.subTest(title=title):
                self.assertTrue(is_self_promo_post(title))

    def test_case_and_surrounding_whitespace_do_not_matter(self):
        self.assertTrue(is_self_promo_post("  show hn: lowercase variant"))
        self.assertTrue(is_self_promo_post("SHOW HN: shouting variant"))

    def test_real_news_is_not_filtered(self):
        for title in (
            "Terence Tao: Mathematics in the Age of AI [pdf]",
            "AI bet goes awry: Oracle fires 21,000 employees",
            "Anthropic launches Opus 5",
            # 제목 중간에 들어간 경우까지 지우면 정상 기사를 잃는다 — 접두사만 본다.
            "How to show HN readers your work",
        ):
            with self.subTest(title=title):
                self.assertFalse(is_self_promo_post(title))


class TestReserveDefaults(unittest.TestCase):
    """예비 후보는 원문을 못 읽거나 실을 가치가 없는 기사를 교체하기 위한 것이라,
    기본값이 0이면 장치 자체가 동작하지 않는다."""

    def test_reserve_count_default_is_positive(self):
        self.assertEqual(parse_args([]).reserve_count, RESERVE_COUNT)
        self.assertGreater(RESERVE_COUNT, 0)


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

    def test_topics_may_be_omitted(self):
        # 과거 아카이브에는 topics가 없다 — 선택 필드로 남겨두지 않으면 재생성이 깨진다.
        d = self.load({"date": "2026-07-26", "articles": [self.GOOD_ARTICLE]})
        self.assertIsNone(d["articles"][0].get("topics"))

    def test_known_topic_slug_passes(self):
        from generate_site import load_topics

        slug = load_topics()[0]["slug"]
        good = dict(self.GOOD_ARTICLE, topics=[slug])
        d = self.load({"date": "2026-07-26", "articles": [good]})
        self.assertEqual(d["articles"][0]["topics"], [slug])

    def test_unknown_topic_slug_is_rejected_with_valid_list(self):
        # 오타를 통과시키면 그 기사만 어느 토픽 페이지에도 안 잡힌 채 조용히 사라진다.
        bad = dict(self.GOOD_ARTICLE, topics=["not-a-real-topic"])
        with self.assertRaises(SystemExit) as cm:
            self.load({"date": "2026-07-26", "articles": [bad]})
        message = str(cm.exception)
        self.assertIn("not-a-real-topic", message)
        self.assertIn("config/topics.json", message)  # 유효 목록을 함께 보여줘야 고칠 수 있다

    def test_topics_must_be_a_list(self):
        bad = dict(self.GOOD_ARTICLE, topics="models")
        self.assertRejects({"date": "2026-07-26", "articles": [bad]}, "topics")

    def test_cross_source_count_must_be_non_negative_int(self):
        for value in (-1, "3", 1.5):
            with self.subTest(value=value):
                bad = dict(self.GOOD_ARTICLE, cross_source_count=value)
                self.assertRejects({"date": "2026-07-26", "articles": [bad]}, "cross_source_count")


class TestArchiveJsonRoundTrip(unittest.TestCase):
    """docs/archive/*.json은 토픽 페이지·커버리지 배지가 과거 데이터를 읽는 유일한
    경로다(data/*.json은 커밋되지 않는다) — 여기서 필드가 빠지면 조용히 사라진다."""

    def _save_and_load(self, article):
        import json
        import tempfile
        from generate_site import save_archive_json

        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp)
            save_archive_json(archive, {"date": "2026-07-26", "articles": [article]})
            return json.loads((archive / "2026-07-26.json").read_text(encoding="utf-8"))["articles"][0]

    def test_topics_and_count_survive(self):
        saved = self._save_and_load(
            {"title": "T", "link": "http://x", "source": "S", "topics": ["models", "safety"], "cross_source_count": 3}
        )
        self.assertEqual(saved["topics"], ["models", "safety"])
        self.assertEqual(saved["cross_source_count"], 3)

    def test_missing_fields_become_safe_defaults(self):
        saved = self._save_and_load({"title": "T", "link": "http://x", "source": "S"})
        self.assertEqual(saved["topics"], [])
        self.assertEqual(saved["cross_source_count"], 0)


class TestSiteStats(unittest.TestCase):
    """랜딩의 신뢰 지표는 아카이브에서 자동 계산된다 — 손으로 고칠 값이 아니다."""

    def _stats(self, days):
        import json
        import tempfile
        from generate_site import collect_site_stats

        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp)
            for date, count in days:
                payload = {"date": date, "articles": [{"title": f"a{i}"} for i in range(count)]}
                (archive / f"{date}.json").write_text(json.dumps(payload), encoding="utf-8")
            # 발송 마커는 브리핑이 아니므로 일수에 세면 안 된다
            (archive / "2026-07-23.sent.json").write_text('{"recipient_count": 1}', encoding="utf-8")
            return collect_site_stats(archive, glossary_count=7)

    def test_counts_days_articles_and_start_date(self):
        stats = self._stats([("2026-07-23", 10), ("2026-07-24", 9), ("2026-07-25", 10)])
        self.assertEqual(stats["days"], 3)
        self.assertEqual(stats["articles"], 29)
        self.assertEqual(stats["since"], "2026-07-23")
        self.assertEqual(stats["terms"], 7)

    def test_empty_archive_reports_zero_without_crashing(self):
        stats = self._stats([])
        self.assertEqual(stats["days"], 0)
        self.assertIsNone(stats["since"])


class TestRssFeed(unittest.TestCase):
    """피드는 아카이브 전량을 매번 다시 스캔해 재작성하는 멱등 산출물이다."""

    def _build(self, lang="ko"):
        import json
        import tempfile
        from xml.etree import ElementTree

        from seo_utils import build_rss_feed

        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp)
            archive = docs / "archive"
            archive.mkdir()
            for date in ("2026-07-25", "2026-07-26"):
                (archive / f"{date}.json").write_text(
                    json.dumps(
                        {
                            "date": date,
                            "generated_at": f"{date}T08:00:00",
                            "daily_insight": {"headline_ko": f"헤드라인 {date}", "headline_en": f"Headline {date}",
                                              "paragraphs_ko": ["첫 문단"], "paragraphs_en": ["First para"]},
                            "articles": [{"title": "T & <b>", "link": "http://x?a=1&b=2",
                                          "summary_ko": "요약", "summary_en": "Summary"}],
                        }
                    ),
                    encoding="utf-8",
                )
            # 발송 마커가 피드 항목으로 새어 들어가면 안 된다
            (archive / "2026-07-26.sent.json").write_text('{"recipient_count": 1}', encoding="utf-8")
            count = build_rss_feed(docs, "https://example.com", lang)
            path = docs / "en" / "feed.xml" if lang == "en" else docs / "feed.xml"
            return count, ElementTree.fromstring(path.read_text(encoding="utf-8"))

    def test_feed_is_well_formed_with_one_item_per_day(self):
        count, root = self._build()
        self.assertEqual(count, 2)
        items = root.findall("./channel/item")
        self.assertEqual(len(items), 2)
        # 최신 날짜가 먼저 와야 피드 리더가 올바른 순서로 보여준다
        self.assertEqual(items[0].find("link").text, "https://example.com/archive/2026-07-26")

    def test_item_title_uses_daily_insight_headline(self):
        _, root = self._build()
        self.assertEqual(root.find("./channel/item/title").text, "헤드라인 2026-07-26")

    def test_english_feed_uses_english_fields(self):
        _, root = self._build(lang="en")
        self.assertEqual(root.find("./channel/item/title").text, "Headline 2026-07-26")
        self.assertIn("First para", root.find("./channel/item/description").text)

    def test_pubdate_is_rfc822_with_explicit_timezone(self):
        # 타임존이 없으면 피드 리더마다 9시간씩 어긋나게 해석한다.
        _, root = self._build()
        self.assertTrue(root.find("./channel/item/pubDate").text.endswith("+0900"))

    def test_content_markup_is_escaped_but_our_own_wrappers_are_not(self):
        # description은 HTML 조각이라 두 층의 이스케이프가 겹친다. 기사 제목에 섞인
        # <b>는 마크업이 아니라 글자로 남아야 하고(그래야 피드 리더에서 제목이 굵어지는
        # 등 원문에 없던 서식이 생기지 않는다), 우리가 만든 <a>/<ul>은 살아 있어야 한다.
        # XML 파싱이 통과한다는 것 자체가 & 처리가 올바르다는 뜻이기도 하다.
        _, root = self._build()
        description = root.find("./channel/item/description").text
        self.assertIn("&lt;b&gt;", description)
        self.assertIn("<ul><li><a href=", description)
        self.assertIn("a=1&amp;b=2", description)

    def test_empty_archive_still_produces_valid_channel(self):
        import tempfile
        from xml.etree import ElementTree

        from seo_utils import build_rss_feed

        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp)
            self.assertEqual(build_rss_feed(docs, "https://example.com"), 0)
            root = ElementTree.fromstring((docs / "feed.xml").read_text(encoding="utf-8"))
        self.assertEqual(len(root.findall("./channel/item")), 0)


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
