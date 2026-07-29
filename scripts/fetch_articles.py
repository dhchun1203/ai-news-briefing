#!/usr/bin/env python3
"""config/feeds.json의 RSS 피드를 순회해 최근 기사 중 상위 N개를 골라 JSON으로 저장한다."""
import argparse
import json
import re
import socket
import sys
from calendar import timegm
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import feedparser

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FEEDS_PATH = ROOT / "config" / "feeds.json"
DEFAULT_DATA_DIR = ROOT / "data"
KST = ZoneInfo("Asia/Seoul")
DEFAULT_DOCS_DIR = ROOT / "docs"

# 한 출처가 상위 목록을 독점하지 않도록 출처당 최대 채택 개수를 둔다.
MAX_PER_SOURCE = 3

# 원문을 읽을 수 없거나(봇 차단·페이월) 브리핑에 실을 가치가 없는 기사가 나왔을 때
# 갈아끼울 예비 후보 개수. 하루 10건 중 3건까지 교체가 필요했던 날이 있어 여유를 둔다.
RESERVE_COUNT = 5

# 기사 하나에 붙일 "같은 사건을 다룬 다른 매체" 링크 수 상한. 카드 하단 한 줄에
# 들어가야 읽는 흐름을 끊지 않는다.
RELATED_MAX = 4

# ---- 랭킹 점수 구성 ----
# 예전에는 cross_source_count(몇 개 매체가 같은 사건을 다뤘나)가 단독 최상위 정렬
# 키였다. 그러면 "여러 곳이 받아쓴 흔한 속보"가 항상 이기고, 아무도 안 쓴 단독
# 심층 보도는 교차 보도 수가 0이라 무조건 꼴찌가 된다 — 2026-07-27에 5일치를
# 점검했더니 MIT Technology Review와 Wired가 한 건도 못 실린 이유가 정확히 이것이었다.
# 화제성은 여러 신호 중 하나여야지 절대 우선순위가 되면 안 되므로, 출처 가중치·교차
# 보도·신선도를 합산한 점수로 정렬한다.
CROSS_SOURCE_POINT = 1.0  # 교차 보도 1건당 가점
CROSS_SOURCE_CAP = 3  # 그 이상 다뤄져도 더 쳐주지 않는다(흔한 속보의 무한 독주 방지)
RECENCY_POINT = 1.0  # 룩백 창에서 가장 최신이면 이만큼, 창 끝이면 0
DEFAULT_SOURCE_WEIGHT = 1.0  # feeds.json에 weight가 없는 피드의 기본값

# 공식 발표(type: primary)에 최소한 보장하는 자리 수. 1차 출처는 그것을 받아쓴
# 기사보다 항상 낫고 발행량도 적어서(하루 0.3~0.4건), 점수만으로 겨루게 두면
# 발행량 많은 매체에 밀려 사라진다. 있으면 우선 채우고, 없으면 그냥 넘어간다.
PRIMARY_MIN_SLOTS = 2


def compute_rank_score(article: dict, cutoff, now) -> float:
    """후보 하나의 랭킹 점수. 값이 클수록 우선 채택된다.

    세 항목의 합이다:
      - 출처 가중치: 발행량과 무관하게 그 매체 기사 한 건의 기본 가치
      - 교차 보도: 여러 매체가 동시에 다룰수록 화제성이 높다(상한 있음)
      - 신선도: 같은 조건이면 최신 기사를 앞에 둔다
    """
    published = datetime.fromisoformat(article["published_at"])
    window = (now - cutoff).total_seconds()
    # 룩백 창 안에서의 위치를 0~1로 정규화한다(1=방금, 0=창 끝).
    recency = 1.0 if window <= 0 else max(0.0, min(1.0, (published - cutoff).total_seconds() / window))
    return (
        article.get("source_weight", DEFAULT_SOURCE_WEIGHT)
        + CROSS_SOURCE_POINT * min(article["cross_source_count"], CROSS_SOURCE_CAP)
        + RECENCY_POINT * recency
    )

# 피드 하나가 응답하지 않을 때 전체 실행이 멈추지 않도록 거는 소켓 타임아웃(초).
FEED_TIMEOUT_SEC = 20
# Cloudflare 뒤에 있는 매체들이 기본 urllib UA를 봇으로 보고 403으로 막는 일이 있다.
USER_AGENT = "ai-news-briefing-bot/1.0 (+https://www.dailyaithread.com)"

# "죽은 피드"(발행이 사실상 멈춘 매체) 판단 기준은 후보 선정용 --lookback-days와
# 별개로 고정한다. lookback-days를 신선도 때문에 짧게(1~2일) 줄이면, 발행 주기가
# 원래 느린 정상 피드(예: 격일 발행)까지 매번 "죽었다"고 오탐하게 되기 때문이다 —
# 이 값은 "그 매체가 정말 발행을 멈췄는지"만 넉넉하게 판단하는 별도 기준이다.
STALE_FEED_THRESHOLD_DAYS = 14

# 제목에서 고유명사/버전명을 추정하기 위해 제외할 흔한 대문자 시작 단어들
# (문장 맨 앞 단어나 흔한 관사·부사라 "화제성 키워드"로 보기엔 너무 일반적인 것들).
TITLE_STOPWORDS = {
    "The", "This", "That", "With", "From", "After", "Says", "New", "How",
    "Why", "What", "Its", "For", "And", "But", "Are", "Is", "Was", "Will",
    "AI", "Show", "Ask", "Meet", "You", "Your", "Watch", "Inside", "Explore",
    # 발표 기사 제목에 관용적으로 붙는 동사·틀. 사건을 특정하지 못하는데 대문자로
    # 시작해 키워드로 잡힌다 — "Introducing OpenAI Presence"와 "Introducing Gemini
    # 3.6 Flash"가 "Introducing" 하나로 같은 사건이 되는 실제 오병합이 있었다.
    "Introducing", "Launches", "Launch", "Announces", "Announcing", "Releases",
    "Release", "Unveils", "Debuts", "Brings", "Adds", "Reveals", "Rolls",
    "Expands", "Makes", "Gets", "Update", "Updates", "Here", "Now", "Report",
    "Reports", "Says", "Introduces",
}


def parse_args(argv=None):
    """argv=None이면 argparse가 평소처럼 sys.argv를 읽는다 — 테스트에서 실제 CLI
    인자 없이 기본값(예: --lookback-days 기본이 1인지)을 확인할 수 있도록 명시적
    argv를 받는 통로만 열어둔다."""
    p = argparse.ArgumentParser(description="RSS 피드에서 최근 AI 기사를 수집한다.")
    p.add_argument("--feeds", default=str(DEFAULT_FEEDS_PATH), help="feeds.json 경로")
    p.add_argument("--lookback-days", type=int, default=1, help="최근 며칠 이내 기사만 대상으로 할지")
    p.add_argument("--top-n", type=int, default=10, help="최종 선별할 기사 개수")
    p.add_argument("--max-per-source", type=int, default=MAX_PER_SOURCE, help="출처당 최대 채택 개수")
    p.add_argument(
        "--reserve-count",
        type=int,
        default=RESERVE_COUNT,
        help="원문을 못 읽거나 실을 가치가 없는 기사를 교체할 때 쓸 예비 후보 개수",
    )
    p.add_argument("--output", default=None, help="출력 파일 경로 (기본: data/articles_<오늘날짜>.json)")
    p.add_argument(
        "--docs-dir",
        default=str(DEFAULT_DOCS_DIR),
        help="과거 브리핑 기록(docs/archive/*.json)이 있는 디렉토리 — 중복 기사 제외에 사용",
    )
    return p.parse_args(argv)


def load_published_links(docs_dir: Path) -> set:
    """과거에 이미 브리핑에 실렸던 기사 링크 전체를 docs/archive/*.json에서 모은다.
    generate_site.py가 매 실행마다 그날의 원본 digest를 이 경로에 영구 보관해두므로,
    여기 있는 링크는 이미 다른 날짜에 다뤄졌다는 뜻이라 다시 후보로 뽑지 않는다."""
    archive_dir = docs_dir / "archive"
    links = set()
    if not archive_dir.exists():
        return links
    for f in archive_dir.glob("*.json"):
        if f.name.endswith(".sent.json"):
            continue  # 발송 완료 마커(send_broadcast.py) — 기사 원본이 아니다
        try:
            day = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for a in day.get("articles", []):
            link = a.get("link")
            if link:
                links.add(link.strip())
    return links


def extract_keywords(title: str) -> set:
    """제목에서 대문자로 시작하는 고유명사 추정 단어(2글자 이상)와 4자리 이상 숫자
    (버전·연도 등)를 뽑는다. 여러 후보 기사가 같은 키워드를 공유하면 같은 사건을
    서로 다른 매체가 동시에 다루고 있다는 신호로 쓴다."""
    words = re.findall(r"[A-Z][A-Za-z0-9\-]{2,}|\d{4,}", title)
    return {w for w in words if w not in TITLE_STOPWORDS}


# Hacker News의 관용 접두사. "Show HN"은 만든 사람이 직접 올리는 자기 제품 홍보,
# "Ask HN"/"Tell HN"은 링크 없는 토론 글, "Launch HN"은 YC 스타트업 런칭 공지다.
# 셋 다 "그날 무슨 일이 있었는지"를 다루는 뉴스 브리핑에 실을 성격이 아니고, 특히
# Show HN은 원문이 제품 랜딩페이지라 요약할 기사 본문 자체가 없는 경우가 많다.
# 피드 URL의 points 필터로도 대부분 걸러지지만(hnrss가 간헐적으로 불안정해 그것만
# 믿을 수 없다), 여기서 한 번 더 막아 어느 쪽이 실패해도 방어되게 한다.
SELF_PROMO_PREFIXES = ("show hn:", "ask hn:", "tell hn:", "launch hn:")


def is_self_promo_post(title: str) -> bool:
    return title.strip().lower().startswith(SELF_PROMO_PREFIXES)


def compute_cross_source_counts(candidates: list) -> None:
    """후보들의 제목 키워드를 모아, 키워드별로 등장한 서로 다른 출처 집합을 구한 뒤
    각 후보에 '이 기사와 같은 사건을 다루는 것으로 보이는 다른 출처 수'를 매긴다.
    같은 출처가 같은 키워드를 여러 번 언급하는 건 교차 확인이 아니므로 세지 않는다.
    각 후보 dict에 `_cross_source_count`를 직접 채워 넣는다(in-place)."""
    keyword_sources = {}
    for c in candidates:
        for kw in extract_keywords(c["title"]):
            keyword_sources.setdefault(kw, set()).add(c["source"])

    for c in candidates:
        sources = set()
        for kw in extract_keywords(c["title"]):
            sources |= keyword_sources.get(kw, set())
        sources.discard(c["source"])
        c["_cross_source_count"] = len(sources)


SAME_STORY_MAX_DOC_FREQ = 6  # 이보다 많은 서로 다른 제목에 등장하면 "흔한 키워드"로 본다

# 클러스터링에서 "이것만 겹치는 건 같은 사건이라는 근거가 못 된다"고 보는 이름들 —
# 회사·기관명과, 그 아래 수많은 무관한 소식이 달리는 **우산 브랜드**다.
#
# 회사는 하루에도 서로 무관한 일을 여러 건 만든다("구글이 데이터센터 계약을 했다"와
# "구글 검색 점유율 데이터가 나왔다"는 같은 사건이 아니다). 우산 브랜드도 똑같이
# 행동한다 — "ChatGPT 음성 모드"와 "ChatGPT 헬스"와 "ChatGPT 취약점"은 전부 다른
# 사건인데 실제로 한 묶음이 됐다. 반면 제품 세부명·모델·버전("GPT-6", "Opus",
# "Flash", "AlphaFold")은 그 자체가 특정 사건을 가리킨다.
#
# 문서빈도 임계값으로는 이 둘을 못 가른다 — 후보 44건에서 "Google"이 5개 제목,
# 5개 매체가 다룬 진짜 대형 발표의 제품명도 5개 제목이라 수치가 같다. 그래서
# 명시적 목록으로 구분한다.
CLUSTER_STOP_ENTITIES = {
    # 회사·기관
    "Google", "Alphabet", "DeepMind", "OpenAI", "Anthropic", "Meta", "Microsoft",
    "Nvidia", "Apple", "Amazon", "Tesla", "IBM", "Intel", "AMD", "Samsung",
    "Qualcomm", "Oracle", "Salesforce", "Adobe", "Reddit", "TikTok", "ByteDance",
    "Baidu", "Alibaba", "Tencent", "Moonshot", "Mistral", "Cohere", "Perplexity",
    "Stability", "Hugging", "HuggingFace", "Databricks", "Snowflake", "Figma",
    # 우산 브랜드 (하위 제품·사건이 계속 갈라져 나오는 이름)
    "ChatGPT", "Gemini", "Claude", "Copilot", "Llama", "Alexa", "Siri", "Bard",
}


def build_same_story_clusters(candidates: list) -> list:
    """제목 키워드가 겹치는 후보들을 "같은 사건"으로 묶는다(union-find).

    후보 전체에서 각 키워드가 몇 개의 서로 다른 제목에 등장하는지(document frequency)를
    센 뒤, 흔한 키워드(`SAME_STORY_MAX_DOC_FREQ`개 초과 제목에 등장)는 "사건을 특정하지
    못하는 일반 명사"로 보고 매칭에서 제외한다.

    남은 키워드가 겹칠 때 **무엇이 겹쳤는지**가 이 함수의 핵심이다. 예전에는 무엇이든
    하나만 겹쳐도 묶었는데, 그러면 회사명 하나로 완전히 무관한 기사들이 통째로
    합쳐진다. 2026-07-29에 실측한 실제 사례(후보 44건):

        Google AI Blog    5 ways to host the ultimate dinner party with Google Search
        Ars Technica AI   Despite AI hype, Google's data shows workers aren't automating…
        Ars Technica AI   "Google and Reddit do not own the Internet," web scraper says
        Ars Technica AI   Verizon touts $1B dark fiber deal for Google data centers
        TechCrunch AI     Google's AI search is rapidly becoming the default, new data…

    다섯 건이 공유하는 키워드는 "Google" 하나뿐인데 같은 사건으로 묶였고, 선별 루프가
    클러스터당 하나만 채택하므로 **나머지 네 건이 중복으로 폐기됐다.**

    흔한 키워드 임계값(6)을 조정하는 방식으로는 못 고친다 — 다섯 매체가 다룬 진짜
    대형 발표도 제품명이 다섯 제목에 등장하므로 수치가 같다. "몇 개가 겹쳤나"로도
    못 가른다 — 제품명이 하나만 겹치는 정상 클러스터가 흔하다("GPT-6"만 공유하는
    세 건은 같은 사건이 맞다).

    그래서 **회사명은 병합 근거에서 뺀다**(`CLUSTER_STOP_ENTITIES`). 회사는 하루에도
    무관한 일을 여러 건 만들지만, 제품·모델·버전명은 그 자체로 사건을 특정한다.
    회사명만 겹치는 경우에도 서로 다른 회사가 둘 이상 함께 겹치면 같은 사건일
    가능성이 높아 그때만 예외로 병합한다.

    이 변경으로 "회사명만 공유하는 진짜 같은 사건"(예: 제목에 금액·제품명이 없는
    투자 유치 기사 두 건)은 갈라질 수 있다. 그쪽이 안전한 실패다 — 잘못 묶으면
    정상 기사가 폐기되지만, 갈라지면 비슷한 기사 두 건이 실릴 뿐이고 화제성은
    `compute_cross_source_counts`가 따로 잡아 순위로 반영한다.

    `compute_cross_source_counts`(순위 매기기용, 느슨한 기준)와는 다른 용도라 별도
    함수로 둔다 — 이건 "최종 선택에서 하나만 남길지" 판단에 쓰인다."""
    n = len(candidates)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    keyword_sets = [extract_keywords(c["title"]) for c in candidates]
    doc_freq = {}
    for kws in keyword_sets:
        for kw in kws:
            doc_freq[kw] = doc_freq.get(kw, 0) + 1
    specific_sets = [{kw for kw in kws if doc_freq[kw] <= SAME_STORY_MAX_DOC_FREQ} for kws in keyword_sets]

    for i in range(n):
        if not specific_sets[i]:
            continue
        for j in range(i + 1, n):
            shared = specific_sets[i] & specific_sets[j]
            if not shared:
                continue
            # 제품·모델·버전명이 하나라도 겹치면 같은 사건으로 본다. 회사·브랜드명만
            # 겹치는 건 근거가 못 된다 — 개수를 세는 것도 소용없다. "OpenAI"와
            # "ChatGPT"처럼 한 회사의 이름 쌍은 늘 함께 등장해서, 둘 다 겹쳤다고
            # 병합하면 무관한 ChatGPT 기사들이 union-find 전이로 줄줄이 엮인다
            # (실제로 음성 모드 기사가 헬스 기사 묶음에 딸려 들어갔다).
            if shared - CLUSTER_STOP_ENTITIES:
                union(i, j)

    return [find(i) for i in range(n)]


def entry_published_at(entry, tz_name=None):
    """피드 항목의 발행 시각을 UTC로 돌려준다.

    feedparser는 타임존 표기가 없는 `pubDate`(예: `2026-07-29 17:26:28`)를 **UTC로
    가정해** 파싱한다. 그런데 국내 매체는 타임존 없이 KST를 그대로 싣는 경우가 있어,
    그대로 두면 발행 시각이 9시간 미래로 잡힌다. 그러면 (1) 룩백 컷오프를 항상
    통과하고 (2) 신선도 점수가 늘 최대치가 되어 그 매체가 순위를 영구 독식하며
    (3) `feeds_stale` 감지가 영원히 작동하지 않는다.

    그래서 `config/feeds.json`에 `tz`가 지정된 피드는, 타임존이 없는 타임스탬프에
    한해 그 지역시로 해석한다. 타임존을 제대로 주는 피드는 `*_parsed`에 이미 UTC로
    정규화돼 들어오므로 이 보정이 적용되지 않는다."""
    for key in ("published_parsed", "updated_parsed"):
        struct = entry.get(key)
        if not struct:
            continue
        as_utc = datetime.fromtimestamp(timegm(struct), tz=timezone.utc)
        if tz_name and not _entry_has_explicit_tz(entry, key):
            try:
                local = as_utc.replace(tzinfo=ZoneInfo(tz_name))
            except Exception:
                return as_utc  # 알 수 없는 타임존 이름이면 보정을 포기하고 원본을 쓴다
            return local.astimezone(timezone.utc)
        return as_utc
    return None


def _entry_has_explicit_tz(entry, parsed_key):
    """원본 날짜 문자열에 타임존 표기가 있었는지 본다. feedparser는 파싱 결과에서
    그 정보를 지워버리므로, 대응하는 원문 필드(`published`/`updated`)를 직접 확인한다."""
    raw = entry.get(parsed_key.replace("_parsed", "")) or ""
    return bool(re.search(r"(Z|[+-]\d{2}:?\d{2}|\b(?:UT|GMT|UTC|EST|EDT|PST|PDT|KST)\b)\s*$", raw.strip()))


def entry_summary(entry):
    if entry.get("summary"):
        return entry["summary"]
    if entry.get("description"):
        return entry["description"]
    return ""


def fetch_feed(name, url):
    # feedparser는 내부적으로 urllib을 쓰는데 기본 소켓 타임아웃이 None(무한)이라,
    # 응답을 끝내 주지 않는 호스트가 하나만 있어도 매일 08:00 무인 실행이 영원히
    # 멈춘다. 전역 소켓 타임아웃으로 상한을 건다(feedparser에 per-call 타임아웃
    # 인자가 없어 이 방법을 쓴다).
    socket.setdefaulttimeout(FEED_TIMEOUT_SEC)
    # 기본 UA(Python-urllib/x.x)는 Cloudflare가 봇으로 보고 403으로 막는 경우가 있다.
    # send_broadcast.py가 같은 이유로 이미 UA를 지정하고 있는데, 정작 Cloudflare 뒤에
    # 있는 피드(Wired, Ars Technica, TechCrunch)를 긁는 이쪽에는 빠져 있었다.
    parsed = feedparser.parse(url, agent=USER_AGENT)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"파싱 실패: {parsed.bozo_exception}")
    return parsed.entries


def main():
    args = parse_args()
    feeds_config = json.loads(Path(args.feeds).read_text(encoding="utf-8"))
    feeds = feeds_config["feeds"]

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.lookback_days)
    stale_cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_FEED_THRESHOLD_DAYS)
    published_links = load_published_links(Path(args.docs_dir))

    candidates = []
    failed_feeds = []
    stale_feeds = []
    skipped_duplicates = 0
    skipped_self_promo = 0
    for feed in feeds:
        name, url = feed["name"], feed["url"]
        try:
            entries = fetch_feed(name, url)
        except Exception as exc:  # 피드 하나가 실패해도 나머지는 계속 진행
            print(f"[WARN] {name} 수집 실패: {exc}", file=sys.stderr)
            failed_feeds.append(name)
            continue

        # 피드가 200을 주고 항목도 있는데 전부 STALE_FEED_THRESHOLD_DAYS보다 오래된
        # 경우 = 그 매체가 사실상 발행을 멈춘 상태다. 실패로 잡히지 않아 조용히 0건만
        # 기여하므로, 눈에 띄게 보고해 사람이 피드 교체 여부를 판단할 수 있게 한다.
        # (candidates용 cutoff가 아니라 별도의 넉넉한 기준을 쓴다 — cutoff는 신선도
        # 때문에 1~2일까지 짧아질 수 있는데, 그 기준으로 죽음을 판단하면 며칠에 한 번
        # 발행하는 정상 피드까지 매번 죽었다고 오탐한다.)
        feed_tz = feed.get("tz")
        newest = max((d for d in (entry_published_at(e, feed_tz) for e in entries) if d), default=None)
        if entries and (newest is None or newest < stale_cutoff):
            stale_feeds.append(
                {"name": name, "latest": newest.date().isoformat() if newest else None}
            )
            print(
                f"[WARN] {name}: 최근 {STALE_FEED_THRESHOLD_DAYS}일 이내 기사 없음"
                f"(최신 {newest.date().isoformat() if newest else '날짜없음'}) — 피드가 죽었는지 확인 필요",
                file=sys.stderr,
            )

        for entry in entries:
            published_at = entry_published_at(entry, feed_tz)
            if published_at is None or published_at < cutoff:
                continue
            link = entry.get("link")
            title = entry.get("title")
            if not link or not title:
                continue
            link = link.strip()
            if link in published_links:
                # 다른 날짜의 브리핑에 이미 실린 기사는 다시 후보로 뽑지 않는다.
                skipped_duplicates += 1
                continue
            if is_self_promo_post(title):
                skipped_self_promo += 1
                continue
            candidates.append(
                {
                    "title": title.strip(),
                    "link": link,
                    "source": name,
                    "source_type": feed.get("type", "press"),
                    "source_weight": float(feed.get("weight", DEFAULT_SOURCE_WEIGHT)),
                    "published_at": published_at.isoformat(),
                    "rss_summary": entry_summary(entry).strip(),
                }
            )

    # 출처 가중치·교차 보도·신선도를 합산한 점수로 정렬한 뒤, 출처 다양성을 지키면서
    # top-n을 채운다(점수 구성은 compute_rank_score 주석 참고).
    compute_cross_source_counts(candidates)
    for c in candidates:
        c["cross_source_count"] = c.pop("_cross_source_count")
    now = datetime.now(timezone.utc)
    for c in candidates:
        c["rank_score"] = round(compute_rank_score(c, cutoff, now), 3)
    # 점수가 같을 때는 최신순 — 정렬이 실행마다 흔들리지 않도록 결정적으로 만든다.
    candidates.sort(key=lambda a: (a["rank_score"], a["published_at"]), reverse=True)

    # 같은 사건을 다루는 후보가 여러 개 있어도(=cross_source_count가 높아 순위는
    # 위로 올라오지만) top-10 자리를 여러 개 차지하지 않도록, 사건 클러스터마다
    # 가장 순위 높은 것 하나만 채택한다 — 링크가 달라도 내용이 겹치는 기사가
    # 브리핑에 나란히 실리는 걸 막는 핵심 로직.
    cluster_ids = build_same_story_clusters(candidates)

    selected = []
    per_source_count = {}
    used_clusters = set()

    # 공식 발표(primary) 자리를 먼저 확보한다. 1차 출처는 그걸 받아쓴 기사보다 항상
    # 낫지만 발행량이 하루 0.3~0.4건뿐이라, 점수만으로 겨루게 두면 하루 6건씩 쏟아내는
    # 매체에 밀려 사라진다. 점수 순서는 그대로 존중하고(이미 정렬돼 있다) 개수만
    # 보장하며, 그날 공식 발표가 없으면 아무 일도 하지 않는다.
    for article, cid in zip(candidates, cluster_ids):
        if len(selected) >= min(PRIMARY_MIN_SLOTS, args.top_n):
            break
        if article.get("source_type") != "primary" or cid in used_clusters:
            continue
        if per_source_count.get(article["source"], 0) >= args.max_per_source:
            continue
        selected.append(article)
        per_source_count[article["source"]] = per_source_count.get(article["source"], 0) + 1
        used_clusters.add(cid)

    selected_links = {a["link"] for a in selected}
    for article, cid in zip(candidates, cluster_ids):
        if len(selected) >= args.top_n:
            break
        if cid in used_clusters or article["link"] in selected_links:
            continue
        count = per_source_count.get(article["source"], 0)
        if count >= args.max_per_source:
            continue
        selected.append(article)
        selected_links.add(article["link"])
        per_source_count[article["source"]] = count + 1
        used_clusters.add(cid)

    # 출처 다양성 제한 때문에 top-n을 못 채웠다면, 이번엔 그 제한만 풀고
    # 사건 클러스터 중복 방지는 유지한 채로 부족분을 채운다.
    if len(selected) < args.top_n:
        chosen_links = {a["link"] for a in selected}
        for article, cid in zip(candidates, cluster_ids):
            if len(selected) >= args.top_n:
                break
            if article["link"] in chosen_links or cid in used_clusters:
                continue
            selected.append(article)
            chosen_links.add(article["link"])
            used_clusters.add(cid)

    # 그래도 못 채웠다면(사건 종류 자체가 top-n보다 적을 만큼 뉴스가 적은 날)
    # 마지막으로 클러스터 중복 방지까지 풀어서 채운다 — 자리를 비워두는 것보다는 낫다.
    if len(selected) < args.top_n:
        chosen_links = {a["link"] for a in selected}
        for article in candidates:
            if len(selected) >= args.top_n:
                break
            if article["link"] in chosen_links:
                continue
            selected.append(article)
            chosen_links.add(article["link"])

    # primary 슬롯 보장은 "뽑히느냐"에만 관여해야지 "몇 번째로 실리느냐"까지 정하면
    # 안 된다 — 먼저 채운 순서를 그대로 두면 사소한 공식 블로그 글이 그날 가장 큰
    # 속보보다 위에 실린다. 최종 노출 순서는 점수 순으로 되돌린다.
    selected.sort(key=lambda a: (a["rank_score"], a["published_at"]), reverse=True)

    # 같은 사건을 다룬 다른 매체(related). 클러스터 계산 결과에서 채택되지 않고
    # 버려지던 형제 기사를 살려, 기사 카드에 "이 사건을 다룬 다른 매체"로 보여준다.
    # 지금까지는 몇 곳이 다뤘는지(cross_source_count)만 숫자로 알려주고 정작 어디가
    # 다뤘는지는 못 보여줬는데, Techmeme이 파는 가치가 정확히 그 "어디가"다.
    #
    # 클러스터가 정확해야만 의미가 있다 — 회사명 하나로 무관한 기사가 묶이던 시절에
    # 이걸 만들었다면 전혀 다른 사건을 "같은 사건"이라고 독자에게 표시했을 것이다.
    cluster_members = {}
    for article, cid in zip(candidates, cluster_ids):
        cluster_members.setdefault(cid, []).append(article)
    cluster_of = {a["link"]: cid for a, cid in zip(candidates, cluster_ids)}
    for article in selected:
        siblings = cluster_members.get(cluster_of.get(article["link"]), [])
        article["related"] = [
            {"title": s["title"], "link": s["link"], "source": s["source"]}
            for s in siblings
            if s["link"] != article["link"]
        ][:RELATED_MAX]

    # 예비 후보(reserves): 원문을 읽을 수 없거나 브리핑에 실을 가치가 없는 기사가
    # 나왔을 때 그 자리를 대신 채울 대체재다.
    #
    # 지금까지는 top-n만 내보내고 나머지 후보를 통째로 버렸는데(어느 날은 22개 중
    # 12개를 버렸다), 그러면 원문 접속이 막힌 기사가 나와도 갈아끼울 게 없어서 RSS
    # 요약만으로 쓴 부실한 항목을 그대로 실어야 했다. 실제로 하루에 10건 중 3건이
    # 그렇게 나간 적이 있다. 버리던 후보를 남겨두는 것만으로 그 자리를 정상 기사로
    # 채울 수 있다.
    #
    # 선정 기준은 본선과 같다 — 이미 뽑힌 기사와 링크가 겹치지 않고, 같은 사건
    # 클러스터도 아니어야 한다(교체했는데 내용이 겹치면 의미가 없다). 출처 상한도
    # 일단 지키되, 그것 때문에 예비가 하나도 없으면 상한만 풀어 채운다 — 예비가
    # 필요한 상황은 대개 특정 출처(HN처럼 외부 링크를 가리키는 피드)가 실패할 때라,
    # 예비가 비어 있으면 장치 자체가 무의미해진다.
    selected_links = {a["link"] for a in selected}
    selected_clusters = {cid for a, cid in zip(candidates, cluster_ids) if a["link"] in selected_links}

    reserves = []
    reserve_links = set()
    reserve_clusters = set()
    reserve_source_count = dict(per_source_count)
    for enforce_source_cap in (True, False):
        for article, cid in zip(candidates, cluster_ids):
            if len(reserves) >= args.reserve_count:
                break
            if article["link"] in selected_links or article["link"] in reserve_links:
                continue
            if cid in selected_clusters or cid in reserve_clusters:
                continue
            if enforce_source_cap and reserve_source_count.get(article["source"], 0) >= args.max_per_source:
                continue
            reserves.append(article)
            reserve_links.add(article["link"])
            reserve_clusters.add(cid)
            reserve_source_count[article["source"]] = reserve_source_count.get(article["source"], 0) + 1
        if len(reserves) >= args.reserve_count:
            break

    today_label = datetime.now(KST).strftime("%Y-%m-%d")
    output_path = Path(args.output) if args.output else DEFAULT_DATA_DIR / f"articles_{today_label}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = {
        "date": today_label,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": args.lookback_days,
        "feeds_total": len(feeds),
        "feeds_failed": failed_feeds,
        "feeds_stale": stale_feeds,  # 200은 오지만 룩백 기간 내 기사가 없는 = 사실상 죽은 피드
        "candidates_total": len(candidates),
        "skipped_duplicates": skipped_duplicates,
        "skipped_self_promo": skipped_self_promo,
        "articles": selected,
        "reserves": reserves,
    }
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"수집 완료: 후보 {len(candidates)}개(과거 중복 {skipped_duplicates}개, "
        f"자기홍보/토론글 {skipped_self_promo}개 제외) 중 "
        f"{len(selected)}개 선별, 예비 {len(reserves)}개 -> {output_path}"
    )
    if len(reserves) < args.reserve_count:
        # 예비가 모자라면 교체 여력이 그만큼 줄어든다는 뜻이라 눈에 띄게 알린다
        # (뉴스가 적은 날이나 중복 제외가 많았던 날에 발생).
        print(
            f"예비 후보 부족: {len(reserves)}/{args.reserve_count}개 — 원문을 못 읽는 기사가 "
            f"{len(reserves)}건을 넘으면 교체할 대체재가 없습니다.",
            file=sys.stderr,
        )
    if failed_feeds:
        print(f"실패한 피드: {', '.join(failed_feeds)}", file=sys.stderr)
    if stale_feeds:
        detail = ", ".join(f"{s['name']}(최신 {s['latest'] or '날짜없음'})" for s in stale_feeds)
        print(f"오래된 피드(최근 기사 없음): {detail}", file=sys.stderr)


if __name__ == "__main__":
    main()
