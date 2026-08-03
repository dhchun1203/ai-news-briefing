#!/usr/bin/env python3
"""templates/static/favicon.svg와 같은 그림을 PNG로 렌더링한다.

**왜 PNG/ICO가 따로 필요한가**: 구글 검색 결과에 파비콘이 지구본(기본 아이콘)으로
나왔다. 이 사이트는 SVG 파비콘만 제공하고 있었는데, 구글 파비콘 크롤러가 SVG를
못 가져가는 경우가 보고된다. 브라우저 탭에는 선명한 SVG를 그대로 쓰고, 검색엔진용
으로 PNG를 나란히 둔다.

**favicon.ico도 함께 만든다.** 구글은 <link rel="icon">을 먼저 보지만, 그걸 못 읽으면
사이트 루트의 /favicon.ico를 찾는다. 링크 태그와 무관하게 항상 있어야 하는 자리라
비워두면 폴백이 통째로 사라진다(실제로 404였다). 16/32/48 세 크기를 한 파일에 담는다.

**왜 매 실행 렌더링이 아니라 한 번 만들어 커밋하나**: 파비콘은 디자인이 바뀔 때만
갱신되는 정적 자산이다. 매일 도는 파이프라인에 Pillow 의존을 하나 더 얹으면,
그림 하나 때문에 사이트 생성이 멈출 수 있다(og_image.py가 실패해도 사이트가
살아남도록 폴백을 둔 것과 같은 이유). 결과물을 커밋해두고 SHARED_ASSETS로
복사만 한다. **favicon.svg를 고치면 이 스크립트를 다시 돌려 PNG도 맞춰야 한다.**

    py scripts/tools/generate_favicon_png.py

구글 가이드라인은 48px의 배수인 정사각형을 권한다. 96×96(48×2)으로 만든다.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent.parent
FONT_PATH = ROOT / "templates" / "static" / "fonts" / "NotoSerifKR-Variable.ttf"
OUT_PNG = ROOT / "templates" / "static" / "favicon.png"
OUT_ICO = ROOT / "templates" / "static" / "favicon.ico"
# ICO에 담을 크기들. 브라우저 탭·북마크·검색엔진이 각각 다른 크기를 고른다.
ICO_SIZES = [(48, 48), (32, 32), (16, 16)]

# favicon.svg는 viewBox="0 0 64 64" 기준이다. 아래 값들은 그 좌표를 그대로 옮기고
# SCALE만 곱한 것이라, SVG를 고치면 같은 자리에 같은 배율로 반영하면 된다.
SVG_SIZE = 64
SCALE = 96 / SVG_SIZE  # 96px = 구글 권장 48px의 2배
SIZE = int(SVG_SIZE * SCALE)

BG = "#121212"        # <rect fill>
FG = "#ffffff"        # <text fill>
ACCENT = "#a2201d"    # <circle fill>
RADIUS = 10 * SCALE   # rect rx
DOT_CX, DOT_CY, DOT_R = 50 * SCALE, 14 * SCALE, 6 * SCALE
TEXT_SIZE = int(34 * SCALE)
TEXT_CX, TEXT_BASELINE = 32 * SCALE, 44 * SCALE

# 렌더링 배율. 라운드 모서리와 원을 크게 그린 뒤 줄이면 계단 현상이 사라진다
# (Pillow에는 안티에일리어싱 옵션이 없어 이 방식이 사실상 표준이다).
SS = 8


def main() -> None:
    n = SIZE * SS
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, n - 1, n - 1], radius=RADIUS * SS, fill=BG)

    # 세리프 A. SVG는 Georgia를 쓰지만 여기서는 저장소에 있는 Noto Serif KR을 쓴다 —
    # OG 이미지·브랜드 마크와 같은 자형이라 채널 사이에서 마크가 달라 보이지 않는다.
    font = ImageFont.truetype(str(FONT_PATH), TEXT_SIZE * SS)
    # SVG는 Georgia의 font-weight:700인데, Noto Serif KR은 같은 Bold라도 획이 훨씬
    # 가늘다. 네 굵기를 나란히 렌더링해 비교한 결과 Black이 Georgia Bold에 가장
    # 가까웠다. 파비콘은 실제로 16~32px로 보이므로 굵은 쪽이 형태도 더 잘 남는다.
    font.set_variation_by_name("Black")
    # SVG의 text-anchor="middle" + y=베이스라인을 그대로 재현한다. anchor="ms"가
    # (수평 중앙, 베이스라인) 기준이라 좌표를 다시 계산할 필요가 없다.
    draw.text((TEXT_CX * SS, TEXT_BASELINE * SS), "A", font=font, fill=FG, anchor="ms")

    draw.ellipse(
        [(DOT_CX - DOT_R) * SS, (DOT_CY - DOT_R) * SS,
         (DOT_CX + DOT_R) * SS, (DOT_CY + DOT_R) * SS],
        fill=ACCENT,
    )

    flat = img.resize((SIZE, SIZE), Image.LANCZOS)
    flat.save(OUT_PNG, "PNG")
    print(f"{OUT_PNG} ({SIZE}x{SIZE}) 생성")

    # ICO는 큰 원본 하나를 넘기면 Pillow가 각 크기로 줄여 담는다. 미리 96px로 줄인
    # 것을 다시 줄이면 두 번 리샘플링돼 작은 크기에서 뭉개지므로 고해상도에서 간다.
    img.resize((256, 256), Image.LANCZOS).save(OUT_ICO, "ICO", sizes=ICO_SIZES)
    print(f"{OUT_ICO} ({', '.join(f'{w}x{h}' for w, h in ICO_SIZES)}) 생성")


if __name__ == "__main__":
    main()
