"""Shared style model and helpers for building pens/brushes."""
from __future__ import annotations

from dataclasses import dataclass, replace, field

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen, QBrush


DASHES = ("solid", "dash", "dot")

# (on, off) lengths in units of the stroke width, tuned for round caps: a
# near-zero "on" length plus the round cap gives a true round dot.
_DASH_PATTERNS = {"dash": (3.0, 2.5), "dot": (0.01, 2.0)}

# Line-end decorations. Each end of a line/arrow picks its own.
CAPS = ("none", "triangle", "stealth", "open", "circle", "bar")


def dash_pattern(dash: str, width: float):
    """(on, off) in units of the stroke width, or None for a solid stroke.
    Hairlines get a stretched pattern, otherwise the gaps close up."""
    pat = _DASH_PATTERNS.get(dash)
    if pat is None:
        return None
    k = max(1.0, 2.0 / max(width, 0.5))
    return pat[0] * k, pat[1] * k


@dataclass
class Style:
    """Visual style for an annotation. Also used as the app-wide default."""

    stroke: QColor = field(default_factory=lambda: QColor("#e53935"))
    fill: QColor = field(default_factory=lambda: QColor("#ffee58"))
    fill_enabled: bool = False
    width: int = 3
    opacity: float = 1.0  # 0..1, applied to the whole item
    dash: str = "solid"
    start_cap: str = "none"  # one of CAPS
    end_cap: str = "none"
    font_size: int = 24
    text_color: QColor = field(default_factory=lambda: QColor("#e53935"))

    def clone(self) -> "Style":
        return replace(
            self,
            stroke=QColor(self.stroke),
            fill=QColor(self.fill),
            text_color=QColor(self.text_color),
        )

    def to_dict(self) -> dict:
        return {
            "stroke": self.stroke.name(QColor.HexArgb),
            "fill": self.fill.name(QColor.HexArgb),
            "fill_enabled": self.fill_enabled,
            "width": self.width,
            "opacity": self.opacity,
            "dash": self.dash,
            "start_cap": self.start_cap,
            "end_cap": self.end_cap,
            "font_size": self.font_size,
            "text_color": self.text_color.name(QColor.HexArgb),
        }

    @staticmethod
    def from_dict(d: dict) -> "Style":
        base = Style()
        if "start_cap" in d or "end_cap" in d:
            start_cap = d.get("start_cap", base.start_cap)
            end_cap = d.get("end_cap", base.end_cap)
        else:
            # documents from before each end had its own shape: one shared
            # shape plus an on/off switch per end ("line" was the crossbar)
            shape = d.get("arrow_shape", "triangle")
            shape = {"line": "bar"}.get(shape, shape)
            start_cap = shape if d.get("arrow_start") else "none"
            end_cap = shape if d.get("arrow_end") else "none"
        if start_cap not in CAPS:
            start_cap = "none"
        if end_cap not in CAPS:
            end_cap = "none"
        return Style(
            stroke=QColor(d.get("stroke", base.stroke.name())),
            fill=QColor(d.get("fill", base.fill.name())),
            fill_enabled=d.get("fill_enabled", base.fill_enabled),
            width=d.get("width", base.width),
            opacity=d.get("opacity", base.opacity),
            dash=d.get("dash", base.dash),
            start_cap=start_cap,
            end_cap=end_cap,
            font_size=d.get("font_size", base.font_size),
            text_color=QColor(d.get("text_color", base.text_color.name())),
        )

    def pen(self) -> QPen:
        pen = QPen(QColor(self.stroke), self.width)
        pat = dash_pattern(self.dash, self.width)
        if pat is not None:
            pen.setDashPattern(list(pat))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        if self.width <= 0:
            pen.setStyle(Qt.NoPen)
        return pen

    def brush(self) -> QBrush:
        if self.fill_enabled:
            return QBrush(QColor(self.fill))
        return QBrush(Qt.NoBrush)
