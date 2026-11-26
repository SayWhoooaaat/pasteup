"""Contextual style panel.

Shows only the settings that make sense for what the user is doing: the
current selection if there is one, otherwise the active drawing tool. Every
tool remembers its own style (Canvas.tool_styles), and edits made while items
are selected also update the matching tool's memory, so the next item drawn
looks like the one just tweaked.

Everything is chosen by picture rather than by text (see pickers.py): a grid
of ready-made quick styles on top, then colour swatches, line thicknesses,
dash styles and arrow ends drawn as they will actually look.

Context keys are the drawing-tool ids and the item kinds — the two
vocabularies deliberately overlap ("rect", "text", ...). Lines and arrows are
the same item with the same options (ends included), but each carries a
permanent kind tag naming the tool preset that created it, and an item's
edits only ever feed back into that preset's memory — so a line remembers
its own end choices without ever rewriting the Arrow preset, and vice versa.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QSlider, QSpinBox,
    QLabel, QToolButton, QFrame,
)

from . import pickers as P
from . import presets
from .model import Style, CAPS, DASHES


# Which setting groups each context gets (opacity is shown for all of them).
GROUPS = {
    "rect": ("stroke", "fill"),
    "ellipse": ("stroke", "fill"),
    "line": ("stroke", "ends"),
    "arrow": ("stroke", "ends"),
    "text": ("text",),
    "callout": ("stroke", "fill", "text"),
    "image": (),
}
TITLES = {
    "rect": "Rectangle", "ellipse": "Ellipse", "line": "Line",
    "arrow": "Arrow", "text": "Text", "callout": "Callout", "image": "Image",
}
CAP_TIPS = {
    "none": "Plain end", "triangle": "Arrowhead", "stealth": "Swept arrowhead",
    "open": "Open arrowhead", "circle": "Dot", "bar": "Bar",
}
WIDTHS = (1, 2, 3, 5, 8)
TEXT_SIZES = ((16, 9), (24, 12), (36, 15), (56, 18))  # (font px, icon px)

PANEL_WIDTH = 270


class PropertiesPanel(QWidget):
    def __init__(self, canvas):
        super().__init__()
        self.canvas = canvas
        self._loading = False
        self._style = Style()      # the style currently shown
        self._preset_kind = None   # which kind the quick-style grid shows
        self._preset_icons = {}    # kind -> its thumbnails, painted once
        self.setFixedWidth(PANEL_WIDTH)
        ink = self.palette().windowText().color()

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignTop)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(8)

        # tool buttons live here, installed by the main window via
        # set_tool_actions() — the actions own the shortcuts and the
        # exclusive checked state, the buttons only mirror them
        self._tools_row = QHBoxLayout()
        self._tools_row.setSpacing(2)
        outer.addLayout(self._tools_row)
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        outer.addWidget(sep)

        self.header = QLabel()
        f = self.header.font()
        f.setBold(True)
        self.header.setFont(f)
        outer.addWidget(self.header)

        self.hint = QLabel(
            "Pick a tool above, or select an item, to style it.\n\n"
            "Esc returns to the Select tool. Right-click an item for "
            "copy, arrange and rotate.")
        self.hint.setWordWrap(True)
        outer.addWidget(self.hint)

        # -- quick styles ---------------------------------------------------
        self.s_presets, lay = self._section("Quick styles")
        self.presets = P.IconChoice(P.PRESET_SIZE, columns=3, tiles=True)
        lay.addWidget(self.presets, 0, Qt.AlignLeft)
        outer.addWidget(self.s_presets)

        # -- outline / line: colour, [start], width, dash, [end] ------------
        self.s_stroke, lay = self._section("Outline")
        self.stroke_caption = self.s_stroke.findChild(QLabel)
        self.stroke = P.SwatchRow(presets.PALETTE)
        lay.addWidget(self.stroke)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        lay.addLayout(grid)

        cap_size = QSize(26, 18)
        self.start_cap = P.IconChoice(cap_size).set_options(
            [(c, P.cap_icon(c, False, ink), CAP_TIPS[c]) for c in CAPS])
        self.end_cap = P.IconChoice(cap_size).set_options(
            [(c, P.cap_icon(c, True, ink), CAP_TIPS[c]) for c in CAPS])
        self.width_pick = P.IconChoice(QSize(22, 18)).set_options(
            [(w, P.width_icon(w, ink), f"{w} px") for w in WIDTHS])
        self.width_spin = QSpinBox()
        self.width_spin.setRange(0, 60)
        self.width_spin.setFixedWidth(52)
        self.width_spin.setToolTip("Thickness in pixels (0 = no outline)")
        self.dash = P.IconChoice(QSize(40, 18)).set_options(
            [(d, P.dash_icon(d, ink), d.title()) for d in DASHES])

        self._l_start = self._row(grid, 0, "Start", self.start_cap)
        self._row(grid, 1, "Width", self.width_pick, self.width_spin)
        self._row(grid, 2, "Style", self.dash)
        self._l_end = self._row(grid, 3, "End", self.end_cap)
        outer.addWidget(self.s_stroke)

        # -- fill -------------------------------------------------------------
        self.s_fill, lay = self._section("Fill")
        self.fill = P.SwatchRow(presets.PALETTE, allow_none=True, alpha=True,
                                none_tip="No fill")
        lay.addWidget(self.fill)
        self.fill_strength = P.IconChoice(QSize(40, 18)).set_options(
            [("solid", P.strength_icon(self._style.fill, 255), "Solid"),
             ("tint", P.strength_icon(self._style.fill, presets.TINT_ALPHA),
              "See-through")])
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.fill_strength)
        row.addStretch(1)
        lay.addLayout(row)
        outer.addWidget(self.s_fill)

        # -- text -------------------------------------------------------------
        self.s_text, lay = self._section("Text")
        self.text_color = P.SwatchRow(presets.PALETTE)
        lay.addWidget(self.text_color)
        self.size_pick = P.IconChoice(QSize(22, 18)).set_options(
            [(px, P.size_icon(icon_px, ink), f"{px} px")
             for px, icon_px in TEXT_SIZES])
        self.font_size = QSpinBox()
        self.font_size.setRange(6, 200)
        self.font_size.setFixedWidth(52)
        self.font_size.setToolTip("Text size in pixels")
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        lay.addLayout(grid)
        self._row(grid, 0, "Size", self.size_pick, self.font_size)
        outer.addWidget(self.s_text)

        # -- opacity ----------------------------------------------------------
        self.s_opacity, lay = self._section("Opacity")
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(10, 100)
        self.opacity_lbl = QLabel("100%")
        self.opacity_lbl.setFixedWidth(38)
        self.opacity_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(self.opacity, 1)
        row.addWidget(self.opacity_lbl)
        lay.addLayout(row)
        outer.addWidget(self.s_opacity)
        outer.addStretch(1)

        self._groups = {"stroke": self.s_stroke, "fill": self.s_fill,
                        "text": self.s_text}

        self.presets.chosen.connect(self._preset_picked)
        self.stroke.picked.connect(lambda c: self._apply(stroke=c))
        self.width_pick.chosen.connect(lambda v: self._apply(width=v))
        self.width_spin.valueChanged.connect(lambda v: self._apply(width=v))
        self.dash.chosen.connect(lambda v: self._apply(dash=v))
        self.start_cap.chosen.connect(lambda v: self._apply(start_cap=v))
        self.end_cap.chosen.connect(lambda v: self._apply(end_cap=v))
        self.fill.picked.connect(self._fill_picked)
        self.fill_strength.chosen.connect(self._strength_picked)
        self.text_color.picked.connect(lambda c: self._apply(text_color=c))
        self.size_pick.chosen.connect(lambda v: self._apply(font_size=v))
        self.font_size.valueChanged.connect(lambda v: self._apply(font_size=v))
        self.opacity.valueChanged.connect(
            lambda v: self._apply(opacity=v / 100.0))

        canvas.selectionChanged.connect(self.refresh)
        canvas.toolChanged.connect(self.refresh)
        self.refresh()

    # -- construction helpers ---------------------------------------------
    @staticmethod
    def _section(title: str):
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(4)
        caption = QLabel(title)
        caption.setStyleSheet("color:#8a9096;font-size:11px;font-weight:bold;")
        lay.addWidget(caption)
        return box, lay

    @staticmethod
    def _row(grid: QGridLayout, row: int, label: str, *widgets) -> list:
        """Add a labelled row; returns its widgets so it can be hidden."""
        lbl = QLabel(label)
        lbl.setFixedWidth(34)
        grid.addWidget(lbl, row, 0)
        holder = QWidget()
        h = QHBoxLayout(holder)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        for w in widgets:
            h.addWidget(w)
        h.addStretch(1)
        grid.addWidget(holder, row, 1)
        return [lbl, holder]

    def set_tool_actions(self, actions):
        """Install the tool QActions as a row of icon buttons at the top."""
        for a in actions:
            b = QToolButton()
            b.setDefaultAction(a)
            b.setAutoRaise(True)
            b.setIconSize(QSize(22, 22))
            b.setFixedSize(34, 32)
            b.setFocusPolicy(Qt.NoFocus)
            self._tools_row.addWidget(b)
        self._tools_row.addStretch(1)

    # -- write --------------------------------------------------------------
    def _apply(self, **fields):
        """Apply changed settings to the selection (or, with nothing
        selected, to the active tool's memory)."""
        if self._loading:
            return

        def put(style: Style):
            for name, value in fields.items():
                setattr(style, name,
                        QColor(value) if isinstance(value, QColor) else value)

        sel = self.canvas.selected_items()
        if sel:
            for it in sel:
                st = it.get_style()
                put(st)
                it.set_style(st)
            for key in {it.kind for it in sel}:
                put(self.canvas.style_for(key))
        elif self.canvas.tool in self.canvas.tool_styles:
            put(self.canvas.style_for(self.canvas.tool))
        self.refresh()

    def _preset_picked(self, index: int):
        if self._preset_kind is None:
            return
        preset = presets.PRESETS[self._preset_kind][index]
        self._apply(**presets.fields_of(self._preset_kind, preset))

    def _fill_picked(self, color):
        if color is None:
            self._apply(fill_enabled=False)
            return
        color = QColor(color)
        if color.alpha() == 255 and self.fill_strength.value() == "tint":
            color.setAlpha(presets.TINT_ALPHA)
        self._apply(fill=color, fill_enabled=True)

    def _strength_picked(self, strength: str):
        color = QColor(self._style.fill)
        color.setAlpha(presets.TINT_ALPHA if strength == "tint" else 255)
        self._apply(fill=color, fill_enabled=True)

    # -- read -----------------------------------------------------------------
    def refresh(self, *_):
        sel = self.canvas.selected_items()
        if sel:
            kinds = {it.kind for it in sel}
            title = (TITLES.get(sel[0].kind, sel[0].kind.title())
                     if len(sel) == 1 else f"{len(sel)} items")
            groups = set().union(*(GROUPS.get(k, ()) for k in kinds))
            # quick styles only make sense for one kind of item at a time
            kind = next(iter(kinds)) if len(kinds) == 1 else None
            self._show(title, groups, sel[0].get_style(), kind)
        elif self.canvas.tool in GROUPS:
            tool = self.canvas.tool
            self._show(TITLES[tool], set(GROUPS[tool]),
                       self.canvas.style_for(tool), tool)
        else:
            self._show(None, set(), None, None)

    def _show(self, title, groups: set, style: Style | None, kind):
        self.hint.setVisible(title is None)
        self.header.setVisible(title is not None)
        self.header.setText(title or "")
        for name, box in self._groups.items():
            box.setVisible(name in groups)
        for w in self._l_start + self._l_end:
            w.setVisible("ends" in groups)
        self.stroke_caption.setText("Line" if "ends" in groups else "Outline")
        self.s_opacity.setVisible(title is not None)

        if kind not in presets.PRESETS:
            kind = None
        self.s_presets.setVisible(kind is not None)
        if kind is not None and kind != self._preset_kind:
            if kind not in self._preset_icons:
                self._preset_icons[kind] = [
                    P.preset_icon(kind, st) for st in presets.PRESETS[kind]]
            self.presets.set_options(
                [(i, icon, "") for i, icon in
                 enumerate(self._preset_icons[kind])])
        self._preset_kind = kind
        if style is not None:
            self._load(style, kind)

    def _load(self, style: Style, kind):
        self._loading = True
        try:
            self._style = style.clone()
            if kind is not None:
                self.presets.set_value(presets.matching(kind, style))
            self.stroke.set_current(style.stroke)
            self.width_pick.set_value(style.width)
            self.width_spin.setValue(style.width)
            self.dash.set_value(style.dash)
            self.start_cap.set_value(style.start_cap)
            self.end_cap.set_value(style.end_cap)
            self.fill.set_current(style.fill if style.fill_enabled else None)
            tinted = style.fill.alpha() < 255
            self.fill_strength.set_icon(
                "solid", P.strength_icon(style.fill, 255))
            self.fill_strength.set_icon(
                "tint", P.strength_icon(
                    style.fill,
                    style.fill.alpha() if tinted else presets.TINT_ALPHA))
            self.fill_strength.set_value(
                None if not style.fill_enabled
                else "tint" if tinted else "solid")
            self.text_color.set_current(style.text_color)
            self.size_pick.set_value(style.font_size)
            self.font_size.setValue(style.font_size)
            self.opacity.setValue(round(style.opacity * 100))
            self.opacity_lbl.setText(f"{self.opacity.value()}%")
        finally:
            self._loading = False
