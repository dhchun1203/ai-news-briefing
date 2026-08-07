"""일일 브리핑 메일이 구독자의 언어로 나가는지.

/en/ 에서 구독한 독자가 한국어 제목·한국어 요약·한국어 사이트 링크가 담긴 메일을
받고 있었다. 방문자 국가 1위가 미국이라 조용히 큰 구멍이었다.

여기서 제일 중요한 검사는 **영어 메일에 한글이 한 글자도 없는지**다. 분기를 한 곳
빠뜨려도 그 부분만 한국어로 남는데, 한국어 사용자는 영어 메일을 볼 일이 없어서
아무도 눈치채지 못한다. 사람 눈 대신 기계가 본다.
"""

import re
import sys
import unittest
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from send_broadcast import (  # noqa: E402
    COPY,
    LANGS,
    article_title,
    build_catchup_notice,
    build_html,
    build_weekly_teaser_block,
    home_path,
    normalize_lang,
    unsubscribe_url,
)

HANGUL = re.compile(r"[가-힣]")

DIGEST = {
    "date": "2026-08-05",
    "daily_insight": {
        "headline_ko": "한국어 헤드라인", "headline_en": "English headline",
        "watch_ko": "한국어 지켜볼 신호", "watch_en": "English signal to watch",
    },
    "articles": [
        {
            "title": "Texas halts data center connections",
            "title_en": None,
            "summary_ko": "텍사스가 데이터센터 연결을 중단했다.",
            "summary_en": "Texas paused new data center grid hookups.",
            "link": "https://example.test/a",
        },
        {
            "title": "카카오, 새 모델 공개",
            "title_en": "Kakao unveils a new model",
            "summary_ko": "카카오가 새 모델을 공개했다.",
            "summary_en": "Kakao unveiled a new model.",
            "link": "https://example.test/b",
        },
    ],
}

WEEKLY = {"week_label": "2026-W32", "headline_ko": "이번 주 한국어", "headline_en": "This week in English"}

SITE = "https://x.test"


def render(lang, **kw):
    return build_html(
        DIGEST,
        SITE,
        unsubscribe_url(SITE, "secret", "u@x.com", lang),
        weekly_block=build_weekly_teaser_block(WEEKLY, SITE, lang),
        lang=lang,
        **kw,
    )


class TestNoLanguageBleed(unittest.TestCase):
    def test_english_email_contains_no_korean(self):
        """이 테스트 하나가 분기 누락을 전부 잡는다."""
        found = HANGUL.findall(render("en"))
        self.assertEqual(found, [], f"영문 메일에 한글이 남아 있음: {''.join(found)[:120]}")

    def test_english_catchup_notice_contains_no_korean(self):
        found = HANGUL.findall(render("en", catchup=True))
        self.assertEqual(found, [], f"영문 지연발송 메일에 한글: {''.join(found)[:120]}")

    def test_english_subject_contains_no_korean(self):
        subject = COPY["en"]["catchup_prefix"] + COPY["en"]["subject"].format(date="2026-08-05", n=2)
        self.assertEqual(HANGUL.findall(subject), [])

    def test_korean_email_is_still_korean(self):
        """영문화 작업이 한국어 메일을 망가뜨리지 않았는지."""
        html = render("ko")
        self.assertTrue(HANGUL.search(html))
        self.assertIn("텍사스가 데이터센터", html)


class TestLanguageRouting(unittest.TestCase):
    def test_english_uses_english_summaries(self):
        html = render("en")
        self.assertIn("Texas paused new data center grid hookups.", html)
        self.assertNotIn("텍사스가", html)

    def test_english_uses_title_en_when_source_is_korean(self):
        self.assertEqual(article_title(DIGEST["articles"][1], "en"), "Kakao unveils a new model")

    def test_english_falls_back_to_original_title(self):
        """title_en은 출처가 한국어일 때만 채워진다. 없으면 원문 헤드라인이 이미 영어다."""
        self.assertEqual(
            article_title(DIGEST["articles"][0], "en"), "Texas halts data center connections"
        )

    def test_korean_always_uses_original_title(self):
        self.assertEqual(article_title(DIGEST["articles"][1], "ko"), "카카오, 새 모델 공개")

    def test_english_links_point_into_en_section(self):
        html = render("en")
        self.assertIn(f"{SITE}/en", html)
        self.assertIn(f"{SITE}/en/weekly/2026-W32.html", html)

    def test_korean_links_stay_on_korean_site(self):
        html = render("ko")
        self.assertIn(f"{SITE}/index.html", html)
        self.assertNotIn("/en/weekly/", html)

    def test_english_insight_uses_english_headline(self):
        html = render("en")
        self.assertIn("English headline", html)
        self.assertNotIn("한국어 헤드라인", html)

    def test_unsubscribe_link_carries_lang(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(unsubscribe_url(SITE, "s", "u@x.com", "en")).query)
        self.assertEqual(q["lang"], ["en"])
        self.assertTrue(q["token"][0])

    def test_unsubscribe_signature_unchanged_by_lang(self):
        """서명에 lang을 넣으면 이미 발송된 모든 구독취소 링크가 죽는다."""
        ko = urllib.parse.parse_qs(urllib.parse.urlparse(unsubscribe_url(SITE, "s", "u@x.com", "ko")).query)
        en = urllib.parse.parse_qs(urllib.parse.urlparse(unsubscribe_url(SITE, "s", "u@x.com", "en")).query)
        self.assertEqual(ko["token"], en["token"])

    def test_home_path_per_language(self):
        self.assertEqual(home_path("en"), "/en")
        self.assertEqual(home_path("ko"), "/index.html")


class TestWatchSignal(unittest.TestCase):
    """지켜볼 신호가 메일에도 실리는지.

    이 브리핑에서 유일하게 앞을 내다보는 문장인데 메일에는 빠져 있었다. 사이트에
    들어와야만 볼 수 있게 둘 이유가 없다.
    """

    def test_included_in_both_languages(self):
        self.assertIn("한국어 지켜볼 신호", render("ko"))
        self.assertIn("English signal to watch", render("en"))

    def test_label_is_localized(self):
        self.assertIn(COPY["ko"]["watch_label"], render("ko"))
        self.assertIn(COPY["en"]["watch_label"], render("en"))

    def test_english_mail_with_watch_has_no_korean(self):
        self.assertEqual(HANGUL.findall(render("en")), [])

    def test_sits_below_the_insight_headline(self):
        """사이트와 같은 자리여야 한다 — 구조가 다르면 읽는 사람이 매번 다시 찾는다."""
        html = render("ko")
        self.assertLess(html.index("한국어 헤드라인"), html.index("한국어 지켜볼 신호"))

    def test_missing_english_watch_drops_only_that_line(self):
        """영문 신호가 없을 때 한국어를 끼워 넣지 않는다. 인사이트는 그대로 남는다."""
        digest = dict(DIGEST, daily_insight={
            "headline_ko": "한국어 헤드라인", "headline_en": "English headline",
            "watch_ko": "한국어만 있다", "watch_en": "",
        })
        html = build_html(digest, SITE, "https://x.test/u", lang="en")
        self.assertEqual(HANGUL.findall(html), [])
        self.assertIn("English headline", html)
        self.assertNotIn(COPY["en"]["watch_label"], html)

    def test_no_insight_means_no_watch(self):
        """헤드라인이 없으면 인사이트 블록 자체가 안 나온다 — 신호만 떠 있으면 안 된다."""
        digest = dict(DIGEST, daily_insight={"headline_ko": "", "watch_ko": "신호만 있다"})
        html = build_html(digest, SITE, "https://x.test/u", lang="ko")
        self.assertNotIn("신호만 있다", html)


class TestMissingTranslations(unittest.TestCase):
    def test_missing_english_summary_omits_it_rather_than_falling_back(self):
        """영어 메일에 한국어 요약을 끼워 넣느니 요약 없이 제목만 내는 편이 낫다."""
        digest = {
            "date": "2026-08-05",
            "daily_insight": {},
            "articles": [
                {
                    "title": "A story",
                    "summary_ko": "한국어 요약만 있다",
                    "summary_en": "",
                    "link": "https://example.test/a",
                }
            ],
        }
        html = build_html(digest, SITE, "https://x.test/u", lang="en")
        self.assertEqual(HANGUL.findall(html), [])
        self.assertIn("A story", html)

    def test_missing_english_weekly_headline_drops_the_block(self):
        weekly = {"week_label": "2026-W32", "headline_ko": "한국어만", "headline_en": ""}
        self.assertEqual(build_weekly_teaser_block(weekly, SITE, "en"), "")

    def test_missing_english_insight_drops_the_block(self):
        digest = dict(DIGEST, daily_insight={"headline_ko": "한국어만", "headline_en": ""})
        html = build_html(digest, SITE, "https://x.test/u", lang="en")
        self.assertEqual(HANGUL.findall(html), [])


class TestLangNormalization(unittest.TestCase):
    def test_unknown_values_fall_back_to_korean(self):
        for value in (None, "", "fr", "EN-US", "ko-KR", 5, "  "):
            self.assertIn(normalize_lang(value), LANGS)
        self.assertEqual(normalize_lang("fr"), "ko")
        self.assertEqual(normalize_lang(None), "ko")

    def test_case_and_whitespace_tolerated(self):
        self.assertEqual(normalize_lang(" EN "), "en")
        self.assertEqual(normalize_lang("KO"), "ko")

    def test_every_copy_key_exists_in_both_languages(self):
        self.assertEqual(set(COPY["ko"]), set(COPY["en"]))
        for lang in LANGS:
            for key, value in COPY[lang].items():
                self.assertTrue(str(value).strip(), f"{lang}.{key} 비어 있음")

    def test_english_copy_table_has_no_korean(self):
        for key, value in COPY["en"].items():
            self.assertEqual(HANGUL.findall(str(value)), [], f"COPY['en']['{key}']에 한글")

    def test_catchup_notice_language(self):
        self.assertEqual(HANGUL.findall(build_catchup_notice("2026-08-05", "en")), [])
        self.assertTrue(HANGUL.search(build_catchup_notice("2026-08-05", "ko")))


if __name__ == "__main__":
    unittest.main()
