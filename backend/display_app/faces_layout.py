from __future__ import annotations

from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from .data import (
    AIR_QUALITY_AMAZING,
    AIR_QUALITY_AWFUL,
    AIR_QUALITY_AVERAGE,
    AIR_QUALITY_BAD,
    AIR_QUALITY_GOOD,
    DisplayModel,
)
from .layout_common import (
    BACKGROUND,
    COLOR_MUTED,
    LAYOUT_FACES,
    DisplayLayout,
    co2_value_box,
    draw_value,
    top_section_height,
)

AIR_QUALITY_LEVELS = (
    AIR_QUALITY_AWFUL,
    AIR_QUALITY_BAD,
    AIR_QUALITY_AVERAGE,
    AIR_QUALITY_GOOD,
    AIR_QUALITY_AMAZING,
)
EMOJI_FONT_PATH = "/usr/local/share/fonts/truetype/noto/NotoEmoji.ttf"
FACE_STRIP_RAISE = 16
FACE_ICON_SIZE = 70
FACE_SUPERSAMPLE = 4
AIR_QUALITY_GLYPHS = {
    AIR_QUALITY_AWFUL: "🤮",
    AIR_QUALITY_BAD: "😥",
    AIR_QUALITY_AVERAGE: "😬",
    AIR_QUALITY_GOOD: "☺︎",
    AIR_QUALITY_AMAZING: "🤩",
}

@lru_cache(maxsize=64)
def load_emoji_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(EMOJI_FONT_PATH, size=size)


@lru_cache(maxsize=128)
def best_fit_emoji_font(glyph: str, max_w: int, max_h: int) -> ImageFont.FreeTypeFont:
    low = 12
    high = max(12, max(max_w, max_h) * 2)
    best = load_emoji_font(low)
    while low <= high:
        mid = (low + high) // 2
        font = load_emoji_font(mid)
        bbox = font.getbbox(glyph)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        if width <= max_w and height <= max_h:
            best = font
            low = mid + 1
        else:
            high = mid - 1
    return best


@lru_cache(maxsize=64)
def render_face_icon(size: int, quality_level: str, color: str) -> Image.Image:
    canvas_size = max(24, size) * FACE_SUPERSAMPLE
    icon = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)
    padding = max(8, canvas_size // 10)
    glyph = AIR_QUALITY_GLYPHS[quality_level]
    font = best_fit_emoji_font(glyph, canvas_size - (padding * 2), canvas_size - (padding * 2))
    bbox = draw.textbbox((0, 0), glyph, font=font)
    glyph_w = bbox[2] - bbox[0]
    glyph_h = bbox[3] - bbox[1]
    glyph_x = ((canvas_size - glyph_w) // 2) - bbox[0]
    glyph_y = ((canvas_size - glyph_h) // 2) - bbox[1]
    draw.text((glyph_x, glyph_y), glyph, font=font, fill=color)

    return icon.resize((size, size), resample=Image.Resampling.LANCZOS)


def draw_face_strip(img: Image.Image, model: DisplayModel, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    box_width = x1 - x0 + 1
    box_height = y1 - y0 + 1
    cell_width = box_width / len(AIR_QUALITY_LEVELS)
    face_size = max(24, min(FACE_ICON_SIZE, box_height - 10))

    for index, quality_level in enumerate(AIR_QUALITY_LEVELS):
        cell_x0 = x0 + int(round(index * cell_width))
        cell_x1 = x0 + int(round((index + 1) * cell_width)) - 1
        icon_x = cell_x0 + max(0, ((cell_x1 - cell_x0 + 1) - face_size) // 2)
        icon_y = y0 + max(0, (box_height - face_size) // 2)
        icon_color = model.co2_color if model.co2_quality == quality_level else COLOR_MUTED
        icon = render_face_icon(face_size, quality_level, icon_color)
        img.paste(icon, (icon_x, icon_y), icon)


class FacesDisplayLayout(DisplayLayout):
    name = LAYOUT_FACES

    def render(self, model: DisplayModel, size: tuple[int, int]) -> Image.Image:
        width, height = size
        img = Image.new("RGB", (width, height), BACKGROUND)
        draw = ImageDraw.Draw(img)
        top_height = top_section_height(height)
        draw_value(draw, co2_value_box(draw, size), model.co2_value, model.co2_color)
        draw_face_strip(img, model, (0, max(0, top_height - FACE_STRIP_RAISE), width - 1, height - 1))
        return img
