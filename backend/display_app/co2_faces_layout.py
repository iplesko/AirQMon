from __future__ import annotations

from functools import lru_cache

from PIL import Image, ImageDraw

from .data import (
    CO2_FACE_HAPPY,
    CO2_FACE_NEUTRAL,
    CO2_FACE_SAD,
    CO2_FACE_SMILE,
    DisplayModel,
)
from .layout_common import (
    BACKGROUND,
    COLOR_MUTED,
    LAYOUT_CO2_FACES,
    DisplayLayout,
    co2_value_box,
    draw_value,
    top_section_height,
)

FACE_EXPRESSIONS = (
    CO2_FACE_SAD,
    CO2_FACE_NEUTRAL,
    CO2_FACE_SMILE,
    CO2_FACE_HAPPY,
)
FACE_STRIP_RAISE = 16
FACE_SUPERSAMPLE = 4
FACE_SPECS = {
    CO2_FACE_SAD: {"mouth_kind": "arc", "mouth_box": (0.27, 0.56, 0.73, 0.83), "mouth_angles": (200, 340)},
    CO2_FACE_NEUTRAL: {"mouth_kind": "line", "mouth_box": (0.31, 0.70, 0.69, 0.70)},
    CO2_FACE_SMILE: {"mouth_kind": "arc", "mouth_box": (0.27, 0.47, 0.73, 0.74), "mouth_angles": (20, 160)},
    CO2_FACE_HAPPY: {"mouth_kind": "chord", "mouth_box": (0.30, 0.43, 0.70, 0.72), "mouth_angles": (0, 180)},
}


def _relative_box(size: int, box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    return (
        int(round(x0 * size)),
        int(round(y0 * size)),
        int(round(x1 * size)),
        int(round(y1 * size)),
    )


@lru_cache(maxsize=64)
def render_face_icon(size: int, expression: str, color: str) -> Image.Image:
    canvas_size = max(24, size) * FACE_SUPERSAMPLE
    icon = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)
    stroke_width = max(4, canvas_size // 34)
    feature_width = max(4, canvas_size // 28)
    head_padding = int(round(canvas_size * 0.12))
    head_box = (
        head_padding,
        head_padding,
        canvas_size - head_padding - 1,
        canvas_size - head_padding - 1,
    )

    draw.ellipse(head_box, outline=color, width=stroke_width)

    eye_y = int(round(canvas_size * 0.40))
    eye_radius_x = int(round(canvas_size * 0.055))
    eye_radius_y = int(round(canvas_size * 0.075))
    eye_centers = (
        int(round(canvas_size * 0.37)),
        int(round(canvas_size * 0.63)),
    )
    for eye_center_x in eye_centers:
        draw.ellipse(
            (
                eye_center_x - eye_radius_x,
                eye_y - eye_radius_y,
                eye_center_x + eye_radius_x,
                eye_y + eye_radius_y,
            ),
            fill=color,
        )

    spec = FACE_SPECS[expression]
    if spec["mouth_kind"] == "line":
        mouth_x0, mouth_y0, mouth_x1, mouth_y1 = _relative_box(canvas_size, spec["mouth_box"])
        draw.line((mouth_x0, mouth_y0, mouth_x1, mouth_y1), fill=color, width=feature_width)
    elif spec["mouth_kind"] == "chord":
        draw.chord(
            _relative_box(canvas_size, spec["mouth_box"]),
            start=spec["mouth_angles"][0],
            end=spec["mouth_angles"][1],
            fill=color,
            outline=color,
            width=feature_width,
        )
    else:
        draw.arc(
            _relative_box(canvas_size, spec["mouth_box"]),
            start=spec["mouth_angles"][0],
            end=spec["mouth_angles"][1],
            fill=color,
            width=feature_width,
        )

    return icon.resize((size, size), resample=Image.Resampling.LANCZOS)


def draw_face_strip(img: Image.Image, model: DisplayModel, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    box_width = x1 - x0 + 1
    box_height = y1 - y0 + 1
    cell_width = box_width / len(FACE_EXPRESSIONS)
    face_size = max(24, min(int(cell_width) - 10, box_height - 10))

    for index, expression in enumerate(FACE_EXPRESSIONS):
        cell_x0 = x0 + int(round(index * cell_width))
        cell_x1 = x0 + int(round((index + 1) * cell_width)) - 1
        icon_x = cell_x0 + max(0, ((cell_x1 - cell_x0 + 1) - face_size) // 2)
        icon_y = y0 + max(0, (box_height - face_size) // 2)
        icon_color = model.co2_color if model.co2_face == expression else COLOR_MUTED
        icon = render_face_icon(face_size, expression, icon_color)
        img.paste(icon, (icon_x, icon_y), icon)


class CO2FacesDisplayLayout(DisplayLayout):
    name = LAYOUT_CO2_FACES

    def render(self, model: DisplayModel, size: tuple[int, int]) -> Image.Image:
        width, height = size
        img = Image.new("RGB", (width, height), BACKGROUND)
        draw = ImageDraw.Draw(img)
        top_height = top_section_height(height)
        draw_value(draw, co2_value_box(draw, size), model.co2_value, model.co2_color)
        draw_face_strip(img, model, (0, max(0, top_height - FACE_STRIP_RAISE), width - 1, height - 1))
        return img


Co2OnlyDisplayLayout = CO2FacesDisplayLayout
