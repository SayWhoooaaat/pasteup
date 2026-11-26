"""Quick styles: a handful of ready-made looks per tool.

The style panel shows these as a grid of example thumbnails, so the common
cases (a red outline, a yellow highlight, a blue arrow...) are one click
instead of several trips through colour dialogs and spin boxes.

A preset only owns the fields listed for its kind in ``FIELDS``; everything
else on the item is left alone. Each preset is a full ``Style`` so the same
object can be painted as a thumbnail and compared with an item's style.
"""
from __future__ import annotations

from PySide6.QtGui import QColor

from .model import Style

# The colours offered as one-click swatches (name, hex).
PALETTE = (
    ("Red", "#e53935"), ("Orange", "#fb8c00"), ("Yellow", "#fdd835"),
    ("Green", "#43a047"), ("Blue", "#1e88e5"), ("Purple", "#8e24aa"),
    ("Black", "#212121"), ("White", "#ffffff"),
)
RED, ORANGE, YELLOW, GREEN, BLUE, PURPLE, BLACK, WHITE = (c for _, c in PALETTE)

TINT_ALPHA = 70  # alpha of a "see-through" fill (0-255)

_SHAPE = ("stroke", "width", "dash", "fill", "fill_enabled", "opacity")
_LINE = ("stroke", "width", "dash", "start_cap", "end_cap", "opacity")
FIELDS = {
    "rect": _SHAPE,
    "ellipse": _SHAPE,
    "line": _LINE,
    "arrow": _LINE,
    "text": ("text_color", "font_size", "opacity"),
    # a callout preset leaves the font size alone
    "callout": ("stroke", "width", "dash", "fill", "fill_enabled",
                "text_color", "opacity"),
}


def _tint(color: str, alpha: int = TINT_ALPHA) -> QColor:
    c = QColor(color)
    c.setAlpha(alpha)
    return c


def _style(**kw) -> Style:
    for key in ("stroke", "fill", "text_color"):
        if isinstance(kw.get(key), str):
            kw[key] = QColor(kw[key])
    if "fill" in kw:
        kw.setdefault("fill_enabled", True)
    return Style(**kw)


_SHAPES = [
    _style(stroke=RED),
    _style(stroke=BLUE),
    _style(stroke=GREEN),
    _style(stroke=RED, fill=_tint(RED)),
    _style(stroke=BLUE, fill=_tint(BLUE)),
    _style(stroke=YELLOW, width=0, fill=_tint("#ffeb3b", 120)),  # highlighter
    _style(stroke=RED, dash="dash"),
    _style(stroke=BLACK, width=2, fill=WHITE),                   # label box
    _style(stroke=BLACK, width=0, fill=BLACK),                   # redaction
]

_LINES = [
    _style(stroke=RED),
    _style(stroke=BLUE),
    _style(stroke=BLACK, width=2),
    _style(stroke=RED, width=6),
    _style(stroke="#ffeb3b", width=14, opacity=0.5),             # highlighter
    _style(stroke=RED, dash="dash"),
    _style(stroke=BLACK, width=2, dash="dot"),
    _style(stroke=BLACK, width=2, start_cap="bar", end_cap="bar"),
    _style(stroke=BLUE, start_cap="circle", end_cap="circle"),
]

_ARROWS = [
    _style(stroke=RED, end_cap="triangle"),
    _style(stroke=BLUE, end_cap="triangle"),
    _style(stroke=BLACK, width=2, end_cap="triangle"),
    _style(stroke=RED, width=6, end_cap="triangle"),
    _style(stroke=RED, start_cap="triangle", end_cap="triangle"),
    _style(stroke=RED, dash="dash", end_cap="triangle"),
    _style(stroke=BLUE, end_cap="open"),
    _style(stroke=RED, start_cap="circle", end_cap="triangle"),
    _style(stroke=BLACK, width=2, end_cap="stealth"),
]

_TEXTS = [
    _style(text_color=color, font_size=size)
    for size in (16, 24, 40) for color in (RED, BLUE, BLACK)
]

_CALLOUTS = [
    _style(stroke=RED, fill="#fffde7", text_color=RED),
    _style(stroke=BLACK, width=2, fill=WHITE, text_color=BLACK),
    _style(stroke=BLUE, fill=WHITE, text_color=BLUE),
    _style(stroke=RED, fill=RED, text_color=WHITE),
    _style(stroke=BLUE, fill=BLUE, text_color=WHITE),
    _style(stroke=BLACK, fill=BLACK, text_color=WHITE),
    _style(stroke=BLACK, width=2, fill=YELLOW, text_color=BLACK),
    _style(stroke=GREEN, fill=GREEN, text_color=WHITE),
    _style(stroke=ORANGE, fill=ORANGE, text_color=WHITE),
]

PRESETS = {
    "rect": _SHAPES,
    "ellipse": _SHAPES,
    "line": _LINES,
    "arrow": _ARROWS,
    "text": _TEXTS,
    "callout": _CALLOUTS,
}


def fields_of(kind: str, style: Style) -> dict:
    """The values a preset of this kind would set, taken from `style`."""
    out = {}
    for name in FIELDS.get(kind, ()):
        value = getattr(style, name)
        out[name] = QColor(value) if isinstance(value, QColor) else value
    return out


def matching(kind: str, style: Style) -> int | None:
    """Index of the preset `style` currently looks like, if any."""
    current = fields_of(kind, style)
    for i, preset in enumerate(PRESETS.get(kind, ())):
        if fields_of(kind, preset) == current:
            return i
    return None
