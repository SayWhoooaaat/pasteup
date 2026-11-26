"""Main application window: toolbar, docks, filmstrip and action wiring."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QGuiApplication
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QDockWidget, QToolBar, QFileDialog,
    QToolButton, QLineEdit, QApplication, QPlainTextEdit, QScrollArea, QMenu,
    QStyle,
)

from . import canvas as C
from . import icons
from . import library as L
from .history import History
from .properties import PropertiesPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PasteUp")
        self.resize(1180, 820)

        self.canvas = C.Canvas()
        self.history = History(self.canvas.scene_)
        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.canvas, 1)

        self.filmstrip = L.Filmstrip()
        lay.addWidget(self.filmstrip)
        self.setCentralWidget(central)

        self.props = PropertiesPanel(self.canvas)
        dock = QDockWidget("Tools", self)
        # scrolls if the window is too short for a tall set of settings
        scroll = QScrollArea()
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(self.props)
        scroll.setFixedWidth(self.props.width() + self.style().pixelMetric(
            QStyle.PM_ScrollBarExtent))
        dock.setWidget(scroll)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        # no close button: the dock holds the drawing tools, hiding it
        # would leave the app without them
        dock.setFeatures(QDockWidget.DockWidgetMovable
                         | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

        # current document identity + debounced auto-save
        self.doc_path = None
        self._loading = False
        self._autosave = QTimer(self)
        self._autosave.setSingleShot(True)
        self._autosave.setInterval(1200)
        self._autosave.timeout.connect(self._save_current)

        self._build_actions()
        self._wire()
        self.filmstrip.reload()
        self.canvas.scene_.new_document()
        self.statusBar().showMessage(
            "New 200×200 document. Paste (Ctrl+V), open or drag in an image to begin.")

    # -- actions ----------------------------------------------------------
    def _act(self, text, slot, shortcut=None, checkable=False):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.setCheckable(checkable)
        a.triggered.connect(slot)
        return a

    def _build_actions(self):
        file_tb = QToolBar("File")
        file_tb.setMovable(False)
        self.addToolBar(file_tb)
        file_tb.addAction(self._act("New", self.new_document, "Ctrl+N"))
        file_tb.addAction(self._act("Open", self.open_files, "Ctrl+O"))
        self.copy_action = self._act("Copy", self.copy_selection, "Ctrl+C")
        self.paste_action = self._act("Paste", self.paste, "Ctrl+V")
        file_tb.addAction(self.copy_action)
        file_tb.addAction(self.paste_action)
        # documents save themselves, so Ctrl+S means "save a PNG somewhere"
        export = self._act("Export…", self.export_png)
        export.setShortcuts([QKeySequence("Ctrl+S"), QKeySequence("Ctrl+E")])
        export.setToolTip("Export the page as a PNG (Ctrl+S)")
        file_tb.addAction(export)
        file_tb.addAction(self._act("Copy Image", self.copy_result,
                                    "Ctrl+Shift+C"))
        file_tb.addSeparator()
        self.undo_action = self._act("Undo", self.undo, "Ctrl+Z")
        self.redo_action = self._act("Redo", self.redo)
        self.redo_action.setShortcuts(
            [QKeySequence("Ctrl+Shift+Z"), QKeySequence("Ctrl+Y")])
        file_tb.addAction(self.undo_action)
        file_tb.addAction(self.redo_action)
        file_tb.addSeparator()
        file_tb.addAction(self._act("Library", self.open_gallery, "Ctrl+G"))

        # tools — icon buttons at the top of the right-hand panel. The
        # QActions are still added to the window so the shortcuts work.
        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)
        self._tool_actions = {}
        icon_color = self.palette().windowText().color()
        tools = [
            ("Select", C.SELECT, "V"),
            ("Rectangle", C.RECT, "R"),
            ("Ellipse", C.ELLIPSE, "O"),
            ("Line", C.LINE, "L"),
            ("Arrow", C.ARROW, "A"),
            ("Text", C.TEXT, "T"),
            ("Callout", C.CALLOUT, "C"),
        ]
        for label, tool, sc in tools:
            a = self._act(label, lambda checked=False, t=tool: self.set_tool(t),
                          sc, checkable=True)
            a.setIcon(icons.tool_icon(tool, icon_color))
            a.setToolTip(f"{label} ({sc})")
            self.addAction(a)
            self.tool_group.addAction(a)
            self._tool_actions[tool] = a
        self._tool_actions[C.SELECT].setChecked(True)
        self.props.set_tool_actions(list(self._tool_actions.values()))

        # arrange / transform / edit --------------------------------------
        edit_tb = QToolBar("Arrange")
        edit_tb.setMovable(False)
        self.addToolBar(Qt.BottomToolBarArea, edit_tb)
        self.front_action = self._act("Front", self._front, "Ctrl+Shift+]")
        self.forward_action = self._act("Forward", self._forward, "Ctrl+]")
        self.backward_action = self._act("Backward", self._backward, "Ctrl+[")
        self.back_action = self._act("Back", self._back, "Ctrl+Shift+[")
        self.flip_h_action = self._act("Flip H", self._flip_h)
        self.flip_v_action = self._act("Flip V", self._flip_v)
        self.rotate_action = self._act("Rotate 90°", self._rotate90)
        self.rotate_left_action = self._act(
            "Rotate 90° Left", lambda: self._rotate90(-90))
        self.duplicate_action = self._act(
            "Duplicate", self.duplicate_selected, "Ctrl+D")
        self.delete_action = self._act("Delete", self.delete_selected, "Delete")
        self.addAction(self.rotate_left_action)
        edit_tb.addActions([self.front_action, self.forward_action,
                            self.backward_action, self.back_action])
        edit_tb.addSeparator()
        edit_tb.addActions([self.flip_h_action, self.flip_v_action,
                            self.rotate_action])
        edit_tb.addSeparator()
        edit_tb.addActions([self.duplicate_action, self.delete_action])
        # these only mean something with a selection; greyed out otherwise
        self._selection_actions = [
            self.front_action, self.forward_action, self.backward_action,
            self.back_action, self.flip_h_action, self.flip_v_action,
            self.rotate_action, self.rotate_left_action,
            self.duplicate_action, self.delete_action]

        # zoom shortcuts (buttons live in the status bar)
        self.addAction(self._act("Fit", self.canvas.fit_to_page, "Ctrl+0"))
        self.addAction(self._act("Zoom In", self.canvas.zoom_in, "Ctrl+="))
        self.addAction(self._act("Zoom In", self.canvas.zoom_in, "Ctrl++"))
        self.addAction(self._act("Zoom Out", self.canvas.zoom_out, "Ctrl+-"))
        self._build_zoom_controls()

    def _build_zoom_controls(self):
        bar = self.statusBar()

        def btn(text, slot, tip):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.clicked.connect(slot)
            return b

        self.zoom_edit = QLineEdit("100%")
        self.zoom_edit.setFixedWidth(56)
        self.zoom_edit.setAlignment(Qt.AlignCenter)
        self.zoom_edit.setToolTip("Zoom — type a percentage and press Enter")
        self.zoom_edit.editingFinished.connect(self._zoom_edit_committed)
        bar.addPermanentWidget(btn("Fit", self.canvas.fit_to_page, "Fit page (Ctrl+0)"))
        bar.addPermanentWidget(btn("−", self.canvas.zoom_out, "Zoom out (Ctrl+-)"))
        bar.addPermanentWidget(self.zoom_edit)
        bar.addPermanentWidget(btn("+", self.canvas.zoom_in, "Zoom in (Ctrl+=)"))
        self.canvas.zoomChanged.connect(self._on_zoom_changed)

    def _on_zoom_changed(self, zoom: float):
        if not self.zoom_edit.hasFocus():
            self.zoom_edit.setText(f"{round(zoom * 100)}%")

    def _zoom_edit_committed(self):
        text = self.zoom_edit.text().strip().rstrip("%").strip()
        try:
            value = float(text)
        except ValueError:
            self._on_zoom_changed(self.canvas.current_zoom())
            return
        self.canvas.set_zoom_percent(value)
        self.zoom_edit.setText(f"{round(self.canvas.current_zoom() * 100)}%")
        self.canvas.setFocus()

    def _wire(self):
        self.canvas.scene_.changed.connect(self._schedule_autosave)
        self.canvas.toolChanged.connect(self._on_tool_changed)
        self.canvas.selectionChanged.connect(self._sync_selection_actions)
        self.canvas.menuRequested.connect(self._canvas_menu)
        self._sync_selection_actions()
        self.filmstrip.docActivated.connect(self.open_document)
        self.filmstrip.docDeleted.connect(self._on_doc_deleted)
        self.filmstrip.docDuplicateRequested.connect(self.duplicate_document)
        self.history.changed.connect(self._sync_history_actions)
        self._sync_history_actions()

    # -- undo / redo --------------------------------------------------------
    def _sync_history_actions(self):
        self.undo_action.setEnabled(self.history.can_undo())
        self.redo_action.setEnabled(self.history.can_redo())

    def undo(self):
        # While an inline text editor (or the zoom box) has focus, Ctrl+Z must
        # mean text undo, never a document rollback under the user's cursor.
        fw = QApplication.focusWidget()
        if isinstance(fw, (QPlainTextEdit, QLineEdit)):
            fw.undo()
            return
        self.history.undo()

    def redo(self):
        fw = QApplication.focusWidget()
        if isinstance(fw, (QPlainTextEdit, QLineEdit)):
            fw.redo()
            return
        self.history.redo()

    # -- tool -------------------------------------------------------------
    def set_tool(self, tool: str):
        self.canvas.set_tool(tool)

    def _on_tool_changed(self, tool: str):
        # the canvas can change tool by itself (Esc), so the buttons follow
        # the canvas rather than the other way round
        if tool in self._tool_actions:
            self._tool_actions[tool].setChecked(True)

    def keyPressEvent(self, event):
        # Esc reaches here when focus is somewhere other than the canvas
        # (a spin box in the style panel, say) and nothing else wanted it
        if event.key() == Qt.Key_Escape:
            self.canvas.escape()
            self.canvas.setFocus()
            event.accept()
            return
        super().keyPressEvent(event)

    # -- right-click menu on the canvas -------------------------------------
    def _sync_selection_actions(self):
        has = bool(self.canvas.selected_items())
        for a in self._selection_actions:
            a.setEnabled(has)

    def _canvas_menu(self, global_pos, scene_pos):
        menu = QMenu(self)
        if self.canvas.selected_items():
            menu.addAction(self.copy_action)
            menu.addAction(self.duplicate_action)
            menu.addAction(self.delete_action)
            menu.addSeparator()
            menu.addAction("Bring to Front", self._front)
            menu.addAction("Bring Forward", self._forward)
            menu.addAction("Send Backward", self._backward)
            menu.addAction("Send to Back", self._back)
            menu.addSeparator()
            menu.addAction("Rotate 90° Right", self._rotate90)
            menu.addAction("Rotate 90° Left", lambda: self._rotate90(-90))
            menu.addAction("Flip Horizontal", self._flip_h)
            menu.addAction("Flip Vertical", self._flip_v)
            menu.addSeparator()
        menu.addAction("Paste Here", lambda: self.paste(scene_pos))
        menu.exec(global_pos)

    # -- file -------------------------------------------------------------
    def open_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Open image(s)", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        for p in paths:
            self.canvas.open_file(p)

    def paste(self, at=None):
        # `at` is a scene position (from the right-click menu); the toolbar
        # action passes its "checked" bool here, which means "default spot"
        if isinstance(at, bool):
            at = None
        if not self.canvas.paste_clipboard(at):
            self.statusBar().showMessage("Clipboard has no image or items.", 3000)

    def copy_selection(self):
        sel = self.canvas.selected_items()
        if not sel:
            self.statusBar().showMessage("Nothing selected to copy.", 3000)
            return
        self.canvas.copy_selection()
        self.statusBar().showMessage(
            f"Copied {len(sel)} item{'s' if len(sel) > 1 else ''}.", 3000)

    def export_png(self):
        img = self.canvas.scene_.render_document()
        if img is None:
            self.statusBar().showMessage("Nothing to export.", 3000)
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PNG", "annotation.png", "PNG image (*.png)")
        if path:
            if not path.lower().endswith(".png"):
                path += ".png"
            img.save(path, "PNG")
            self.statusBar().showMessage(f"Exported {path}", 4000)

    def copy_result(self):
        img = self.canvas.scene_.render_document()
        if img is None:
            return
        QGuiApplication.clipboard().setImage(img)
        self.statusBar().showMessage("Copied flattened document to clipboard.", 3000)

    def open_gallery(self):
        dlg = L.GalleryDialog(self)
        dlg.docActivated.connect(self.open_document)
        dlg.list.docDeleted.connect(self._on_doc_deleted)
        dlg.list.docDuplicateRequested.connect(self.duplicate_document)
        dlg.list.set_current(self.doc_path)
        dlg.exec()
        self.filmstrip.reload()

    def _on_doc_deleted(self, path: str):
        """If the deleted document is the one on screen, drop it — otherwise the
        pending auto-save would immediately write it back to disk."""
        if self.doc_path == path:
            self._autosave.stop()
            self.doc_path = None
            self.filmstrip.set_current(None)
            self._loading = True
            try:
                self.canvas.scene_.new_document()
            finally:
                self._loading = False
            self.history.reset()
            self.canvas.fit_to_page()
            self.set_tool(C.SELECT)
            self.statusBar().showMessage(
                "Deleted the open document — started a new one.", 4000)
        self.filmstrip.reload()

    # -- document lifecycle ----------------------------------------------
    def new_document(self):
        self._save_current()
        self.canvas.scene_.new_document()
        self.history.reset()
        self.doc_path = None
        self.filmstrip.set_current(None)
        self.canvas.fit_to_page()
        self.set_tool(C.SELECT)
        self.statusBar().showMessage("New 200×200 document.", 3000)

    def open_document(self, path: str):
        if path == self.doc_path:
            return  # already on screen
        self._save_current()
        try:
            data = L.read_document(path)
        except (OSError, ValueError) as exc:
            self.statusBar().showMessage(f"Could not open document: {exc}", 4000)
            return
        self._loading = True
        try:
            self.canvas.scene_.load_from(data)
        finally:
            self._loading = False
        self.history.reset()
        self.doc_path = path
        self.filmstrip.set_current(path)
        self.canvas.fit_to_page()
        self.props.refresh()
        self.statusBar().showMessage(f"Opened {os.path.basename(path)}", 3000)

    def duplicate_document(self, path: str):
        """Right-click > Duplicate on a thumbnail: a second copy of that
        document, placed next to it. The open document stays open."""
        if path == self.doc_path:
            self._save_current(force=True)  # copy what's on screen now
        try:
            L.duplicate_document(path)
        except OSError as exc:
            self.statusBar().showMessage(f"Could not duplicate: {exc}", 4000)
            return
        self.filmstrip.reload()
        self.statusBar().showMessage("Duplicated the document.", 3000)

    def _schedule_autosave(self, *args):
        if self._loading or self.canvas.scene_.is_empty():
            return
        self._autosave.start()

    def _save_current(self, force: bool = False):
        """Persist the current document; assigns a library path on first save."""
        self._autosave.stop()
        if self.canvas.scene_.is_empty():
            return
        # Never save mid-interaction: the document is in a transient state
        # (half-finished drag, page-resize preview), and saving must not be
        # able to disturb an active mouse grab. Try again once things settle.
        if not force and (
                self.canvas.scene_.mouseGrabberItem() is not None
                or QGuiApplication.mouseButtons() != Qt.NoButton):
            self._autosave.start()
            return
        if self.doc_path is None:
            self.doc_path = L.new_document_path()
            self.filmstrip.set_current(self.doc_path)
        # guard so repaints triggered by rendering can't re-arm the
        # auto-save timer and spin forever.
        self._loading = True
        try:
            data = self.canvas.scene_.serialize()
            full = self.canvas.scene_.render_document()
            thumb = None
            if full is not None:
                thumb = full.scaled(256, 256, Qt.KeepAspectRatio,
                                    Qt.SmoothTransformation)
            L.write_document(self.doc_path, data, thumb)
        finally:
            self._loading = False
        self.filmstrip.reload()

    def closeEvent(self, event):
        self._save_current()
        super().closeEvent(event)

    # -- arrange / transform ---------------------------------------------
    def _sel(self):
        return self.canvas.selected_items()

    def _front(self):
        self.canvas.scene_.bring_to_front(self._sel())

    def _back(self):
        self.canvas.scene_.send_to_back(self._sel())

    def _forward(self):
        self.canvas.scene_.move_forward(self._sel())

    def _backward(self):
        self.canvas.scene_.move_backward(self._sel())

    def _flip_h(self):
        for it in self._sel():
            it.flip_horizontal()

    def _flip_v(self):
        for it in self._sel():
            it.flip_vertical()

    def _rotate90(self, degrees=90):
        if isinstance(degrees, bool):  # QAction.triggered passes "checked"
            degrees = 90
        for it in self._sel():
            # (lines keep _rotation at 0, so for them this is the delta)
            it.set_rotation_deg(it._rotation + degrees)

    def duplicate_selected(self):
        self.canvas.duplicate_selection()

    def delete_selected(self):
        for it in self._sel():
            self.canvas.scene_.removeItem(it)
