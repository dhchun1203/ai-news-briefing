#!/usr/bin/env python3
"""날짜별 동적 OG 이미지(1200x630)를 그린다 — 그날의 daily_insight 헤드라인을
직접 이미지에 렌더링해서, 링크 미리보기(카카오톡/트위터/페이스북)만 봐도 그날
무슨 얘기인지 알 수 있게 한다.

이 모듈은 Pillow에 의존하는데, Pillow는 requirements.txt의 다른 패키지(feedparser,
Jinja2)와 달리 이미지 렌더링이라는, 매일 자동 실행되는 파이프라인 입장에서는
"실패해도 사이트 생성 자체를 막으면 안 되는" 부가 기능이다. 그래서 이 모듈을
호출하는 쪽(scripts/seo_utils.py의 build_og_image_url)이 항상 예외를 잡아서
실패 시 기존 정적 og-image.png로 조용히 대체하도록 설계했다 — 이 파일 자체는
그런 안전장치 없이 실패하면 그냥 예외를 던진다(호출부 책임).
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT_PATH = ROOT / "templates" / "static" / "fonts" / "NotoSerifKR-Variable.ttf"

WIDTH, HEIGHT = 1200, 630
BG = "#ffffff"
TEXT = "#121212"
MUTED = "#666666"
ACCENT = "#a2201d"
MARGIN = 90
MAX_HEADLINE_LINES = 3


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), size)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list:
    """한국어 headline은 정상적인 띄어쓰기가 있는 문장이므로 공백 기준으로
    줄바꿈한다. 실제 렌더 너비를 매번 측정해서(추측이 아니라) max_width를
    넘지 않는 선에서 단어를 채운다."""
    words = text.split(" ")
    lines, current = [], ""
    for w in words:
        candidate = f"{current} {w}".strip()
        if not current or draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def _draw_wrapped(draw, text, font, x, y, max_width, line_height, max_lines, fill):
    """max_lines를 넘어가는 텍스트는 마지막 줄을 말줄임(…)으로 잘라, 헤드라인이
    아무리 길어도 이미지 밖으로 넘치거나 다른 요소와 겹치지 않게 한다."""
    lines = _wrap_text(draw, text, font, max_width)
    truncated = len(lines) > max_lines
    lines = lines[:max_lines]
    if truncated and lines:
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > max_width:
            last = last[:-1]
        lines[-1] = last + "…"
    for i, line in enumerate(lines):
        draw.text((x, y + i * line_height), line, font=font, fill=fill)


def generate(identifier: str, headline_ko: str, out_path: Path) -> None:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 10, HEIGHT], fill=ACCENT)  # site.html.j2의 .insight 블록과 동일한 accent 모티프

    eyebrow_font = _font(28)
    draw.text((MARGIN, 90), f"DAILY AI THREAD · {identifier}", font=eyebrow_font, fill=ACCENT)

    headline_font = _font(56)
    max_width = WIDTH - MARGIN * 2
    _draw_wrapped(draw, headline_ko, headline_font, MARGIN, 190, max_width, 72, MAX_HEADLINE_LINES, TEXT)

    footer_font = _font(26)
    draw.text((MARGIN, HEIGHT - 90), "dailyaithread.com", font=footer_font, fill=MUTED)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
