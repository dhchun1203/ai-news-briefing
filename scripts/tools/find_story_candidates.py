#!/usr/bin/env python3
"""아카이브에서 '여러 날에 걸친 이슈' 후보를 찾는다 (사람이 손으로 돌리는 도구).

무엇을 위한 것인가
------------------
`/story/<slug>` 타임라인의 재료를 찾는다. 지금 파이프라인의 클러스터링은
**하루 안에서만** 돈다(`build_same_story_clusters`도 `compute_cross_source_counts`도
그날 후보 리스트 하나만 받는다). 날짜를 가로지르는 연결은 어디에도 없으므로,
이슈를 찾는 일은 사람이 판단한다. 이 스크립트는 그 판단에 후보를 제시할 뿐이다.

왜 키워드 '쌍'인가
------------------
이슈 단위는 회사가 아니라 사건이어야 한다. 실측하면 OpenAI는 17일 중 15일,
Anthropic은 11일 등장한다 — 단일 키워드로 묶으면 "OpenAI 이슈" 같은 무의미한
덩어리가 나온다. 두 키워드가 함께 등장한 날을 세면 "OpenAI+Hugging"처럼 사건에
가까운 단위가 나온다.

하루 안 클러스터링용 `CLUSTER_STOP_ENTITIES`를 그대로 쓰지 않는 이유도 여기 있다.
그 목록에는 `Hugging`이 들어 있어서, 그대로 쓰면 정작 찾으려는 Hugging Face 침해가
사라진다. 여기서는 우산 이름만 뺀다.

한계 (결과를 읽을 때 반드시 감안할 것)
--------------------------------------
- `extract_keywords`는 대문자로 시작하는 ASCII 토큰만 뽑는다. **한글 제목에서는
  아무것도 안 나온다.** 지금까지 발행된 기사 중 한글 제목은 소수라 영향이 작지만,
  한국 매체가 실리기 시작하면 이 도구의 회수율도 같이 떨어진다.
- 제목만 본다. 이슈 이름이 본문에만 있으면 못 찾는다.

사용법
------
    py scripts/tools/find_story_candidates.py
    py scripts/tools/find_story_candidates.py --min-days 3 --out candidates.txt
"""
import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fetch_articles as fa  # noqa: E402

# 우산 이름 — 이것만으로 묶이면 이슈가 아니라 회사다.
UMBRELLA = {
    "Google", "OpenAI", "Anthropic", "Meta", "Microsoft", "Apple", "Amazon",
    "Nvidia", "ChatGPT", "Gemini", "Claude", "Copilot", "Alphabet", "DeepMind",
}


def load_articles(archive_dir: Path):
    arts = []
    for f in sorted(archive_dir.glob("*.json")):
        if f.name.endswith(".sent.json"):
            continue
        try:
            day = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        date = day.get("date", f.stem)
        for i, a in enumerate(day.get("articles", []), 1):
            title = a.get("title") or ""
            arts.append({
                "date": date, "article": i, "title": title,
                "source": a.get("source", ""),
                "keywords": fa.extract_keywords(title) - UMBRELLA,
            })
    return arts


def find_candidates(arts, min_days=2):
    """키워드 쌍별로 등장한 날짜 집합을 만들고, min_days 이상인 것만 남긴다."""
    pair_days, pair_arts = {}, {}
    for a in arts:
        for pair in combinations(sorted(a["keywords"]), 2):
            pair_days.setdefault(pair, set()).add(a["date"])
            pair_arts.setdefault(pair, []).append(a)
    cands = [
        {"pair": pair, "days": sorted(days), "articles": sorted(pair_arts[pair], key=lambda x: x["date"])}
        for pair, days in pair_days.items() if len(days) >= min_days
    ]
    cands.sort(key=lambda c: (-len(c["days"]), -len(c["articles"])))
    return cands


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--docs-dir", default=str(ROOT / "docs"))
    p.add_argument("--min-days", type=int, default=2, help="며칠 이상 이어져야 후보로 볼지")
    p.add_argument("--top", type=int, default=20)
    p.add_argument("--out", help="결과를 쓸 파일(콘솔이 cp949라 한국어가 깨지는 환경용)")
    args = p.parse_args()

    arts = load_articles(Path(args.docs_dir) / "archive")
    dates = sorted({a["date"] for a in arts})
    lines = [f"아카이브 {len(dates)}일, 기사 {len(arts)}건 ({dates[0] if dates else '-'} ~ {dates[-1] if dates else '-'})"]

    hangul = sum(1 for a in arts if any("가" <= c <= "힣" for c in a["title"]))
    lines.append(f"한글 제목 기사 {hangul}건 — 이 도구가 키워드를 못 뽑는 범위")
    lines.append("")

    cands = find_candidates(arts, args.min_days)
    lines.append(f"=== {args.min_days}일 이상 이어진 키워드 쌍: {len(cands)}건 ===")
    for c in cands[:args.top]:
        lines.append("%-30s %d일 %2d건  %s ~ %s" % (
            "+".join(c["pair"]), len(c["days"]), len(c["articles"]), c["days"][0], c["days"][-1]))
        for a in c["articles"]:
            lines.append("      %s  #%-2d [%s] %s" % (a["date"], a["article"], a["source"][:14], a["title"][:62]))
        lines.append("")

    text = "\n".join(lines)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out} ({len(cands)} candidates)")
    else:
        # 콘솔이 cp949인 환경에서 한국어가 깨지는 것은 이 저장소의 알려진 제약이다.
        print(text)


if __name__ == "__main__":
    main()
