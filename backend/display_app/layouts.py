from __future__ import annotations

from .co2_faces_layout import CO2FacesDisplayLayout, Co2OnlyDisplayLayout
from .layout_common import DisplayLayout, LAYOUT_CO2_FACES, LAYOUT_CO2_ONLY, LAYOUT_STANDARD, make_error_frame
from .standard_layout import StandardDisplayLayout

STANDARD_LAYOUT = StandardDisplayLayout()
CO2_FACES_LAYOUT = CO2FacesDisplayLayout()
CO2_ONLY_LAYOUT = CO2_FACES_LAYOUT


def toggle_layout(layout: DisplayLayout) -> DisplayLayout:
    if layout.name == LAYOUT_STANDARD:
        return CO2_FACES_LAYOUT
    return STANDARD_LAYOUT
