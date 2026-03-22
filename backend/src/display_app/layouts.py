from __future__ import annotations

from .faces_layout import FacesDisplayLayout
from .layout_common import DisplayLayout, LAYOUT_STANDARD, make_error_frame
from .standard_layout import StandardDisplayLayout

STANDARD_LAYOUT = StandardDisplayLayout()
FACES_LAYOUT = FacesDisplayLayout()


def toggle_layout(layout: DisplayLayout) -> DisplayLayout:
    if layout.name == LAYOUT_STANDARD:
        return FACES_LAYOUT
    return STANDARD_LAYOUT
