#!/usr/bin/env python3
"""파이프라인의 순수 함수들에 대한 회귀 테스트.

이 저장소는 의존성을 최소로 유지한다(요청은 urllib, npm 패키지 없음). 그래서 pytest
대신 표준 라이브러리 unittest를 쓴다 — 새 의존성 없이 `python -m unittest`로 돌아간다.

여기 담긴 것들은 전부 "조용히 틀려도 아무도 모르는" 종류라 테스트 가치가 높다:
- 같은 사건 클러스터링: 문턱값을 두 번 잘못 잡았던 이력이 있다(PLAN.md §12).
- KST 날짜 계산: 틀리면 주간 회고가 매주 건너뛰어진다(실제로 그랬다).
- 메일 HTML 이스케이프: 뚫려도 발송 자체는 성공해서 티가 안 난다.
"""
import json
import sys
import tempfile
import unittest
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import send_broadcast  # noqa: E402
from fetch_articles import (  # noqa: E402
    CROSS_SOURCE_CAP,
    PRIMARY_MIN_SLOTS,
    RESERVE_COUNT,
    STALE_FEED_THRESHOLD_DAYS,
    build_funnel,
    build_same_story_clusters,
    compute_rank_score,
    extract_keywords,
    is_self_promo_post,
    parse_args,
)
from kst_date import kst_date_facts  # noqa: E402
import seo_utils  # noqa: E402
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


class TestSourcedField(unittest.TestCase):
    """원문을 읽었는지(`sourced`)를 아카이브에 보존한다.

    "헤드라인이 아니라 원문을 읽는다"가 이 브리핑의 첫 번째 포지셔닝인데 그것만
    숫자가 없었다. 다만 이 값 때문에 **과거 아카이브가 바뀌면 안 된다** — 그게
    이 저장소의 1번 규칙이다.
    """

    def save(self, articles, tmp):
        from generate_site import save_archive_json
        save_archive_json(tmp, {"date": "2026-08-08", "generated_at": "x", "articles": articles})
        return json.loads((tmp / "2026-08-08.json").read_text(encoding="utf-8"))

    def test_value_is_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            out = self.save([{"link": "a", "sourced": "fulltext"},
                             {"link": "b", "sourced": "rss_summary"}], Path(d))
        self.assertEqual([a["sourced"] for a in out["articles"]], ["fulltext", "rss_summary"])

    def test_missing_value_drops_the_key_entirely(self):
        """null을 써 넣으면 그것만으로 과거 아카이브 전체에 diff가 난다."""
        with tempfile.TemporaryDirectory() as d:
            out = self.save([{"link": "a"}], Path(d))
        self.assertNotIn("sourced", out["articles"][0])

    def test_regeneration_is_byte_identical(self):
        """같은 입력으로 두 번 저장하면 파일이 한 바이트도 달라지면 안 된다."""
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            arts = [{"link": "a", "sourced": "fulltext"}, {"link": "b"}]
            self.save(arts, tmp)
            first = (tmp / "2026-08-08.json").read_bytes()
            self.save(arts, tmp)
            self.assertEqual((tmp / "2026-08-08.json").read_bytes(), first)


class TestSourceDisplayLabel(unittest.TestCase):
    """매체명은 화면에서만 갈아 끼운다. 저장값은 절대 바뀌면 안 된다."""

    def test_english_pages_use_name_en(self):
        from generate_site import source_label

        self.assertEqual(source_label("AI타임스", "en"), "AI Times")

    def test_korean_pages_keep_the_original(self):
        from generate_site import source_label

        self.assertEqual(source_label("AI타임스", "ko"), "AI타임스")

    def test_unknown_source_falls_back_to_itself(self):
        """feeds.json에 name_en이 없는 매체는 그대로 나온다 — 빈칸이 되면 안 된다."""
        from generate_site import source_label

        for lang in ("ko", "en"):
            self.assertEqual(source_label("TechCrunch AI", lang), "TechCrunch AI")
            self.assertEqual(source_label("듣도 보도 못한 매체", lang), "듣도 보도 못한 매체")

    def test_archive_keeps_the_stored_name(self):
        """표시용 이름이 아카이브에 새면 과거분과 안 맞아 매체별 집계가 둘로 갈라진다."""
        from generate_site import save_archive_json

        with tempfile.TemporaryDirectory() as d:
            arc = Path(d)
            save_archive_json(arc, {
                "date": "2026-08-08", "generated_at": "x",
                "articles": [{"link": "a", "source": "AI타임스"}],
            })
            saved = json.loads((arc / "2026-08-08.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["articles"][0]["source"], "AI타임스")

    def test_aggregation_groups_by_stored_name(self):
        """집계도 저장값 기준이어야 한 매체가 두 줄로 갈라지지 않는다."""
        from generate_site import collect_site_data

        with tempfile.TemporaryDirectory() as d:
            arc = Path(d)
            (arc / "2026-08-01.json").write_text(json.dumps({
                "date": "2026-08-01",
                "articles": [{"source": "AI타임스"}, {"source": "AI타임스"}],
                "glossary": [],
            }, ensure_ascii=False), encoding="utf-8")
            data = collect_site_data(arc)
        self.assertEqual([s["key"] for s in data["sources"]], ["AI타임스"])
        self.assertEqual(data["sources"][0]["count"], 2)


class TestSiteDataAggregation(unittest.TestCase):
    """/data 페이지 집계. **채택된 기사만** 센다 — 이 페이지의 정직성이 곧 방어선이라
    숫자가 틀리면 페이지의 존재 이유가 무너진다."""

    def build(self, days):
        from generate_site import collect_site_data

        with tempfile.TemporaryDirectory() as d:
            arc = Path(d)
            for date, payload in days.items():
                (arc / f"{date}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            return collect_site_data(arc)

    def sample(self):
        return {
            "2026-08-01": {"date": "2026-08-01", "articles": [
                {"source": "A", "topics": ["x", "y"]},
                {"source": "A", "topics": ["x"]},
                {"source": "B", "topics": []},
            ], "glossary": [{"term_ko": "가"}, {"term_ko": "나"}]},
            "2026-08-02": {"date": "2026-08-02", "articles": [
                {"source": "B", "topics": ["y"]},
            ], "glossary": [{"term_ko": "가"}, {"term_ko": "다"}]},
        }

    def test_counts_only_published_articles(self):
        d = self.build(self.sample())
        self.assertEqual(d["article_total"], 4)
        self.assertEqual(d["day_count"], 2)

    def test_source_percentages_sum_to_100(self):
        """비율이 안 맞으면 그래프가 거짓말을 한다."""
        d = self.build(self.sample())
        self.assertAlmostEqual(sum(s["percent"] for s in d["sources"]), 100.0, places=1)

    def test_repeated_terms_counted_once(self):
        """'가'가 이틀 나와도 누적 용어는 하나다 — 아니면 숫자가 부풀려진다."""
        d = self.build(self.sample())
        self.assertEqual(d["term_total"], 3)
        self.assertEqual(d["term_per_day"], round(3 / 2, 1))

    def test_period_bounds_are_actual_days(self):
        d = self.build(self.sample())
        self.assertEqual((d["first_day"], d["last_day"]), ("2026-08-01", "2026-08-02"))

    def test_others_bucket_when_more_sources_than_shown(self):
        from generate_site import DATA_PAGE_TOP_SOURCES
        n = DATA_PAGE_TOP_SOURCES + 3
        # 꼬리 매체마다 기사 수를 다르게 준다. 전부 1건이면 "건수 합"과 "매체 수"가
        # 같아져서, 합계 대신 개수를 세는 실수를 테스트가 못 잡는다(실제로 놓쳤다).
        articles = []
        for i in range(n):
            for _ in range(i + 1):
                articles.append({"source": f"S{i:02d}", "topics": []})
        total = sum(i + 1 for i in range(n))
        d = self.build({"2026-08-01": {"date": "2026-08-01", "articles": articles, "glossary": []}})
        others = d["sources"][-1]
        self.assertTrue(others.get("is_others"))
        self.assertEqual(others["hidden_count"], n - DATA_PAGE_TOP_SOURCES)
        self.assertEqual(sum(s["count"] for s in d["sources"]), total, "기타로 묶으면서 건수가 샜다")
        self.assertGreater(others["count"], others["hidden_count"], "기타가 건수가 아니라 매체 수로 세졌다")
        self.assertEqual(d["source_kinds"], n)

    def test_empty_archive_returns_nothing_to_render(self):
        self.assertEqual(self.build({}), {})

    def test_multi_topic_articles_counted_per_topic(self):
        """기사 하나에 주제가 여러 개면 합계가 기사 수보다 크다 — 페이지가 그걸 밝힌다."""
        d = self.build(self.sample())
        self.assertEqual(sum(t["count"] for t in d["topics"]), 4)  # x2 + y2


class TestFunnelAccounting(unittest.TestCase):
    """퍼널은 **사후 집계**다. 선별 로직에 끼어들면 안 되고, 합이 맞아야 한다."""

    COUNTERS = {
        "feeds_total": 12, "feeds_failed": 0, "entries_seen": 1390,
        "in_lookback": 88, "skipped_duplicates": 8, "skipped_self_promo": 0,
    }

    def build(self, candidates, cluster_ids, selected, max_per_source=3):
        return build_funnel(candidates, cluster_ids, selected, max_per_source, dict(self.COUNTERS))

    def cand(self, link, source, ):
        return {"link": link, "source": source, "title": link}

    def test_counts_add_up_to_candidates(self):
        """합이 안 맞으면 퍼널 그림이 거짓말을 한다."""
        c = [self.cand(f"l{i}", "A" if i < 6 else "B") for i in range(10)]
        ids = list(range(10))
        sel = [c[0], c[1], c[6]]
        f = self.build(c, ids, sel)
        total = f["selected"] + f["dropped_same_story"] + f["dropped_source_cap"] + f["dropped_rank"]
        self.assertEqual(total, f["candidates_total"], f)

    def test_same_cluster_as_selected_counts_as_same_story(self):
        c = [self.cand("a", "A"), self.cand("b", "B"), self.cand("c", "C")]
        ids = [0, 0, 1]           # a와 b가 같은 사건
        f = self.build(c, ids, [c[0]])
        self.assertEqual(f["dropped_same_story"], 1)   # b
        self.assertEqual(f["dropped_rank"], 1)         # c

    def test_source_over_cap_counts_as_source_cap(self):
        c = [self.cand(f"a{i}", "A") for i in range(5)]
        ids = list(range(5))
        f = self.build(c, ids, c[:2], max_per_source=2)
        self.assertEqual(f["dropped_source_cap"], 3)
        self.assertEqual(f["dropped_same_story"], 0)

    def test_same_story_takes_precedence_over_source_cap(self):
        """둘 다 해당하면 먼저 걸린 쪽으로 센다 — 이중 계상이면 합이 깨진다."""
        c = [self.cand("a", "A"), self.cand("b", "A")]
        ids = [0, 0]
        f = self.build(c, ids, [c[0]], max_per_source=1)
        self.assertEqual(f["dropped_same_story"], 1)
        self.assertEqual(f["dropped_source_cap"], 0)

    def test_does_not_mutate_inputs(self):
        """계측이 선별 결과를 건드리면 그날 브리핑이 바뀐다."""
        c = [self.cand("a", "A"), self.cand("b", "B")]
        snapshot = [dict(x) for x in c]
        sel = [c[0]]
        self.build(c, [0, 1], sel)
        self.assertEqual(c, snapshot)
        self.assertEqual([x["link"] for x in sel], ["a"])

    def test_empty_day_does_not_crash(self):
        f = self.build([], [], [])
        self.assertEqual(f["candidates_total"], 0)
        self.assertEqual(f["selected"], 0)

    def test_carries_collection_stage_counters(self):
        f = self.build([self.cand("a", "A")], [0], [])
        for k, v in self.COUNTERS.items():
            self.assertEqual(f[k], v, k)


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

    def test_company_name_alone_does_not_merge_unrelated_stories(self):
        """2026-07-29 실측 회귀. 후보 44건에서 "Google"만 공유하는 무관한 5건이
        한 묶음이 되어, 선별 루프가 그중 4건을 중복으로 폐기하고 있었다.
        흔한 키워드 임계값(6)은 절대값이라 회사명이 늘 그 밑에 깔린다."""
        titles = [
            "5 ways to host the ultimate dinner party with Google Search",
            "Despite AI hype, Google's data shows workers aren't automating jobs",
            '"Google and Reddit do not own the Internet," web scraper says',
            "Verizon touts $1B dark fiber deal for Google data centers",
            "Google's AI search is rapidly becoming the default, new data shows",
        ]
        ids = self.cluster(titles)
        self.assertEqual(
            len(set(ids)), len(titles),
            "회사명 하나만 겹치는 무관한 기사들이 같은 사건으로 묶였다 — 나머지가 폐기된다",
        )

    def test_chain_merge_does_not_propagate(self):
        """A–B가 한 키워드로, B–C가 다른 키워드로 걸려도 A–C까지 묶이면 안 된다.

        예전에는 union-find라 짝만 맞으면 이어 붙었고, 그 전이 때문에 서로 아무
        관계도 없는 A와 C가 한 덩어리가 됐다. 완전연결로 바꿔 클러스터에 들어가려면
        **모든** 멤버와 짝 조건을 만족해야 한다.
        """
        ids = self.cluster([
            "Cloudflare Introduces Kitesurf Browser",   # A: Cloudflare, Kitesurf
            "Cloudflare open-sources Vibe platform",    # B: Cloudflare, Vibe  (A와 Cloudflare 공유)
            "Vibe coding takes over Replit workflows",  # C: Vibe, Replit      (B와 Vibe 공유)
        ])
        self.assertNotEqual(ids[0], ids[2], "A와 C가 B를 거쳐 잘못 묶였다(전이 병합)")

    def test_real_nine_way_chain_stays_apart(self):
        """2026-08-07 실측 회귀. 후보 119건에서 서로 무관한 9건이 한 덩어리가 됐고,
        선별 루프가 클러스터당 하나만 채택하므로 8건이 통째로 폐기됐다.
        후보를 늘릴수록 이 연쇄가 길어져 후보 확대의 발목을 잡던 지점이다."""
        titles = [
            "Meta enters the AI coding wars with Muse Spark 1.2 and Muse Code",
            "Cloudflare Introduces Kitesurf: An Agent-First Web Browser",
            "Adaptive Experimentation with Meta's Ax: A Practical Coding Guide",
            "Prime Intellect Releases Prime Agent: An Open-Source RLM Harness",
            "Microsoft's SkillOpt Shows Optimized Agent Skill Artifacts Transfer",
            "Meta AI Releases Muse Code (Beta): A Terminal Coding Agent",
            "NVIDIA Releases Alpamayo 2 Super: A 34B Open Vision-Language-Action Model",
            "CopilotKit Open Sources Channels SDK: An MIT Licensed Library",
            "Cloudflare open-sources vibe-coding platform for people who aren't coders",
        ]
        ids = self.cluster(titles)
        biggest = max(Counter(ids).values())
        self.assertLessEqual(
            biggest, 3,
            f"무관한 기사 {biggest}건이 한 사건으로 묶였다 — 그중 {biggest - 1}건이 폐기된다")

    def test_clustering_is_deterministic(self):
        """매일 무인으로 도는 단계라, 같은 입력에 결과가 흔들리면 원인 추적이 불가능하다."""
        titles = [
            "Anthropic launches Opus 5",
            "Anthropic releases Opus 5 with new capabilities",
            "Google DeepMind Releases AlphaFold 4",
            "Meta Open-Sources A New Speech Model",
        ]
        first = self.cluster(titles)
        for _ in range(5):
            self.assertEqual(self.cluster(titles), first)

    def test_every_candidate_gets_exactly_one_cluster(self):
        """선별 루프가 인덱스로 짝지어 쓰므로 길이가 어긋나면 조용히 엉뚱한 기사가 빠진다."""
        titles = ["Alpha One", "Beta Two", "Gamma Three", "Alpha One Again"]
        ids = self.cluster(titles)
        self.assertEqual(len(ids), len(titles))
        self.assertTrue(all(isinstance(i, int) for i in ids))

    def test_two_shared_keywords_still_merge(self):
        # 위 수정이 진짜 클러스터링까지 죽이면 안 된다. 제품명+버전이 함께 겹치면
        # 여러 매체가 같은 발표를 다룬 것이므로 계속 묶여야 한다.
        ids = self.cluster([
            "Moonshot releases Kimi K3 with 2.8T parameters",
            "Kimi K3 marks a big shift in open models",
            "Hands on with Kimi K3: what changed",
        ])
        self.assertEqual(len(set(ids)), 1, "같은 발표를 다룬 기사들이 갈라졌다")

    def test_single_rare_keyword_still_merges(self):
        # 후보 전체에서 딱 두 제목에만 등장하는 희귀 고유명사는 우연히 겹칠 일이
        # 거의 없으므로 하나만 겹쳐도 같은 사건으로 본다.
        ids = self.cluster([
            "Team uses AlphaFold to redesign gene-editing proteins",
            "AlphaFold helps scientists make CRISPR safer",
            "Nvidia announces new datacenter GPUs",
            "Apple ships on-device translation",
        ])
        self.assertEqual(ids[0], ids[1], "희귀 키워드를 공유하는 같은 사건이 갈라졌다")
        self.assertEqual(len({ids[0], ids[2], ids[3]}), 3)


class TestRankScore(unittest.TestCase):
    """랭킹 점수. 예전엔 cross_source_count가 단독 최상위 정렬 키여서, 아무도 안 쓴
    단독 심층 보도(교차 보도 0)가 무조건 꼴찌였다 — 실제로 MIT Technology Review와
    Wired가 5일간 한 건도 못 실렸다. 그 회귀를 막는 게 이 테스트의 핵심이다."""

    def setUp(self):
        self.now = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)
        self.cutoff = self.now - timedelta(days=1)

    def score(self, weight, cross, hours_old=0):
        published = self.now - timedelta(hours=hours_old)
        return compute_rank_score(
            {"source_weight": weight, "cross_source_count": cross, "published_at": published.isoformat()},
            self.cutoff,
            self.now,
        )

    def test_high_weight_exclusive_beats_low_weight_corroborated(self):
        # 이게 이번 변경의 존재 이유다: MIT Tech Review 단독 보도(가중치 4, 교차 0)가
        # HN에 올라온 교차 보도 2건짜리 글(가중치 1)보다 위여야 한다.
        self.assertGreater(self.score(4.0, 0), self.score(1.0, 2))

    def test_corroboration_still_helps_within_same_source(self):
        # 화제성을 무시하자는 게 아니다 — 같은 매체라면 여러 곳이 다룬 쪽이 위다.
        self.assertGreater(self.score(2.5, 3), self.score(2.5, 0))

    def test_corroboration_is_capped(self):
        # 상한이 없으면 "모두가 받아쓴 흔한 속보"가 점수를 무한정 벌어 독주한다.
        self.assertEqual(self.score(1.0, CROSS_SOURCE_CAP), self.score(1.0, CROSS_SOURCE_CAP + 10))

    def test_newer_wins_when_everything_else_is_equal(self):
        self.assertGreater(self.score(2.5, 1, hours_old=1), self.score(2.5, 1, hours_old=20))

    def test_missing_weight_falls_back_without_crashing(self):
        # feeds.json에 weight를 안 적은 피드가 있어도 수집이 멈추면 안 된다.
        published = self.now.isoformat()
        got = compute_rank_score({"cross_source_count": 0, "published_at": published}, self.cutoff, self.now)
        self.assertGreater(got, 0)

    def test_article_published_before_cutoff_does_not_go_negative(self):
        # 룩백 경계 밖 기사가 섞여 들어와도 점수가 음수로 뒤집히면 정렬이 무너진다.
        self.assertGreaterEqual(self.score(1.0, 0, hours_old=48), 1.0)


class TestPrimarySlots(unittest.TestCase):
    def test_primary_slot_guarantee_is_positive(self):
        # 0이면 공식 발표 보장 장치가 통째로 꺼진다. 발행량이 하루 0.3~0.4건뿐이라
        # 점수만으로는 발행량 많은 매체에 밀려 사라진다.
        self.assertGreater(PRIMARY_MIN_SLOTS, 0)


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


class TestFeedTimezone(unittest.TestCase):
    """AI타임스 피드는 '2026-07-29 17:26:28'처럼 타임존 없이 KST를 싣는다.
    feedparser가 그걸 UTC로 가정하므로 보정하지 않으면 발행 시각이 9시간 미래가 되고,
    그 매체가 신선도 점수를 늘 최대치로 받아 순위를 영구 독식한다."""

    def _entry(self, raw, struct):
        return {"published": raw, "published_parsed": struct}

    def test_naive_timestamp_is_read_as_declared_local_time(self):
        from fetch_articles import entry_published_at

        # 2026-07-29 17:26:28 KST == 08:26:28 UTC
        entry = self._entry("2026-07-29 17:26:28", (2026, 7, 29, 17, 26, 28, 0, 0, 0))
        got = entry_published_at(entry, "Asia/Seoul")
        self.assertEqual(got, datetime(2026, 7, 29, 8, 26, 28, tzinfo=timezone.utc))

    def test_naive_timestamp_does_not_land_in_the_future(self):
        # 이 회귀가 방치되면 조용히 랭킹만 망가진다 — 명시적으로 잡는다.
        from fetch_articles import entry_published_at

        entry = self._entry("2026-07-29 17:26:28", (2026, 7, 29, 17, 26, 28, 0, 0, 0))
        naive_utc = entry_published_at(entry)
        corrected = entry_published_at(entry, "Asia/Seoul")
        self.assertLess(corrected, naive_utc, "KST 보정 후에는 UTC 해석보다 이른 시각이어야 한다")

    def test_explicit_timezone_is_left_alone(self):
        from fetch_articles import entry_published_at

        entry = self._entry("Wed, 29 Jul 2026 00:09:05 +0000", (2026, 7, 29, 0, 9, 5, 2, 210, 0))
        self.assertEqual(
            entry_published_at(entry, "Asia/Seoul"),
            entry_published_at(entry),
            "타임존을 명시한 피드에 tz 보정이 잘못 적용됐다",
        )

    def test_unknown_timezone_name_does_not_crash(self):
        from fetch_articles import entry_published_at

        entry = self._entry("2026-07-29 17:26:28", (2026, 7, 29, 17, 26, 28, 0, 0, 0))
        self.assertIsNotNone(entry_published_at(entry, "Not/AZone"))


class TestArchiveIndex(unittest.TestCase):
    """홈은 최근 60일만 링크하므로, 이 목록이 없으면 오래된 날짜가 사람
    내비게이션에서 사라진다(sitemap에만 남으면 크롤러가 링크를 못 따라간다)."""

    def _build(self, dates):
        import json
        import tempfile
        from generate_site import build_archive_index

        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp)
            archive = docs / "archive"
            archive.mkdir()
            for d in dates:
                (archive / f"{d}.json").write_text(
                    json.dumps({
                        "date": d,
                        "daily_insight": {"headline_ko": f"{d} 헤드라인", "headline_en": f"{d} headline"},
                        "articles": [],
                    }),
                    encoding="utf-8",
                )
            (archive / "2026-07-01.sent.json").write_text('{"recipient_count": 1}', encoding="utf-8")
            total = build_archive_index(
                docs, archive, "https://x.test",
                {"google_site_verification": None, "naver_site_verification": None},
                "https://x.test/og.png", {"topics": 1, "terms": 2},
            )
            # 언어별로 한 언어만 담긴 페이지가 각각 나온다.
            return (total,
                    (archive / "index.html").read_text(encoding="utf-8"),
                    (docs / "en" / "archive" / "index.html").read_text(encoding="utf-8"))

    def test_groups_by_month_and_counts_all_days(self):
        total, ko, en = self._build(["2026-06-28", "2026-07-01", "2026-07-15"])
        self.assertEqual(total, 3)
        self.assertIn("2026년 7월", ko)
        self.assertIn("2026년 6월", ko)
        # 영어 월 이름은 locale에 의존하지 않아야 하고, 영어판에만 나와야 한다.
        self.assertIn("July 2026", en)
        self.assertNotIn("2026년 7월", en, "영어판에 한국어가 섞였다")

    def test_links_are_absolute_and_language_correct(self):
        """링크는 절대경로여야 한다.

        cleanUrls가 켜져 있으면 /archive 와 /archive/ 가 **둘 다 200으로 서빙되는데
        서로 리다이렉트하지 않는다**(2026-08-03 실측). 두 URL의 상대경로 기준이
        달라서 상대경로로는 양쪽을 동시에 맞출 수 없다 — 이 저장소에서 같은 계열
        사고가 세 번 났고(/topics 404, 영어판 언어 누수, /en 홈에서 한국어로 새는 것)
        전부 이 원인이었다."""
        _, ko, en = self._build(["2026-07-15"])
        self.assertIn('href="/archive/2026-07-15.html"', ko)
        self.assertIn('href="/site-base.css"', ko)
        # 자산은 사이트 루트 하나뿐이라 두 언어판이 같은 경로를 쓴다.
        self.assertIn('href="/site-base.css"', en)
        # 페이지 링크는 언어 루트부터 — 영어판이 한국어 트리로 새면 안 된다.
        self.assertIn('href="/en/archive/2026-07-15.html"', en)
        self.assertNotIn('href="/archive/2026-07-15.html"', en)

    def test_no_relative_links_remain(self):
        """상대경로가 하나라도 남으면 그 링크만 조용히 다른 곳을 가리킨다."""
        import re

        _, ko, en = self._build(["2026-07-15"])
        for label, html_text in (("ko", ko), ("en", en)):
            rel = [m for m in re.findall(r'(?:href|src)="([^"]+)"', html_text)
                   if not m.startswith(("http", "#", "mailto:", "/"))]
            self.assertEqual(rel, [], f"{label}판에 상대경로가 남아 있다: {rel}")

    def test_sent_markers_are_not_listed_as_days(self):
        total, _, _ = self._build(["2026-07-15"])
        self.assertEqual(total, 1)


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

    def test_값_없는_선택필드는_키째로_빠진다(self):
        """이 저장소의 제1 규칙 — 사이트를 재생성해도 영속 원본은 안 바뀌어야 한다.

        title_en을 추가하면서 값이 없을 때 null을 써 넣었더니, 그것만으로 과거
        아카이브 전체에 diff가 났다(2026-08-02). 매일 도는 파이프라인에서 이런
        변경은 '오늘 뭐가 바뀌었나'를 볼 수 없게 만들고, 최악의 경우 발송 마커
        주변 파일까지 함께 커밋되게 한다."""
        saved = self._save_and_load({
            "title": "Building abundant intelligence",
            "link": "https://openai.com/x", "source": "OpenAI News",
        })
        self.assertNotIn("title_en", saved,
                         "title_en이 없으면 키 자체가 없어야 한다 (null도 남기면 안 됨)")

    def test_title_en이_있으면_보존된다(self):
        saved = self._save_and_load({
            "title": "문샷, 알리바바서 GPU 공급받아",
            "title_en": "Moonshot secures GPUs from Alibaba",
            "link": "https://www.aitimes.com/x", "source": "AI타임스",
        })
        self.assertEqual(saved["title_en"], "Moonshot secures GPUs from Alibaba")

    def test_재저장해도_바이트가_같다(self):
        """같은 입력을 두 번 저장하면 완전히 동일해야 한다(멱등)."""
        import json
        import tempfile
        from generate_site import save_archive_json

        digest = {"date": "2026-07-26", "articles": [
            {"title": "A", "link": "https://a/", "source": "S"},
            {"title": "한국어 제목", "title_en": "Korean title",
             "link": "https://b/", "source": "AI타임스"},
        ]}
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp)
            save_archive_json(archive, digest)
            first = (archive / "2026-07-26.json").read_bytes()
            # 저장된 것을 다시 입력으로 넣어도 같아야 한다 — 실제 재생성 경로가 이것이다
            reloaded = json.loads(first.decode("utf-8"))
            save_archive_json(archive, reloaded)
            self.assertEqual(first, (archive / "2026-07-26.json").read_bytes())

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


class TestSearchIndexSync(unittest.TestCase):
    """검색 테이블로 올릴 행을 아카이브에서 뽑는 단계. 이게 틀리면 그날 기사가
    사이트 검색에 안 잡히는데, 사이트 자체는 멀쩡해 보여서 알아채기 어렵다."""

    def _collect(self, days, extra_files=None):
        import json
        import tempfile
        from sync_search_index import collect_rows

        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp)
            for date, articles in days:
                (archive / f"{date}.json").write_text(
                    json.dumps({"date": date, "articles": articles}), encoding="utf-8"
                )
            for name, body in (extra_files or {}).items():
                (archive / name).write_text(body, encoding="utf-8")
            return collect_rows(archive)

    def _article(self, link, title="T"):
        return {
            "link": link, "title": title, "source": "S",
            "summary_ko": "요약", "summary_en": "summary",
        }

    def test_collects_searchable_fields(self):
        rows = self._collect([("2026-07-27", [self._article("https://a")])])
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            set(rows[0]), {"link", "date", "title", "source", "summary_ko", "summary_en"}
        )
        self.assertEqual(rows[0]["date"], "2026-07-27")

    def test_same_link_on_two_days_is_deduped_to_latest(self):
        # link가 기본키라 중복이 남아 있으면 upsert가 같은 배치 안에서 충돌한다.
        rows = self._collect([
            ("2026-07-26", [self._article("https://a", "옛 제목")]),
            ("2026-07-27", [self._article("https://a", "새 제목")]),
        ])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "새 제목")

    def test_sent_markers_are_ignored(self):
        rows = self._collect(
            [("2026-07-27", [self._article("https://a")])],
            extra_files={"2026-07-27.sent.json": '{"recipient_count": 5}'},
        )
        self.assertEqual(len(rows), 1)

    def test_articles_without_link_or_title_are_skipped(self):
        rows = self._collect([("2026-07-27", [
            self._article("https://a"),
            {"link": "", "title": "링크없음"},
            {"link": "https://b", "title": "   "},
        ])])
        self.assertEqual([r["link"] for r in rows], ["https://a"])

    def test_missing_archive_dir_returns_empty(self):
        from sync_search_index import collect_rows

        self.assertEqual(collect_rows(Path("does-not-exist-xyz")), [])


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

class TestIndexNow(unittest.TestCase):
    """IndexNow는 매일 무인으로 도는 경로에 네트워크 호출을 하나 더 얹는 것이라,
    "실패해도 파이프라인이 멈추지 않는다"를 특히 확실히 해둬야 한다."""

    def test_키_파일은_키_문자열_자체를_담는다(self):
        # 프로토콜 규정 — 파일 내용이 키와 정확히 같아야 소유 증명이 된다.
        with tempfile.TemporaryDirectory() as d:
            docs = Path(d)
            key = seo_utils.write_indexnow_key_file(docs)
            self.assertIsNotNone(key, "config/indexnow.json에 키가 있어야 한다")
            self.assertEqual((docs / f"{key}.txt").read_text(encoding="utf-8"), key)

    def test_설정_파일이_없으면_비활성이고_예외도_안_난다(self):
        original = seo_utils.CONFIG_DIR
        try:
            with tempfile.TemporaryDirectory() as d:
                seo_utils.CONFIG_DIR = Path(d)  # 빈 디렉토리 = 설정 없음
                cfg = seo_utils.load_indexnow_config()
                self.assertFalse(cfg["enabled"])
                self.assertIsNone(cfg["key"])
                with tempfile.TemporaryDirectory() as d2:
                    self.assertIsNone(seo_utils.write_indexnow_key_file(Path(d2)))
                ok, msg = seo_utils.submit_indexnow("https://example.com", ["https://example.com/"])
                self.assertFalse(ok)
        finally:
            seo_utils.CONFIG_DIR = original

    def test_망이_끊겨도_예외를_던지지_않는다(self):
        # 무인 실행에서 통보 실패가 사이트 생성/발송을 막으면 안 된다.
        original = seo_utils.INDEXNOW_ENDPOINT
        try:
            # 실제로 존재하지 않는 호스트 — DNS 해석부터 실패한다.
            seo_utils.INDEXNOW_ENDPOINT = "https://indexnow.invalid-host-for-test.example/x"
            ok, msg = seo_utils.submit_indexnow(
                "https://www.dailyaithread.com", ["https://www.dailyaithread.com/"], timeout=3
            )
            self.assertFalse(ok)
            self.assertTrue(msg, "실패 원인이 메시지로 남아야 한다")
        finally:
            seo_utils.INDEXNOW_ENDPOINT = original

    def test_URL_목록이_비면_보내지_않는다(self):
        ok, msg = seo_utils.submit_indexnow("https://www.dailyaithread.com", [])
        self.assertFalse(ok)

    def test_통보_대상은_매일_바뀌는_페이지로_한정된다(self):
        # 과거 아카이브까지 매일 밀어 넣으면 엔진이 스팸으로 보고 무시하기 시작한다.
        import ping_indexnow

        urls = ping_indexnow.build_changed_urls("https://www.dailyaithread.com", "2026-07-30", None)
        self.assertIn("https://www.dailyaithread.com/archive/2026-07-30", urls)
        self.assertIn("https://www.dailyaithread.com/en/archive/2026-07-30", urls)
        self.assertIn("https://www.dailyaithread.com/", urls)
        self.assertIn("https://www.dailyaithread.com/en/", urls)
        # 어제 날짜는 안 바뀌므로 들어가면 안 된다
        self.assertNotIn("https://www.dailyaithread.com/archive/2026-07-29", urls)
        # 두 언어판이 짝을 이룬다
        self.assertEqual(len(urls), 10)

    def test_주간_회고를_만든_날은_그_페이지도_통보한다(self):
        import ping_indexnow

        urls = ping_indexnow.build_changed_urls(
            "https://www.dailyaithread.com", "2026-07-26", "2026-W30")
        self.assertIn("https://www.dailyaithread.com/weekly/2026-W30", urls)
        self.assertIn("https://www.dailyaithread.com/en/weekly/2026-W30", urls)
        self.assertEqual(len(urls), 12)

    def test_그날_용어_페이지도_양_언어로_통보한다(self):
        # 용어 페이지는 이 사이트 최고의 GEO 자산인데, sitemap만으로는 신규 도메인에서
        # 발견 자체가 안 된다는 걸 2026-07-31에 실측했다(6일 된 페이지가 not discovered).
        import ping_indexnow

        urls = ping_indexnow.build_changed_urls(
            "https://www.dailyaithread.com", "2026-07-31", None, ["ai-slop", "capex"])
        self.assertIn("https://www.dailyaithread.com/glossary/ai-slop", urls)
        self.assertIn("https://www.dailyaithread.com/en/glossary/ai-slop", urls)
        self.assertIn("https://www.dailyaithread.com/glossary/capex", urls)
        self.assertEqual(len(urls), 14)  # 기본 10 + 용어 2개 x 2언어

    def test_용어_슬러그는_그날_digest에서만_온다(self):
        # 누적 39개 전부를 매일 밀어 넣으면 엔진이 스팸으로 보고 무시하기 시작한다.
        import ping_indexnow

        with tempfile.TemporaryDirectory() as d:
            docs = Path(d)
            (docs / "archive").mkdir(parents=True)
            (docs / "archive" / "2026-07-31.json").write_text(json.dumps({
                "glossary": [
                    {"term_ko": "AI 슬롭", "term_en": "AI Slop"},
                    {"term_ko": "설비투자(캐펙스)", "term_en": "CapEx"},
                ]
            }, ensure_ascii=False), encoding="utf-8")
            # 다른 날짜 파일은 읽지 않아야 한다
            (docs / "archive" / "2026-07-30.json").write_text(json.dumps({
                "glossary": [{"term_ko": "다른날", "term_en": "Other Day"}]
            }, ensure_ascii=False), encoding="utf-8")

            slugs = ping_indexnow.collect_glossary_slugs(docs, "2026-07-31")
            self.assertEqual(slugs, ["ai-slop", "capex"])
            self.assertNotIn("other-day", slugs)

    def test_아카이브_파일이_없어도_통보는_계속된다(self):
        # 부가 정보 수집 실패가 통보 전체를 막으면 안 된다(무인 운영 원칙).
        import ping_indexnow

        with tempfile.TemporaryDirectory() as d:
            slugs = ping_indexnow.collect_glossary_slugs(Path(d), "2026-07-31")
            self.assertEqual(slugs, [])
            urls = ping_indexnow.build_changed_urls(
                "https://www.dailyaithread.com", "2026-07-31", None, slugs)
            self.assertEqual(len(urls), 10, "용어가 없어도 기본 10건은 그대로 나가야 한다")



class TestOgImagePerLanguage(unittest.TestCase):
    """/en/ 링크를 공유했을 때 미리보기 카드에 한국어 문장이 뜨던 문제(2026-07-30
    Reddit 게시로 발견)를 막는다. 런칭 채널에서 첫인상을 결정하는 부분이라 조용히
    되돌아가면 안 된다."""

    def test_언어별로_다른_파일명을_쓴다(self):
        self.assertEqual(seo_utils.og_image_name("2026-07-30", "ko"), "2026-07-30.png")
        self.assertEqual(seo_utils.og_image_name("2026-07-30", "en"), "2026-07-30-en.png")

    def test_한국어_경로는_바뀌지_않는다(self):
        # 이미 공유된 링크의 미리보기가 깨지면 안 된다.
        with tempfile.TemporaryDirectory() as d:
            url = seo_utils.build_og_image_url(
                "https://example.com", Path(d), "2026-07-30", "오늘의 헤드라인", "ko")
            self.assertTrue(url.endswith("/og/2026-07-30.png"), url)

    def test_영어_헤드라인이_비면_한국어_이미지로_대체하지_않는다(self):
        # 틀린 언어를 보여주느니 중립적인 브랜드 카드가 낫다.
        with tempfile.TemporaryDirectory() as d:
            url = seo_utils.build_og_image_url(
                "https://example.com", Path(d), "2026-07-30", "", "en")
            self.assertEqual(url, "https://example.com/og-image.png")

    def test_두_언어가_서로_다른_이미지를_만든다(self):
        with tempfile.TemporaryDirectory() as d:
            docs = Path(d)
            ko = seo_utils.build_og_image_url(
                "https://example.com", docs, "2026-07-30", "한국어 헤드라인입니다", "ko")
            en = seo_utils.build_og_image_url(
                "https://example.com", docs, "2026-07-30", "An English headline here", "en")
            self.assertNotEqual(ko, en)
            # Pillow가 있으면 실제 파일이 두 개 생기고, 없으면 둘 다 폴백이라 같아진다.
            if "og-image.png" not in ko:
                files = sorted(f.name for f in (docs / "og").glob("*.png"))
                self.assertEqual(files, ["2026-07-30-en.png", "2026-07-30.png"])
                self.assertNotEqual(
                    (docs / "og" / "2026-07-30.png").read_bytes(),
                    (docs / "og" / "2026-07-30-en.png").read_bytes(),
                    "두 언어 카드의 내용이 같으면 언어별 렌더링이 안 된 것이다",
                )


class TestDisplayTitle(unittest.TestCase):
    """영어판에 한국어 제목이 그대로 노출되던 문제(2026-08-02, AI타임스 기사가
    allowlist 수정 후 처음 선정되면서 드러남)를 막는다."""

    def test_영어판은_title_en을_쓴다(self):
        a = {"title": "문샷, 알리바바서 엔비디아 GPU 2만개 공급받아",
             "title_en": "Moonshot secures 20,000 Nvidia GPUs from Alibaba"}
        self.assertEqual(seo_utils.display_title(a, "en"),
                         "Moonshot secures 20,000 Nvidia GPUs from Alibaba")

    def test_한국어판은_언제나_원제를_쓴다(self):
        # 한국어판은 영어 기사도 영어 원제 그대로 — 출처 표기로 정직한 쪽을 택했다.
        a = {"title": "Judge denies xAI's request", "title_en": "Judge denies xAI's request"}
        self.assertEqual(seo_utils.display_title(a, "ko"), "Judge denies xAI's request")
        b = {"title": "문샷, 알리바바서 GPU 공급받아", "title_en": "Moonshot secures GPUs"}
        self.assertEqual(seo_utils.display_title(b, "ko"), "문샷, 알리바바서 GPU 공급받아")

    def test_title_en이_없으면_원제로_떨어진다(self):
        # 영어 원제 기사에는 아예 없고, 과거 아카이브에도 없다. 없다고 빈 제목이
        # 나가면 그 기사만 화면에서 사라진다.
        a = {"title": "Building abundant intelligence"}
        self.assertEqual(seo_utils.display_title(a, "en"), "Building abundant intelligence")
        self.assertEqual(seo_utils.display_title(a, "ko"), "Building abundant intelligence")

    def test_title_en이_빈_문자열이어도_원제로_떨어진다(self):
        a = {"title": "Building abundant intelligence", "title_en": "   "}
        self.assertEqual(seo_utils.display_title(a, "en"), "Building abundant intelligence")


class TestGlossarySeenDates(unittest.TestCase):
    """용어 페이지는 검색 유입의 주력 착지점인데, 예전에는 '처음 등장'과 '가장 최근
    등장' 두 줄이 47개 중 41개에서 같은 날짜였다(2026-08-02 점검). 등장 날짜를 전부
    모아 브리핑으로 가는 길을 늘린다."""

    def _archive(self, tmp, days):
        import json
        archive = Path(tmp)
        for date, terms in days.items():
            (archive / f"{date}.json").write_text(
                json.dumps({"date": date, "glossary": terms}, ensure_ascii=False),
                encoding="utf-8")
        return archive

    def test_등장한_날짜를_모두_모은다(self):
        from generate_site import collect_glossary_terms

        with tempfile.TemporaryDirectory() as tmp:
            archive = self._archive(tmp, {
                "2026-07-25": [{"term_ko": "샌드박스", "term_en": "Sandbox"}],
                "2026-07-26": [{"term_ko": "샌드박스", "term_en": "Sandbox"}],
                "2026-08-01": [{"term_ko": "샌드박스", "term_en": "Sandbox"}],
            })
            term = collect_glossary_terms(archive)[0]
            self.assertEqual(term["seen_dates"], ["2026-07-25", "2026-07-26", "2026-08-01"])
            self.assertEqual(term["first_seen"], "2026-07-25")
            self.assertEqual(term["last_seen"], "2026-08-01")

    def test_한_번만_나온_용어는_날짜가_하나다(self):
        from generate_site import collect_glossary_terms

        with tempfile.TemporaryDirectory() as tmp:
            archive = self._archive(tmp, {
                "2026-07-31": [{"term_ko": "AI 슬롭", "term_en": "AI Slop"}]})
            term = collect_glossary_terms(archive)[0]
            self.assertEqual(term["seen_dates"], ["2026-07-31"])

    def test_슬러그로_합칠_때_날짜도_합쳐진다(self):
        # 표기만 다른 같은 개념("정렬" / "정렬(얼라인먼트)")을 합치면서 밀려난 쪽의
        # 날짜를 버리면 브리핑 링크가 실제보다 적어진다.
        from generate_site import collect_glossary_terms, group_glossary_by_slug

        with tempfile.TemporaryDirectory() as tmp:
            archive = self._archive(tmp, {
                "2026-07-24": [{"term_ko": "정렬", "term_en": "Alignment"}],
                "2026-07-28": [{"term_ko": "정렬(얼라인먼트)", "term_en": "Alignment"}],
            })
            merged = group_glossary_by_slug(collect_glossary_terms(archive))
            self.assertEqual(len(merged), 1, "같은 term_en이면 한 페이지로 합쳐져야 한다")
            self.assertEqual(merged[0]["seen_dates"], ["2026-07-24", "2026-07-28"])
            self.assertEqual(merged[0]["first_seen"], "2026-07-24")
            self.assertEqual(merged[0]["last_seen"], "2026-07-28")

    def test_같은_날_중복_등록은_한_번만_센다(self):
        from generate_site import collect_glossary_terms

        with tempfile.TemporaryDirectory() as tmp:
            archive = self._archive(tmp, {"2026-07-31": [
                {"term_ko": "LLM", "term_en": "LLM"},
                {"term_ko": "LLM", "term_en": "LLM"},
            ]})
            self.assertEqual(collect_glossary_terms(archive)[0]["seen_dates"], ["2026-07-31"])


class TestUnbrokenStreak(unittest.TestCase):
    """홈의 "하루도 빠짐없이"(every day since)는 `days` 숫자와 **다른 주장**이다.
    days는 발행한 날 수라 하루 걸러도 안 늘 뿐이지만, 저 문구는 결번이 없다고
    단언한다. 둘을 묶어두면 하루 거른 뒤에도 문구가 그대로 나가 거짓말이 된다.
    마케팅 카피가 이 숫자를 인용하므로 특히 조용히 틀리면 안 된다(2026-08-04)."""

    def _stats(self, dates):
        from generate_site import collect_site_stats

        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp)
            for d in dates:
                (archive / f"{d}.json").write_text(
                    json.dumps({"date": d, "articles": []}), encoding="utf-8")
            return collect_site_stats(archive, glossary_count=0)

    def test_연속이면_참(self):
        s = self._stats(["2026-07-23", "2026-07-24", "2026-07-25"])
        self.assertTrue(s["unbroken"])
        self.assertEqual(s["days"], 3)
        self.assertEqual(s["since"], "2026-07-23")

    def test_하루라도_비면_거짓(self):
        # 7/24가 빠졌다 — days는 3이지만 시작~끝은 4일이다.
        s = self._stats(["2026-07-23", "2026-07-25", "2026-07-26"])
        self.assertFalse(s["unbroken"])
        self.assertEqual(s["days"], 3, "days는 발행한 날 수 그대로여야 한다")

    def test_하루뿐이어도_참(self):
        self.assertTrue(self._stats(["2026-07-23"])["unbroken"])

    def test_아카이브가_비면_거짓(self):
        s = self._stats([])
        self.assertFalse(s["unbroken"])
        self.assertIsNone(s["since"])

    def test_날짜를_못_읽으면_주장하지_않는다(self):
        # 확인할 수 없을 때는 주장하지 않는 쪽이 맞다. 무인 실행이라 예외로 죽어서도
        # 안 된다 — 파일명이 이상해도 사이트 생성은 끝나야 한다.
        from generate_site import _is_unbroken_streak

        self.assertFalse(_is_unbroken_streak(["not-a-date", "2026-07-24"]))
class TestGlossarySlugAliases(unittest.TestCase):
    """같은 개념이 표기 차이로 여러 URL에 흩어지는 것을 막는 별칭 맵.

    실제로 오픈웨이트가 open-weight / open-weights / open-weight-model /
    open-weight-models 4개 URL로 갈라졌고, 용어사전이 링크하지 않는 2개는 sitemap에만
    살아남아 구글이 낡은 페이지를 보고 있었다."""

    def test_alias_collapses_variants(self):
        from generate_site import glossary_slug
        aliases = {"open-weight": "open-weight-model", "open-weights": "open-weight-model",
                   "open-weight-models": "open-weight-model"}
        for term_en in ("open weight", "Open Weights", "open-weight models", "open weight model"):
            self.assertEqual(glossary_slug(term_en, "", aliases), "open-weight-model", term_en)

    def test_no_alias_map_keeps_old_behavior(self):
        """맵이 비어 있으면 예전과 똑같이 동작해야 한다(설정 파일이 없어도 생성은 돈다)."""
        from generate_site import glossary_slug
        self.assertEqual(glossary_slug("open weights"), "open-weights")

    def test_group_merges_aliased_terms_into_one_page(self):
        from generate_site import group_glossary_by_slug
        terms = [
            {"term_ko": "오픈웨이트", "term_en": "open weights",
             "definition_ko": "옛 설명", "seen_dates": ["2026-07-25"], "last_seen": "2026-07-25"},
            {"term_ko": "오픈웨이트 모델", "term_en": "open-weight models",
             "definition_ko": "새 설명", "seen_dates": ["2026-08-06"], "last_seen": "2026-08-06"},
        ]
        merged = group_glossary_by_slug(terms, {"open-weights": "open-weight-model",
                                                "open-weight-models": "open-weight-model"})
        self.assertEqual(len(merged), 1)
        entry = merged[0]
        self.assertEqual(entry["slug"], "open-weight-model")
        self.assertEqual(entry["definition_ko"], "새 설명")  # 최근 것이 대표
        self.assertIn("오픈웨이트", entry["aliases_ko"])     # 밀려난 표기는 별칭으로 보존
        # 등장 날짜는 합쳐야 "이 용어가 나온 브리핑"이 실제보다 적어 보이지 않는다.
        self.assertEqual(entry["seen_dates"], ["2026-07-25", "2026-08-06"])

    def test_retired_slugs_have_redirects(self):
        """별칭에 넣어 은퇴시킨 슬러그는 vercel.json에 301이 있어야 한다.

        그냥 지우면 이미 색인된 URL이 404가 된다. 별칭만 추가하고 리다이렉트를 잊는
        것이 정확히 그 사고이므로, 설정 두 개가 어긋나면 여기서 잡는다."""
        import json
        root = Path(__file__).resolve().parent.parent
        aliases = json.loads((root / "config" / "glossary_aliases.json").read_text(encoding="utf-8"))["aliases"]
        redirects = json.loads((root / "vercel.json").read_text(encoding="utf-8")).get("redirects", [])
        pairs = {(r["source"], r["destination"]) for r in redirects if r.get("permanent")}
        for old_slug, new_slug in aliases.items():
            for prefix in ("", "/en"):
                self.assertIn((f"{prefix}/glossary/{old_slug}", f"{prefix}/glossary/{new_slug}"), pairs,
                              f"{prefix}/glossary/{old_slug} 301 누락")


class TestPruneStaleGlossaryPages(unittest.TestCase):
    def test_removes_only_unlisted_glossary_pages(self):
        from generate_site import prune_stale_glossary_pages
        with tempfile.TemporaryDirectory() as d:
            docs = Path(d)
            for sub in ("glossary", "en/glossary", "archive"):
                (docs / sub).mkdir(parents=True)
            (docs / "glossary" / "open-weight-model.html").write_text("keep", encoding="utf-8")
            (docs / "glossary" / "open-weights.html").write_text("stale", encoding="utf-8")
            (docs / "en" / "glossary" / "open-weights.html").write_text("stale", encoding="utf-8")
            (docs / "archive" / "2026-08-07.html").write_text("건드리면 안 됨", encoding="utf-8")
            (docs / "glossary.html").write_text("인덱스", encoding="utf-8")

            removed = prune_stale_glossary_pages(docs, {"open-weight-model"})

            self.assertEqual(len(removed), 2, removed)
            self.assertTrue((docs / "glossary" / "open-weight-model.html").exists())
            self.assertFalse((docs / "glossary" / "open-weights.html").exists())
            self.assertFalse((docs / "en" / "glossary" / "open-weights.html").exists())
            # 용어 디렉터리 밖은 절대 건드리지 않는다.
            self.assertTrue((docs / "archive" / "2026-08-07.html").exists())
            self.assertTrue((docs / "glossary.html").exists())


class TestSitemapExcludesRetiredGlossary(unittest.TestCase):
    def test_sitemap_skips_files_not_in_index(self):
        """정리가 실패해 파일이 남아도 sitemap에는 새어 나가지 않아야 한다(이중 방어).

        예전에는 sitemap이 docs/glossary/*.html을 통째로 훑어서, 인덱스가 링크하지 않는
        낡은 파일이 검색엔진에만 계속 제출됐다."""
        import seo_utils
        with tempfile.TemporaryDirectory() as d:
            docs = Path(d)
            (docs / "glossary").mkdir(parents=True)
            (docs / "glossary.html").write_text("인덱스", encoding="utf-8")
            (docs / "glossary" / "open-weight-model.html").write_text("x", encoding="utf-8")
            (docs / "glossary" / "open-weights.html").write_text("x", encoding="utf-8")

            seo_utils.build_sitemap(docs, "https://example.com", "2026-08-07", {"open-weight-model"})
            xml = (docs / "sitemap.xml").read_text(encoding="utf-8")
            self.assertIn("https://example.com/glossary/open-weight-model<", xml)
            self.assertNotIn("open-weights", xml)

            # 슬러그를 안 넘기면 예전 동작(전량 포함) — 주간 빌드는 용어 목록을 모른다.
            seo_utils.build_sitemap(docs, "https://example.com", "2026-08-07")
            self.assertIn("open-weights", (docs / "sitemap.xml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
