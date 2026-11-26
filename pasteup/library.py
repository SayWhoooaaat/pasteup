"""On-disk document library plus the filmstrip and gallery widgets.

A *document* is stored as a ``.snagdoc`` JSON file (page + all items, with
images embedded as base64 PNG) alongside a ``.png`` thumbnail used by the
filmstrip and gallery.

Display order is **creation order** (newest first), never modification order —
editing a document must not make it jump around. The filename encodes its
creation time, so re-saving can't change it. A manual order (set by dragging
thumbnails) is persisted in ``order.json`` and takes precedence.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import time

from PySide6.QtCore import Qt, QSize, Signal, QStandardPaths, QTimer
from PySide6.QtGui import QIcon, QPixmap, QImage
from PySide6.QtWidgets import (
    QApplication, QListWidget, QListWidgetItem, QDialog, QVBoxLayout, QLabel,
    QMenu, QMessageBox,
)


THUMB = QSize(120, 96)
DOC_EXT = ".snagdoc"
ORDER_FILE = "order.json"

_NAME_RE = re.compile(r"^doc-(\d{8})-(\d{6})")


def library_dir() -> str:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    path = os.path.join(base or os.path.expanduser("~/.pasteup"), "library")
    # One-time migration: the app used to be called "Annotator" (with an
    # organizationName, hence the doubled directory). Only runs for the real
    # app identity, so test runs with other app names can't touch it.
    legacy = os.path.expanduser("~/.local/share/Annotator/Annotator/library")
    if (os.path.basename(base or "") == "PasteUp"
            and not os.path.isdir(path) and os.path.isdir(legacy)):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        shutil.move(legacy, path)
    os.makedirs(path, exist_ok=True)
    return path


def new_document_path() -> str:
    ts = time.strftime("%Y%m%d-%H%M%S")
    name = f"doc-{ts}-{int(time.time() * 1000) % 1000:03d}{DOC_EXT}"
    return os.path.join(library_dir(), name)


def thumb_path(doc_path: str) -> str:
    return doc_path[: -len(DOC_EXT)] + ".png"


def created_time(doc_path: str) -> float:
    """When the document was created. Taken from the filename, so that saving
    (which updates mtime) can never reorder the library."""
    m = _NAME_RE.match(os.path.basename(doc_path))
    if m:
        try:
            dt = datetime.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
            return dt.timestamp()
        except ValueError:
            pass
    try:
        return os.path.getctime(doc_path)
    except OSError:
        return 0.0


# -- manual order ---------------------------------------------------------
def _order_path() -> str:
    return os.path.join(library_dir(), ORDER_FILE)


def read_order() -> list[str]:
    try:
        with open(_order_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return [str(x) for x in data] if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def write_order(names: list[str]):
    try:
        with open(_order_path(), "w", encoding="utf-8") as f:
            json.dump(list(names), f)
    except OSError:
        pass


# -- document IO ----------------------------------------------------------
def write_document(path: str, data: dict, thumbnail: QImage | None):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)
    if thumbnail is not None and not thumbnail.isNull():
        thumbnail.save(thumb_path(path), "PNG")


def read_document(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_documents() -> list[str]:
    """Documents in display order: manual order first (as dragged), with any
    not-yet-ordered documents newest-created first at the front."""
    d = library_dir()
    by_name = {f: os.path.join(d, f) for f in os.listdir(d) if f.endswith(DOC_EXT)}
    ordered = [by_name.pop(n) for n in read_order() if n in by_name]
    fresh = sorted(by_name.values(), key=created_time, reverse=True)
    result = fresh + ordered
    if fresh:  # pin new documents into the order so it stays stable
        write_order([os.path.basename(p) for p in result])
    return result


def duplicate_document(path: str) -> str:
    """Copy a document (and its thumbnail); the copy is placed right after
    the original in the display order. Returns the copy's path."""
    names = [os.path.basename(p) for p in list_documents()]
    new = new_document_path()
    while os.path.exists(new):  # two copies within the same millisecond
        time.sleep(0.002)
        new = new_document_path()
    shutil.copyfile(path, new)
    if os.path.exists(thumb_path(path)):
        shutil.copyfile(thumb_path(path), thumb_path(new))
    name = os.path.basename(path)
    at = names.index(name) + 1 if name in names else 0
    names.insert(at, os.path.basename(new))
    write_order(names)
    return new


def delete_document(path: str):
    for p in (path, thumb_path(path)):
        try:
            os.remove(p)
        except OSError:
            pass
    name = os.path.basename(path)
    order = read_order()
    if name in order:
        order.remove(name)
        write_order(order)


def _label(doc_path: str) -> str:
    return time.strftime("%b %d  %H:%M", time.localtime(created_time(doc_path)))


_icon_cache: dict = {}  # (thumbnail path, w, h) -> (mtime, QIcon)


def _icon(doc_path: str, size: QSize) -> QIcon:
    """The document's thumbnail, re-read only when its file has changed —
    the strip is refreshed on every auto-save."""
    thumb = thumb_path(doc_path)
    try:
        mtime = os.stat(thumb).st_mtime_ns
    except OSError:
        return QIcon()
    key = (thumb, size.width(), size.height())
    hit = _icon_cache.get(key)
    if hit is not None and hit[0] == mtime:
        return hit[1]
    pix = QPixmap(thumb)
    icon = QIcon()
    if not pix.isNull():
        pix = pix.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        icon.addPixmap(pix, QIcon.Normal)
        # same picture when selected: the default blue wash hides it, and
        # the highlighted label already shows which document is open
        icon.addPixmap(pix, QIcon.Selected)
    _icon_cache[key] = (mtime, icon)
    return icon


class _DocList(QListWidget):
    docActivated = Signal(str)
    docDeleted = Signal(str)
    docDuplicateRequested = Signal(str)

    def __init__(self, icon_size: QSize = THUMB):
        super().__init__()
        self._isize = icon_size
        self._current_path = None   # the document open in the editor
        self._mute_clicks = False
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(icon_size)
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setSelectionMode(QListWidget.SingleSelection)
        self.itemActivated.connect(self._activated)
        self.itemClicked.connect(self._activated)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

    def _activated(self, item: QListWidgetItem):
        if not self._mute_clicks:
            self.docActivated.emit(item.data(Qt.UserRole))

    def set_current(self, path: str | None):
        """Highlight the document that is open in the editor."""
        self._current_path = path
        self._mark_current()

    def _mark_current(self):
        for i in range(self.count()):
            if self.item(i).data(Qt.UserRole) == self._current_path:
                self.setCurrentRow(i)
                return
        self.setCurrentRow(-1)
        self.clearSelection()

    # -- right-click ------------------------------------------------------
    def _context_menu(self, pos):
        item = self.itemAt(pos)
        if item is None:
            return
        path = item.data(Qt.UserRole)
        menu = QMenu(self)
        act_open = menu.addAction("Open")
        act_dup = menu.addAction("Duplicate")
        menu.addSeparator()
        act_del = menu.addAction("Delete…")
        chosen = menu.exec(self.viewport().mapToGlobal(pos))
        if chosen == act_open:
            self.docActivated.emit(path)
        elif chosen == act_dup:
            self.docDuplicateRequested.emit(path)
        elif chosen == act_del:
            self._confirm_delete(path)

    def _confirm_delete(self, path: str):
        answer = QMessageBox.question(
            self, "Delete document",
            f"Permanently delete “{_label(path)}”?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        delete_document(path)
        self.reload()
        self.docDeleted.emit(path)

    def reload(self, paths: list[str] | None = None):
        paths = list(paths if paths is not None else list_documents())
        shown = [self.item(i).data(Qt.UserRole) for i in range(self.count())]
        if shown == paths:
            # same documents in the same order (the usual auto-save case):
            # just refresh the pictures, keeping scroll position and all
            for i, p in enumerate(paths):
                self.item(i).setIcon(_icon(p, self._isize))
        else:
            scroll = self.horizontalScrollBar().value()
            self.clear()
            for p in paths:
                it = QListWidgetItem(_icon(p, self._isize), _label(p))
                it.setData(Qt.UserRole, p)
                it.setToolTip(os.path.basename(p))
                self.addItem(it)
            self.horizontalScrollBar().setValue(scroll)
        self._mark_current()


class Filmstrip(_DocList):
    """Horizontal recent-documents strip. Drag a thumbnail sideways to
    rearrange: it follows the cursor from slot to slot, the others making
    room as it passes (like reordering browser tabs)."""

    MAX = 40
    CELL = QSize(THUMB.width() + 14, THUMB.height() + 22)
    EDGE = 28  # px from either end where a drag starts scrolling the strip
    orderChanged = Signal()

    def __init__(self):
        super().__init__(THUMB)
        self.setFlow(QListWidget.LeftToRight)
        self.setWrapping(False)
        self.setGridSize(self.CELL)       # equal slots: reordering is exact
        self.setUniformItemSizes(True)
        self.setFixedHeight(THUMB.height() + 40)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollMode(QListWidget.ScrollPerPixel)
        self.horizontalScrollBar().setSingleStep(self.CELL.width() // 3)
        # Reordering is done by hand in the mouse handlers below rather than
        # with Qt's item drag-and-drop, which in icon mode moves pictures
        # around without changing the underlying order.
        self.setDragEnabled(False)
        self._press_item = None
        self._press_pos = None
        self._dragging = False
        self._drag_x = 0
        self._reload_pending = False
        self._edge_timer = QTimer(self)
        self._edge_timer.setInterval(30)
        self._edge_timer.timeout.connect(self._edge_scroll)

    def reload(self, paths=None):
        if self._press_item is not None:
            # the mouse is down on a thumbnail (possibly mid-drag);
            # rebuilding now would pull it out from under the cursor
            self._reload_pending = True
            return
        super().reload(
            (paths if paths is not None else list_documents())[: self.MAX])

    def wheelEvent(self, event):
        # a plain mouse wheel scrolls the strip sideways
        d = event.angleDelta()
        delta = d.x() if abs(d.x()) > abs(d.y()) else d.y()
        bar = self.horizontalScrollBar()
        bar.setValue(bar.value() - delta)
        event.accept()

    # -- drag to rearrange --------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_item = self.itemAt(event.position().toPoint())
            self._press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press_item is None or not (event.buttons() & Qt.LeftButton):
            return super().mouseMoveEvent(event)
        pos = event.position().toPoint()
        if not self._dragging:
            if ((pos - self._press_pos).manhattanLength()
                    < QApplication.startDragDistance()):
                return
            self._dragging = True
            self.viewport().setCursor(Qt.ClosedHandCursor)
            self.setCurrentItem(self._press_item)
        self._drag_x = pos.x()
        self._move_dragged()
        near_edge = (pos.x() < self.EDGE
                     or pos.x() > self.viewport().width() - self.EDGE)
        if near_edge and not self._edge_timer.isActive():
            self._edge_timer.start()
        elif not near_edge:
            self._edge_timer.stop()
        event.accept()

    def _move_dragged(self):
        """Put the dragged thumbnail into the slot under the cursor."""
        item = self._press_item
        x = self._drag_x + self.horizontalScrollBar().value()
        target = max(0, min(self.count() - 1, x // self.CELL.width()))
        row = self.row(item)
        if row < 0 or target == row:
            return
        self.takeItem(row)
        self.insertItem(target, item)
        self.setCurrentItem(item)

    def _edge_scroll(self):
        bar = self.horizontalScrollBar()
        step = -14 if self._drag_x < self.EDGE else 14
        bar.setValue(bar.value() + step)
        self._move_dragged()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._end_drag()
        # releasing over the thumbnail just dragged must not also open it
        self._mute_clicks = True
        try:
            super().mouseReleaseEvent(event)
        finally:
            self._mute_clicks = False

    def _end_drag(self):
        was_dragging = self._dragging
        clicked = self._press_item
        self._press_item = None
        self._dragging = False
        self._edge_timer.stop()
        pending, self._reload_pending = self._reload_pending, False
        if was_dragging:
            self.viewport().unsetCursor()
            self._persist_order()
            QTimer.singleShot(0, self.reload)
        elif clicked is not None:
            # a plain click: open it (deferred, so the list isn't rebuilt
            # in the middle of its own mouse handling)
            path = clicked.data(Qt.UserRole)
            QTimer.singleShot(0, lambda: self.docActivated.emit(path))
        elif pending:
            QTimer.singleShot(0, self.reload)

    def _persist_order(self):
        names = []
        for i in range(self.count()):
            path = self.item(i).data(Qt.UserRole)
            if path:
                names.append(os.path.basename(path))
        if not names:
            return
        # keep any documents beyond MAX (not shown) after the visible ones
        tail = [n for n in read_order() if n not in names]
        write_order(names + tail)
        self.orderChanged.emit()


class GalleryDialog(QDialog):
    """Grid view of every document in the library folder."""

    docActivated = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Library")
        self.resize(760, 560)
        lay = QVBoxLayout(self)
        self.info = QLabel(library_dir())
        self.info.setStyleSheet("color:#888;")
        lay.addWidget(self.info)
        self.list = _DocList(QSize(180, 140))
        self.list.docActivated.connect(self._pick)
        self.list.docDeleted.connect(lambda _p: self.reload())
        # set by the opener; duplicating needs the main window's help (the
        # open document must be saved first), after which we just re-list
        self.list.docDuplicateRequested.connect(
            lambda _p: QTimer.singleShot(0, self.reload))
        lay.addWidget(self.list)
        self.reload()

    def reload(self):
        paths = list_documents()
        self.list.reload(paths)
        self.info.setText(f"{library_dir()}   —   {len(paths)} document(s)")

    def _pick(self, path: str):
        self.docActivated.emit(path)
        self.accept()
