#!/usr/bin/env python3
"""파이프라인이 쓰는 KST 기준 날짜 정보를 한 번에 출력한다.

왜 셸 `date` 대신 이 스크립트인가:
이 Routine은 `0 23 * * *`(UTC)로 실행되므로 컨테이너 시계는 **UTC**다. 08:00 KST
일요일에 실행될 때 bare `date +%u`는 6(토요일)을 반환해서, 일요일에만 도는 단계
(주간 회고)가 매주 조용히 건너뛰어진다 — 2026-07-26 첫 일요일 직전에 발견한 실제
버그다.

그렇다고 `TZ=Asia/Seoul date`로 고치는 것도 안전하지 않다. `TZ=<지역명>`은 시스템에
IANA tzdata가 있어야 동작하는데, 없으면 **에러 없이 조용히 UTC로 폴백**한다(실제로
개발 환경인 Windows Git Bash가 그렇다 — `/usr/share/zoneinfo`가 없어 `TZ=Asia/Seoul`이
GMT를 그대로 반환한다). 즉 고쳤다고 생각한 뒤에도 같은 버그가 조용히 남을 수 있다.

Python의 `zoneinfo`는 `requirements.txt`에 고정된 `tzdata` 패키지를 폴백으로 쓰므로
시스템 tzdata 유무와 무관하게 항상 올바르다 — 이미 `fetch_articles.py`,
`generate_weekly_site.py`가 같은 방식을 쓰고 있고 운영에서 검증됐다.

출력(파싱하기 쉬운 key=value):
    weekday=7            # ISO 요일, 1=월 ... 7=일
    today=2026-07-26
    week_label=2026-W30  # 이번 주 ISO 주차
    start_date=2026-07-20  # 이번 주 월요일
    end_date=2026-07-26    # 이번 주 일요일
"""
from datetime import timedelta
from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def kst_date_facts(now=None):
    """KST 기준 오늘 날짜와 '이번 주'(월~일) 범위를 계산해 dict로 돌려준다.

    주 범위는 ISO 8601 정의(월요일 시작)를 따른다. week_label도 ISO 주차라
    연말·연초에 달력 연도와 어긋날 수 있는데(예: 2026-12-28은 2027-W01),
    `date.isocalendar()`가 주는 ISO 연도를 그대로 써서 항상 일관되게 맞춘다.
    """
    today = (now or datetime.now(KST)).date()
    iso_year, iso_week, iso_weekday = today.isocalendar()
    monday = today - timedelta(days=iso_weekday - 1)
    sunday = monday + timedelta(days=6)
    return {
        "weekday": iso_weekday,
        "today": today.isoformat(),
        "week_label": f"{iso_year}-W{iso_week:02d}",
        "start_date": monday.isoformat(),
        "end_date": sunday.isoformat(),
    }


def main():
    for key, value in kst_date_facts().items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
