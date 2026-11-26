"""Visual pickers for the style panel: you choose by looking, not by reading.

  * ``SwatchRow``  - a strip of colour swatches (optionally with "none"), the
    last cell opening the full colour dialog.
  * ``IconChoice`` - a row/grid of picture buttons, one of which is current.
  * icon builders  - every picture is painted with the same code that paints
    the real items, so what a button shows is exactly what you get.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QEvent, QPointF, QRectF, QSize, Signal
from PySide6.QtGui import (
    QColor, QConicalGradient, QFont, QIcon, QPainter, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QColorDialog, QGridLayout, QToolButton, QToolTip, QWidget,
)

from . import items as I
from .model import Style

DPR = 2.0  # icons are painted at 2x so they stay crisp on HiDPI screens


def _canvas(w: int, h: int) -> tuple[QPixmap, QPainter]:
    pm = QPixmap(round(w * DPR), round(h * DPR))
    pm.setDevicePixelRatio(DPR)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    return pm, p


# --------------------------------------------------------------------------- #
#  Icons
# --------------------------------------------------------------------------- #
def _line_style(color: QColor, **kw) -> Style:
    return Style(stroke=QColor(color), **kw)


def cap_icon(cap: str, at_end: bool, color: QColor) -> QIcon:
    """A short stub of line wearing `cap` on its left (start) or right end."""
    w, h = 26, 18
    pm, p = _canvas(w, h)
    st = _line_style(color, width=2, **{"end_cap" if at_end else "start_cap": cap})
    a, b = QPointF(-4, h / 2), QPointF(w - 7, h / 2)   # runs off the far side
    if not at_end:
        a, b = QPointF(7, h / 2), QPointF(w + 4, h / 2)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawPath(I.line_path(a, b, st))
    p.end()
    return QIcon(pm)


def width_icon(width: int, color: QColor) -> QIcon:
    w, h = 22, 18
    pm, p = _canvas(w, h)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawPath(I.line_path(QPointF(5, h / 2), QPointF(w - 5, h / 2),
                           _line_style(color, width=width)))
    p.end()
    return QIcon(pm)


def dash_icon(dash: str, color: QColor) -> QIcon:
    w, h = 40, 18
    pm, p = _canvas(w, h)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawPath(I.line_path(QPointF(5, h / 2), QPointF(w - 5, h / 2),
                           _line_style(color, width=2, dash=dash)))
    p.end()
    return QIcon(pm)


def size_icon(pixels: int, color: QColor) -> QIcon:
    """A letter drawn at `pixels` tall, for the text-size picker."""
    w, h = 22, 18
    pm, p = _canvas(w, h)
    f = QFont()
    f.setPixelSize(pixels)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(color))
    p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, "A")
    p.end()
    return QIcon(pm)


def _backdrop(p: QPainter, rect: QRectF):
    """Faint 'lines of text', so see-through fills read as see-through."""
    pen = QPen(QColor("#c3c9cf"), 2)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    for i in (1, 2, 3):
        y = rect.top() + rect.height() * i / 4
        p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))


def strength_icon(fill: QColor, alpha: int) -> QIcon:
    """A patch of the current fill colour at the given opacity."""
    w, h = 40, 18
    pm, p = _canvas(w, h)
    tile = QRectF(1.5, 1.5, w - 3, h - 3)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#ffffff"))
    p.drawRoundedRect(tile, 3, 3)
    _backdrop(p, tile.adjusted(5, 0, -5, 0))
    c = QColor(fill)
    c.setAlpha(alpha)
    p.setPen(QPen(QColor("#9aa0a6"), 1))
    p.setBrush(c)
    p.drawRoundedRect(tile, 3, 3)
    p.end()
    return QIcon(pm)


PRESET_SIZE = QSize(72, 44)


def preset_icon(kind: str, style: Style) -> QIcon:
    """A thumbnail of a real item of `kind` wearing `style`, on a white
    tile standing in for the page."""
    w, h = PRESET_SIZE.width(), PRESET_SIZE.height()
    pm, p = _canvas(w, h)
    p.setPen(QPen(QColor("#b9bfc5"), 1))
    p.setBrush(QColor("#ffffff"))
    p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 5, 5)
    p.setClipRect(QRectF(1, 1, w - 2, h - 2))
    if kind in ("rect", "ellipse"):
        _backdrop(p, QRectF(16, 6, w - 32, h - 12))
        p.setOpacity(style.opacity)
        item = (I.RectItem if kind == "rect" else I.EllipseItem)(style)
        item._rect = QRectF(11, 9, w - 22, h - 18)
        item.paint_content(p)
    elif kind in ("line", "arrow"):
        if style.opacity < 1:
            _backdrop(p, QRectF(16, 6, w - 32, h - 12))
        p.setOpacity(style.opacity)
        s = 0.8  # a little smaller than life, so thick lines still fit
        p.scale(s, s)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(style.stroke))
        p.drawPath(I.line_path(QPointF(13 / s, (h - 11) / s),
                               QPointF((w - 13) / s, 11 / s), style))
    elif kind == "text":
        s = 0.62
        item = I.TextItem(style, "Abc")
        r = item.logical_rect()
        p.setOpacity(style.opacity)
        p.translate((w - r.width() * s) / 2, (h - r.height() * s) / 2)
        p.scale(s, s)
        item.paint_content(p)
    elif kind == "callout":
        s = 0.42
        st = style.clone()
        st.font_size = 30
        item = I.CalloutItem(st, "Abc")
        item._rect = QRectF(0, 0, 128, 60)
        item._tail = QPointF(30, 92)
        p.setOpacity(style.opacity)
        p.translate((w - 128 * s) / 2, 3)
        p.scale(s, s)
        item.paint_content(p)
    p.end()
    return QIcon(pm)


# --------------------------------------------------------------------------- #
#  Picture buttons
# --------------------------------------------------------------------------- #
_CHIP_CSS = (
    "QToolButton{background:palette(base);border:1px solid palette(midlight);"
    "border-radius:5px;padding:1px;}"
    "QToolButton:hover{border-color:palette(dark);}"
    "QToolButton:checked{border:2px solid palette(highlight);padding:0px;}"
)
_TILE_CSS = (
    "QToolButton{background:transparent;border:2px solid transparent;"
    "border-radius:7px;padding:0px;}"
    "QToolButton:hover{border-color:palette(mid);}"
    "QToolButton:checked{border-color:palette(highlight);}"
)


class IconChoice(QWidget):
    """A row (or grid) of picture buttons; at most one is checked."""

    chosen = Signal(object)  # the value of the button just clicked

    def __init__(self, icon_size: QSize, columns: int = 0, tiles: bool = False):
        super().__init__()
        self._icon_size = icon_size
        self._columns = columns
        self._css = _TILE_CSS if tiles else _CHIP_CSS
        self._buttons: list[tuple[object, QToolButton]] = []
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(4 if tiles else 2)

    def set_options(self, options):
        """`options` is a list of (value, icon, tooltip)."""
        for _, b in self._buttons:
            self._grid.removeWidget(b)
            b.hide()  # deleteLater alone leaves it painted for a moment
            b.deleteLater()
        self._buttons = []
        pad = 4 if self._css is _TILE_CSS else 6
        for i, (value, icon, tip) in enumerate(options):
            b = QToolButton()
            b.setCheckable(True)
            b.setIcon(icon)
            b.setIconSize(self._icon_size)
            b.setFixedSize(self._icon_size.width() + pad,
                           self._icon_size.height() + pad)
            b.setToolTip(tip)
            b.setStyleSheet(self._css)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, v=value: self._clicked(v))
            row, col = divmod(i, self._columns) if self._columns else (0, i)
            self._grid.addWidget(b, row, col)
            self._buttons.append((value, b))
        return self

    def set_icon(self, value, icon: QIcon):
        for v, b in self._buttons:
            if v == value:
                b.setIcon(icon)

    def set_value(self, value):
        """Check the button for `value`; none if no button has it."""
        for v, b in self._buttons:
            b.setChecked(v == value)

    def value(self):
        for v, b in self._buttons:
            if b.isChecked():
                return v
        return None

    def _clicked(self, value):
        self.set_value(value)
        self.chosen.emit(value)


# --------------------------------------------------------------------------- #
#  Colour swatches
# --------------------------------------------------------------------------- #
class SwatchRow(QWidget):
    """One-click colours. Cells, left to right: an optional "none", the
    palette, and a last cell that opens the colour dialog for anything else."""

    picked = Signal(object)  # a QColor, or None for "none"

    CELL = 24
    _NONE, _CUSTOM = "none", "custom"

    def __init__(self, palette, allow_none: bool = False, alpha: bool = False,
                 none_tip: str = "None"):
        super().__init__()
        self._names = {}
        self._cells: list = [self._NONE] if allow_none else []
        for name, hexcode in palette:
            c = QColor(hexcode)
            self._cells.append(c)
            self._names[c.rgb()] = name
        self._cells.append(self._CUSTOM)
        self._alpha = alpha
        self._none_tip = none_tip
        self._current: QColor | None = None
        self._has_current = False
        self.setFixedSize(len(self._cells) * self.CELL, self.CELL)
        self.setCursor(Qt.PointingHandCursor)

    # -- state ------------------------------------------------------------
    def set_current(self, color: QColor | None):
        """Mark the cell for `color` (None marks the "none" cell)."""
        self._current = QColor(color) if color is not None else None
        self._has_current = True
        self.update()

    def _current_index(self) -> int | None:
        if not self._has_current:
            return None
        if self._current is None:
            return 0 if self._cells[0] is self._NONE else None
        for i, cell in enumerate(self._cells):
            if isinstance(cell, QColor) and cell.rgb() == self._current.rgb():
                return i
        return len(self._cells) - 1  # not in the palette: the custom cell

    # -- painting ---------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        current = self._current_index()
        for i, cell in enumerate(self._cells):
            box = QRectF(i * self.CELL + 3.5, 3.5, self.CELL - 7, self.CELL - 7)
            p.setPen(QPen(QColor("#8a9096"), 1))
            if cell is self._NONE:
                p.setBrush(QColor("#ffffff"))
                p.drawRoundedRect(box, 3, 3)
                p.setPen(QPen(QColor("#e53935"), 2))
                p.drawLine(box.bottomLeft() + QPointF(2, -2),
                           box.topRight() + QPointF(-2, 2))
            elif cell is self._CUSTOM:
                if i == current and self._current is not None:
                    p.setBrush(QColor(self._current.rgb()))
                else:
                    g = QConicalGradient(box.center(), 0)
                    for k, hue in enumerate(range(0, 361, 60)):
                        g.setColorAt(k / 6, QColor.fromHsv(hue % 360, 200, 250))
                    p.setBrush(g)
                p.drawRoundedRect(box, 3, 3)
            else:
                p.setBrush(cell)
                p.drawRoundedRect(box, 3, 3)
            if i == current:
                p.setPen(QPen(self.palette().highlight().color(), 2))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(box.adjusted(-2.5, -2.5, 2.5, 2.5), 5, 5)
        p.end()

    # -- interaction ------------------------------------------------------
    def _cell_at(self, x: float):
        i = int(x // self.CELL)
        return self._cells[i] if 0 <= i < len(self._cells) else None

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        cell = self._cell_at(event.position().x())
        if cell is None:
            return
        if cell is self._NONE:
            self.picked.emit(None)
        elif cell is self._CUSTOM:
            options = (QColorDialog.ShowAlphaChannel if self._alpha
                       else QColorDialog.ColorDialogOptions())
            start = self._current if self._current is not None else QColor("#e53935")
            c = QColorDialog.getColor(start, self.window(), "Select colour", options)
            if c.isValid():
                self.picked.emit(c)
        else:
            self.picked.emit(QColor(cell))

    def event(self, ev):
        if ev.type() == QEvent.ToolTip:
            cell = self._cell_at(ev.pos().x())
            if cell is self._NONE:
                tip = self._none_tip
            elif cell is self._CUSTOM:
                tip = "Other colour…"
            elif cell is not None:
                tip = self._names.get(cell.rgb(), cell.name())
            else:
                tip = ""
            QToolTip.showText(ev.globalPos(), tip, self)
            return True
        return super().event(ev)
