"""요약 앞부분 분리와 기사별 읽는 시간.

GeekNews 런칭 첫 피드백이 "스크롤이 길고 요약·시사점 분량이 많다"였다. 요약 앞
문장만 남기고 나머지와 시사점을 접었다.

여기서 제일 위험한 건 **자르는 위치**다. 요약에는 용어사전 링크(<button>) 마크업이
섞이는데, 링크화된 문자열을 문장 경계에서 자르면 태그가 열린 채 끊겨 그 아래 카드
전체가 깨진다. 그래서 반드시 링크화 **전** 원문에서 자른다 — 그 순서를 여기서 고정한다.
"""

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from generate_site import (  # noqa: E402
    KO_CHARS_PER_MINUTE,
    LEDE_SENTENCES,
    apply_glossary,
    article_reading_times,
    reading_time,
    split_lede,
    split_sentences,
)


class TestSentenceSplit(unittest.TestCase):
    def test_korean_sentences(self):
        text = "첫 문장이다. 둘째 문장이다. 셋째 문장이다."
        self.assertEqual(len(split_sentences(text)), 3)

    def test_english_sentences(self):
        self.assertEqual(len(split_sentences("One thing happened. Then another. Finally this.")), 3)

    def test_abbreviations_do_not_split(self):
        """영어 요약에 실제로 나오는 것들이다. 여기서 잘리면 문장이 토막난다."""
        for text, expected in [
            ("The U.S. banned it. Then Europe did.", 2),
            ("Costs fell 5.5 percent. Demand rose.", 2),
            ("e.g. this is one. And two.", 2),
            ("Acme Inc. raised $2B. Investors cheered.", 2),
            ("Dr. Lee said no. The board agreed.", 2),
        ]:
            self.assertEqual(len(split_sentences(text)), expected, text)

    def test_decimal_numbers_never_split(self):
        self.assertEqual(len(split_sentences("It grew 1.5x in 2.3 years.")), 1)

    def test_empty_input(self):
        self.assertEqual(split_sentences(""), [])
        self.assertEqual(split_sentences(None), [])


class TestLedeSplit(unittest.TestCase):
    def test_splits_after_configured_sentence_count(self):
        text = "하나다. 둘이다. 셋이다. 넷이다."
        lede, rest = split_lede(text, max_sentences=2)
        self.assertEqual(lede, "하나다. 둘이다.")
        self.assertEqual(rest, "셋이다. 넷이다.")

    def test_short_text_has_no_rest(self):
        """문장이 기준 이하면 전부 보여주고 접을 것이 없다."""
        lede, rest = split_lede("하나뿐이다.", max_sentences=2)
        self.assertEqual(lede, "하나뿐이다.")
        self.assertEqual(rest, "")

    def test_nothing_is_lost(self):
        """자르면서 글자가 사라지면 독자가 내용을 못 본다."""
        text = "첫째 문장이다. 둘째 문장이다. 셋째 문장이다. 넷째 문장이다."
        lede, rest = split_lede(text)
        joined = (lede + " " + rest).strip()
        self.assertEqual(re.sub(r"\s+", "", joined), re.sub(r"\s+", "", text))

    def test_empty_input(self):
        self.assertEqual(split_lede(""), ("", ""))
        self.assertEqual(split_lede(None), ("", ""))

    def test_default_matches_module_constant(self):
        text = " ".join(f"문장{i}이다." for i in range(6))
        lede, _ = split_lede(text)
        self.assertEqual(len(split_sentences(lede)), LEDE_SENTENCES)


class TestMarkupIntegrity(unittest.TestCase):
    """분할이 링크화 **전에** 일어나는지 — 순서가 뒤집히면 태그가 끊긴다."""

    def digest(self):
        return {
            "date": "2026-08-05",
            "articles": [
                {
                    "summary_ko": "LLM이 등장했다. 프롬프트 인젝션이 문제다. 세 번째 문장이다.",
                    "implication_ko": "LLM은 중요하다. 두 번째다.",
                    "summary_en": "An LLM appeared. Prompt injection is the problem. A third sentence here.",
                    "implication_en": "The LLM matters. A second one.",
                }
            ],
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
        for field in ("summary_lede_ko", "summary_rest_ko", "summary_lede_en", "summary_rest_en",
                      "implication_ko", "implication_en"):
            html = a[field]
            self.assertEqual(html.count("<button"), html.count("</button>"), f"{field}: {html}")
            # 잘린 태그의 흔적 — 여는 꺾쇠 뒤에 닫는 꺾쇠가 없는 조각
            self.assertNotRegex(html, r"<button[^>]*$", field)

    def test_terms_are_linked_only_once_across_the_split(self):
        """접힌 부분에 같은 용어가 또 링크되면 한 기사에서 같은 단어가 두 번 눌린다."""
        d = self.digest()
        apply_glossary(d)
        a = d["articles"][0]
        combined = a["summary_lede_ko"] + a["summary_rest_ko"] + a["implication_ko"]
        self.assertEqual(combined.count('data-term="LLM"'), 1, combined)

    def test_lede_and_rest_together_cover_the_summary(self):
        d = self.digest()
        raw = d["articles"][0]["summary_ko"]
        apply_glossary(d)
        a = d["articles"][0]
        plain = re.sub(r"<[^>]+>", "", a["summary_lede_ko"] + " " + a["summary_rest_ko"])
        self.assertEqual(re.sub(r"\s+", "", plain), re.sub(r"\s+", "", raw))


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
        # 단위가 초/분으로 갈리므로 초로 환산해서 비교한다.
        as_seconds = lambda rt: rt["value"] * (60 if rt["unit"] == "min" else 1)
        short = {"summary_ko": "가" * 100, "implication_ko": "", "summary_en": "", "implication_en": ""}
        long = {"summary_ko": "가" * 100, "implication_ko": "나" * 900,
                "summary_en": "", "implication_en": ""}
        self.assertLess(as_seconds(article_reading_times(short)[0]),
                        as_seconds(article_reading_times(long)[0]))

    def test_real_archive_values_are_informative(self):
        """실제 데이터에서 값이 전부 같으면 표시할 이유가 없다."""
        path = Path(__file__).resolve().parent.parent / "docs" / "archive" / "2026-08-05.json"
        if not path.exists():
            self.skipTest("아카이브 없음")
        d = json.loads(path.read_text(encoding="utf-8"))
        values = {article_reading_times(a)[0]["value"] for a in d["articles"]}
        self.assertGreater(len(values), 1, f"모든 기사가 같은 값이면 정보가 아니다: {values}")


if __name__ == "__main__":
    unittest.main()
