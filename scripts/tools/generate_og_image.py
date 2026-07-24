#!/usr/bin/env python3
"""1회성 로컬 스크립트 — templates/static/og-image.png(1200x630)을 만든다.

일별 파이프라인(daily Routine)에서는 절대 실행되지 않는다. 소셜 미리보기(og:image)용
정적 브랜드 카드 한 장을 만드는 용도라 한 번만 실행하면 되고, requirements.txt에
Pillow를 추가하지 않기 위해 로컬에서만 임시로 설치해 실행한다:

    python -m pip install Pillow
    python scripts/tools/generate_og_image.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_PATH = ROOT / "templates" / "static" / "og-image.png"

WIDTH, HEIGHT = 1200, 630
BG = "#ffffff"
TEXT = "#121212"
MUTED = "#666666"
ACCENT = "#a2201d"

FONT_DIR = Path("C:/Windows/Fonts")


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONT_DIR / name
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


def main():
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)

    margin = 90
    draw.rectangle([0, 0, 10, HEIGHT], fill=ACCENT)  # 왼쪽 얇은 accent 바 — 사이트 .insight 블록과 동일한 모티프

    eyebrow_font = _font("segoeuib.ttf", 28)
    draw.text((margin, 140), "DAILY AI THREAD", font=eyebrow_font, fill=ACCENT)

    title_font_ko = _font("NotoSerifKR-VF.ttf", 74)
    title_font_en = _font("georgiab.ttf", 78)
    draw.text((margin, 200), "AI 뉴스 브리핑", font=title_font_ko, fill=TEXT)
    draw.text((margin, 300), "Daily AI Briefing", font=title_font_en, fill=TEXT)

    desc_font_ko = _font("NotoSerifKR-VF.ttf", 32)
    draw.text(
        (margin, 430),
        "매일 아침, 여러 출처의 AI 뉴스를 읽고",
        font=desc_font_ko,
        fill=MUTED,
    )
    draw.text(
        (margin, 478),
        "요약과 \"왜 중요한가\"를 정리해드립니다.",
        font=desc_font_ko,
        fill=MUTED,
    )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT_PATH, "PNG")
    print(f"생성 완료: {OUT_PATH} ({WIDTH}x{HEIGHT})")


if __name__ == "__main__":
    main()
