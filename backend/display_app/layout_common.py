from __future__ import annotations

from abc import ABC, abstractmethod

from PIL import Image, ImageDraw, ImageFont

from .data import DisplayModel

BACKGROUND = "#000000"
COLOR_TEXT = "#E6EEF8"
COLOR_MUTED = "#94A3B8"
COLOR_DIVIDER = "#8792A2"
COLOR_ERROR = "#FF7B72"
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SECTION_DIVIDER_WIDTH = 2
BOTTOM_LABEL_FONT_SIZE = 14
BOTTOM_SECTION_HEIGHT_RATIO = 3
TOP_LABEL_FONT_SIZE = 14
CO2_LABEL_TEXT = "CO2 ppm"
CO2_LABEL_X = 10
CO2_LABEL_Y = 6
LAYOUT_STANDARD = "standard"
LAYOUT_CO2_FACES = "co2_faces"
LAYOUT_CO2_ONLY = LAYOUT_CO2_FACES


def load_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATH, size=size)


def best_fit_font(text: str, max_w: int, max_h: int) -> ImageFont.FreeTypeFont:
    low = 12
    high = 320
    best = load_font(low)
    while low <= high:
        mid = (low + high) // 2
        font = load_font(mid)
        bbox = font.getbbox(text)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        if width <= max_w and height <= max_h:
            best = font
            low = mid + 1
        else:
            high = mid - 1
    return best


def draw_centered_text(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    color: str,
) -> None:
    x0, y0, x1, y1 = box
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = x0 + ((x1 - x0 + 1 - text_w) // 2) - bbox[0]
    y = y0 + ((y1 - y0 + 1 - text_h) // 2) - bbox[1]
    draw.text((x, y), text, font=font, fill=color)


def draw_value(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    value: str,
    color: str,
) -> None:
    value_font = best_fit_font(
        value,
        max(1, box[2] - box[0] + 1),
        max(1, box[3] - box[1] + 1),
    )
    draw_centered_text(draw, box, value, value_font, color)


def draw_metric_box(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    label: str,
    value: str,
    value_color: str,
) -> None:
    x0, y0, x1, y1 = box
    label_font = load_font(BOTTOM_LABEL_FONT_SIZE)
    label_bbox = draw.textbbox((0, 0), label, font=label_font)
    label_w = label_bbox[2] - label_bbox[0]
    label_h = label_bbox[3] - label_bbox[1]
    label_x = x0 + ((x1 - x0 + 1 - label_w) // 2) - label_bbox[0]
    label_y = y0 + 6 - label_bbox[1]
    draw.text((label_x, label_y), label, font=label_font, fill=COLOR_MUTED)

    value_box = (x0 + 6, label_y + label_h + 6, x1 - 6, y1 - 6)
    draw_value(draw, value_box, value, value_color)


def top_section_height(height: int) -> int:
    return (height * (BOTTOM_SECTION_HEIGHT_RATIO - 1)) // BOTTOM_SECTION_HEIGHT_RATIO


def co2_value_box(draw: ImageDraw.ImageDraw, size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = size
    divider_y = top_section_height(height)
    top_label_font = load_font(TOP_LABEL_FONT_SIZE)
    top_label_bbox = draw.textbbox((CO2_LABEL_X, CO2_LABEL_Y), CO2_LABEL_TEXT, font=top_label_font)
    top_box_y0 = top_label_bbox[3] + 4
    return (4, top_box_y0, width - 5, max(top_box_y0, divider_y - 5))


def make_error_frame(message: str, size: tuple[int, int]) -> Image.Image:
    width, height = size
    img = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(img)
    draw.text((12, height // 2 - 12), message, font=load_font(22), fill=COLOR_ERROR)
    return img


class DisplayLayout(ABC):
    name: str

    @abstractmethod
    def render(self, model: DisplayModel, size: tuple[int, int]) -> Image.Image:
        raise NotImplementedError
