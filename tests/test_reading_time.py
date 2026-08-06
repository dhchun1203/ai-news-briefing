"""기사별 읽는 시간, 그리고 글로서리 링크화가 마크업을 깨뜨리지 않는지.

읽는 시간은 GeekNews 런칭 첫 피드백("스크롤이 길다") 대응으로 붙였다. 여기서
중요한 건 **단위**다 — 분으로 반올림하면 10건이 전부 "1분"이 되어 아무것도
구분하지 못한다.
"""

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from generate_site import (  # noqa: E402
    KO_CHARS_PER_MINUTE,
    apply_glossary,
    article_reading_times,
    reading_time,
)


class TestReadingTime(unittest.TestCase):
    def test_under_90_seconds_reports_seconds(self):
        """기사 10건이 전부 1분 미만이라(실측 0.43~1.19분) 분으로 반올림하면
        모두 '1분'이 되어 아무것도 구분하지 못한다."""
        rt = reading_time(400, KO_CHARS_PER_MINUTE)  # 400자 / 500자per분 = 48초
        self.assertEqual(rt["unit"], "sec")
        self.assertEqual(rt["value"] % 10, 0)
        self.assertLess(rt["value"], 90)

    def test_long_text_reports_minutes(self):
        rt = reading_time(2000, KO_CHARS_PER_MINUTE)  # 4분
        self.assertEqual(rt["unit"], "min")
        self.assertGreaterEqual(rt["value"], 2)

    def test_never_shows_zero(self):
        self.assertGreaterEqual(reading_time(5, KO_CHARS_PER_MINUTE)["value"], 10)

    def test_empty_returns_nothing_to_render(self):
        self.assertEqual(reading_time(0, KO_CHARS_PER_MINUTE), {})

    def test_covers_the_collapsed_part_too(self):
        """펼치면 얼마나 걸리는지가 궁금한 값이라, 보이는 부분만 세면 의미가 없다."""
        as_seconds = lambda rt: rt["value"] * (60 if rt["unit"] == "min" else 1)
        short = {"summary_ko": "가" * 100, "implication_ko": "", "summary_en": "", "implication_en": ""}
        long = {"summary_ko": "가" * 100, "implication_ko": "나" * 900,
                "summary_en": "", "implication_en": ""}
        self.assertLess(as_seconds(article_reading_times(short)[0]),
                        as_seconds(article_reading_times(long)[0]))

    def test_real_archive_values_are_informative(self):
        """실제 데이터에서 값이 전부 같으면 표시할 이유가 없다."""
        path = Path(__file__).resolve().parent.parent / "docs" / "archive" / "2026-08-06.json"
        if not path.exists():
            self.skipTest("아카이브 없음")
        d = json.loads(path.read_text(encoding="utf-8"))
        values = {article_reading_times(a)[0]["value"] for a in d["articles"]}
        self.assertGreater(len(values), 1, f"모든 기사가 같은 값이면 정보가 아니다: {values}")

    def test_measured_before_markup(self):
        """링크화 뒤에 재면 <button> 태그가 글자 수에 껴서 시간이 부풀려진다."""
        digest = {
            "date": "2026-08-06",
            "articles": [{
                "summary_ko": "LLM이 등장했다.", "implication_ko": "중요하다.",
                "summary_en": "An LLM appeared.", "implication_en": "It matters.",
            }],
            "glossary": [{"term_ko": "LLM", "term_en": "LLM",
                          "explanation_ko": "x", "explanation_en": "x"}],
        }
        expected = article_reading_times(digest["articles"][0])
        apply_glossary(digest)
        self.assertIn("<button", digest["articles"][0]["summary_ko"])
        self.assertEqual((digest["articles"][0]["reading_ko"],
                          digest["articles"][0]["reading_en"]), expected)


class TestMarkupIntegrity(unittest.TestCase):
    """글로서리 링크화가 태그를 온전히 남기는지. 깨지면 그 아래 카드가 통째로 무너진다."""

    def digest(self):
        return {
            "date": "2026-08-06",
            "articles": [{
                "summary_ko": "LLM이 등장했다. 프롬프트 인젝션이 문제다. 세 번째 문장이다.",
                "implication_ko": "LLM은 중요하다. 두 번째다.",
                "summary_en": "An LLM appeared. Prompt injection is the problem. A third one.",
                "implication_en": "The LLM matters. A second one.",
            }],
            "glossary": [
                {"term_ko": "LLM", "term_en": "LLM", "explanation_ko": "x", "explanation_en": "x"},
                {"term_ko": "프롬프트 인젝션", "term_en": "prompt injection",
                 "explanation_ko": "y", "explanation_en": "y"},
            ],
        }

    def test_every_button_tag_is_balanced(self):
        d = self.digest()
        apply_glossary(d)
        a = d["articles"][0]
        for field in ("summary_ko", "summary_en", "implication_ko", "implication_en"):
            html = a[field]
            self.assertEqual(html.count("<button"), html.count("</button>"), f"{field}: {html}")
            self.assertNotRegex(html, r"<button[^>]*$", field)

    def test_terms_are_linked_once_per_article(self):
        """같은 기사에서 같은 용어가 여러 번 클릭 가능하면 산만하다."""
        d = self.digest()
        apply_glossary(d)
        a = d["articles"][0]
        combined = a["summary_ko"] + a["implication_ko"]
        self.assertEqual(combined.count('data-term="LLM"'), 1, combined)

    def test_summary_text_is_preserved(self):
        d = self.digest()
        raw = d["articles"][0]["summary_ko"]
        apply_glossary(d)
        plain = re.sub(r"<[^>]+>", "", d["articles"][0]["summary_ko"])
        self.assertEqual(re.sub(r"\s+", "", plain), re.sub(r"\s+", "", raw))


if __name__ == "__main__":
    unittest.main()
