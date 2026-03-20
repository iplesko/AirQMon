from __future__ import annotations

from PIL import Image, ImageDraw

from .data import DisplayModel
from .layout_common import (
    BACKGROUND,
    CO2_LABEL_TEXT,
    CO2_LABEL_X,
    CO2_LABEL_Y,
    COLOR_DIVIDER,
    COLOR_MUTED,
    COLOR_TEXT,
    LAYOUT_STANDARD,
    SECTION_DIVIDER_WIDTH,
    TOP_LABEL_FONT_SIZE,
    DisplayLayout,
    co2_value_box,
    draw_metric_box,
    draw_value,
    load_font,
    top_section_height,
)


class StandardDisplayLayout(DisplayLayout):
    name = LAYOUT_STANDARD

    def render(self, model: DisplayModel, size: tuple[int, int]) -> Image.Image:
        width, height = size
        img = Image.new("RGB", (width, height), BACKGROUND)
        draw = ImageDraw.Draw(img)

        top_height = top_section_height(height)
        divider_y = top_height
        bottom_y0 = divider_y + SECTION_DIVIDER_WIDTH

        draw.rectangle((0, divider_y, width - 1, bottom_y0 - 1), fill=COLOR_DIVIDER)

        top_label_font = load_font(TOP_LABEL_FONT_SIZE)
        draw.text((CO2_LABEL_X, CO2_LABEL_Y), CO2_LABEL_TEXT, font=top_label_font, fill=COLOR_MUTED)
        top_box = co2_value_box(draw, size)
        draw_value(draw, top_box, model.co2_value, model.co2_color)

        first_divider_x = width // 3
        second_divider_x = (2 * width) // 3
        draw.rectangle(
            (first_divider_x, bottom_y0, first_divider_x + SECTION_DIVIDER_WIDTH - 1, height - 1),
            fill=COLOR_DIVIDER,
        )
        draw.rectangle(
            (second_divider_x, bottom_y0, second_divider_x + SECTION_DIVIDER_WIDTH - 1, height - 1),
            fill=COLOR_DIVIDER,
        )

        trend_box = (0, bottom_y0, first_divider_x - 1, height - 1)
        temp_box = (first_divider_x + SECTION_DIVIDER_WIDTH, bottom_y0, second_divider_x - 1, height - 1)
        humidity_box = (second_divider_x + SECTION_DIVIDER_WIDTH, bottom_y0, width - 1, height - 1)

        draw_metric_box(draw, trend_box, "Trend", model.trend_value, model.trend_color)
        draw_metric_box(draw, temp_box, "Temp", model.temperature_value, COLOR_TEXT)
        draw_metric_box(draw, humidity_box, "Hum", model.humidity_value, COLOR_TEXT)
        return img
