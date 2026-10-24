"""The main window: looks on the left, the photo in the middle, adjustments on the right, filmstrip below."""
from __future__ import annotations

import copy
import os

import numpy as np
from PIL import Image
from PySide6.QtCore import QByteArray, QSize, Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDockWidget, QFileDialog, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
                               QPushButton, QScrollArea, QToolBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget, QAbstractItemView, QListView, QSizePolicy, QTreeWidgetItemIterator, QHeaderView,
                               QApplication)
from PySide6.QtCore import QEvent

from .. import __version__, imageio
from ..engine import resolve, write_cube
from ..looks import BRANDS, slug
from ..store import Store
from . import theme
from .export_dialog import ExportDialog
from .widgets import AdjustSlider, PreviewView
from .workers import look_icons_job, preview_job, render_job, thumbnail_job, to_qimage

LOOK_ROLE = Qt.UserRole + 1
PATH_ROLE = Qt.UserRole + 2

SLIDERS = [
    ("Light", [("exposure", "Exposure", -2.0, 2.0, 0.05, "{:+.2f} EV"),
               ("contrast", "Contrast", -1.0, 1.0, 0.01, "{:+.2f}"),
               ("highlights", "Highlights", -1.0, 1.0, 0.01, "{:+.2f}"),
               ("shadows", "Shadows", -1.0, 1.0, 0.01, "{:+.2f}"),
               ("fade", "Faded blacks", -0.15, 0.2, 0.005, "{:+.3f}")]),
    ("Colour", [("temperature", "Temperature", -150.0, 150.0, 1.0, "{:+.0f}"),
                ("tint", "Tint", -10.0, 10.0, 0.1, "{:+.1f}"),
                ("saturation", "Saturation", 0.0, 2.0, 0.01, "{:.2f}×")]),
    ("Film", [("grain", "Grain", 0.0, 1.0, 0.01, "{:.2f}"),
              ("vignette", "Vignette", 0.0, 1.0, 0.01, "{:.2f}")]),
]


class MainWindow(QMainWindow):
    def __init__(self, store: Store | None = None):
        super().__init__()
        self.setWindowTitle("Emulsa")
        self.resize(1440, 900)
        self.store = store or Store()
        self.pool = QThreadPool.globalInstance()
        self.files: list[str] = []
        self.current: str | None = None
        self.preview_arr: np.ndarray | None = None
        self.grain_scale = 0.3
        self.look: dict | None = None
        self.base_params: dict = resolve({})
        self.params: dict = resolve({})
        self.strength = 1.0
        self.render_token = 0
        self.icons_token = 0
        self.look_icons: dict[str, QIcon] = {}
        self.thumbs: dict[str, QListWidgetItem] = {}

        self.render_timer = QTimer(self, singleShot=True, interval=40, timeout=self._render)

        self._build_toolbar()
        self._build_center()
        self._build_looks_panel()
        self._build_adjust_panel()
        self.statusBar().showMessage("Ready")
        QApplication.instance().installEventFilter(self)

        geo = self.store.get("geometry")
        if geo:
            self.restoreGeometry(QByteArray.fromBase64(geo.encode()))
        state = self.store.get("window_state")
        if state:
            self.restoreState(QByteArray.fromBase64(state.encode()))

        self._populate_looks()
        first = self.store.look(self.store.get("last_look", "")) or self.store.look("sony-standard") or self.store.looks()[0]
        self.choose_look(first)
        last = self.store.get("last_folder")
        if last and os.path.isdir(last):
            QTimer.singleShot(0, lambda: self.open_folder(last))

    # ------------------------------------------------------------------ building the window
    def _build_toolbar(self):
        tb = QToolBar("Main", self)
        tb.setObjectName("toolbar")
        tb.setMovable(False)
        tb.setIconSize(QSize(16, 16))
        self.addToolBar(Qt.TopToolBarArea, tb)

        def act(text, slot, shortcut=None, tip=None, checkable=False):
            a = QAction(text, self)
            a.triggered.connect(slot)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.setToolTip(f"{tip or text}" + (f"  ({QKeySequence(shortcut).toString(QKeySequence.NativeText)})" if shortcut else ""))
            a.setCheckable(checkable)
            tb.addAction(a)
            return a

        act("Open folder…", self._ask_folder, "Ctrl+O", "Open a folder of photos")
        act("Add photos…", self._ask_files, "Ctrl+Shift+O", "Open individual photos")
        tb.addSeparator()
        self.before_act = act("Before", lambda on: self.preview.set_show_original(on), None,
                              "Show the original photo (or hold the \\ key)", checkable=True)
        tb.addSeparator()
        act("Save look as .cube…", self._export_cube, None, "Save the current look as a LUT for video editors")
        spacer = QWidget(); spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        self.export_btn = QPushButton("Export…")
        self.export_btn.setObjectName("primary")
        self.export_btn.setToolTip("Export the selected photos with this look  (Ctrl+E)")
        self.export_btn.clicked.connect(self._export)
        tb.addWidget(self.export_btn)
        self.addAction(QAction(self, shortcut=QKeySequence("Ctrl+E"), triggered=self._export))
        self.addAction(QAction(self, shortcut=QKeySequence("F"), triggered=self._toggle_current_favourite))

    def _build_center(self):
        central = QWidget(); central.setObjectName("central")
        lay = QVBoxLayout(central); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        self.preview = PreviewView()
        self.preview.files_dropped.connect(self._dropped)
        self.filmstrip = QListWidget()
        self.filmstrip.setObjectName("filmstrip")
        self.filmstrip.setViewMode(QListView.IconMode)
        self.filmstrip.setFlow(QListView.LeftToRight)
        self.filmstrip.setWrapping(False)
        self.filmstrip.setMovement(QListView.Static)
        self.filmstrip.setIconSize(QSize(120, 80))
        self.filmstrip.setFixedHeight(112)
        self.filmstrip.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.filmstrip.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.filmstrip.currentItemChanged.connect(self._photo_changed)
        self.filmstrip.setAccessibleName("Photos")
        lay.addWidget(self.preview, 1)
        lay.addWidget(self.filmstrip)
        self.setCentralWidget(central)
        self._placeholder = QIcon(self._blank(120, 80))

    def _build_looks_panel(self):
        dock = QDockWidget("Looks", self); dock.setObjectName("looksDock")
        dock.setFeatures(QDockWidget.DockWidgetMovable)
        w = QWidget(); w.setObjectName("panel")
        lay = QVBoxLayout(w); lay.setContentsMargins(10, 6, 10, 10); lay.setSpacing(8)
        self.search = QLineEdit(); self.search.setPlaceholderText("Search looks"); self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._populate_looks)
        self.filter = QComboBox()
        self.filter.addItems(["All looks", "★ Favourites", "Custom"] + BRANDS)
        self.filter.currentIndexChanged.connect(self._populate_looks)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(2)
        self.tree.setIconSize(QSize(54, 36))
        self.tree.setIndentation(10)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.tree.header().resizeSection(1, 28)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tree.setAccessibleName("Looks")
        self.tree.itemClicked.connect(self._look_clicked)
        self.tree.currentItemChanged.connect(lambda cur, _: self._look_clicked(cur, 0, keyboard=True))
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._look_menu)
        hint = QLabel("Click ☆ or press F to favourite a look."); hint.setObjectName("hint")
        lay.addWidget(self.search); lay.addWidget(self.filter); lay.addWidget(self.tree, 1); lay.addWidget(hint)
        dock.setWidget(w)
        dock.setMinimumWidth(280)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

    def _build_adjust_panel(self):
        dock = QDockWidget("Adjust", self); dock.setObjectName("adjustDock")
        dock.setFeatures(QDockWidget.DockWidgetMovable)
        inner = QWidget(); inner.setObjectName("panel")
        lay = QVBoxLayout(inner); lay.setContentsMargins(14, 6, 14, 14); lay.setSpacing(4)

        self.look_title = QLabel(); self.look_title.setObjectName("lookTitle"); self.look_title.setWordWrap(True)
        self.look_brand = QLabel(); self.look_brand.setObjectName("lookBrand")
        self.fav_btn = QPushButton("☆ Add to favourites"); self.fav_btn.clicked.connect(self._toggle_current_favourite)
        head = QHBoxLayout(); head.addWidget(self.look_brand, 1); head.addWidget(self.fav_btn)
        lay.addWidget(self.look_title); lay.addLayout(head)

        self.strength_slider = AdjustSlider("strength", "Look strength", 0, 100, 1, "{:.0f}%")
        self.strength_slider.default = 100
        self.strength_slider.set_value(100)
        self.strength_slider.changed.connect(self._strength_changed)
        lay.addWidget(self.strength_slider)

        self.sliders: dict[str, AdjustSlider] = {}
        for section, items in SLIDERS:
            label = QLabel(section.upper()); label.setObjectName("section")
            lay.addWidget(label)
            for key, text, lo, hi, step, fmt in items:
                s = AdjustSlider(key, text, lo, hi, step, fmt)
                s.changed.connect(self._param_changed)
                self.sliders[key] = s
                lay.addWidget(s)
            if section == "Colour":
                self.mono_box = QCheckBox("Black && white")
                self.mono_box.toggled.connect(lambda on: self._param_changed("mono", on))
                lay.addWidget(self.mono_box)

        self.edited_label = QLabel("Edited. Save it to keep this version."); self.edited_label.setObjectName("hint")
        self.edited_label.setWordWrap(True); self.edited_label.hide()
        self.reset_btn = QPushButton("Reset"); self.reset_btn.clicked.connect(self._reset)
        self.save_btn = QPushButton("Save as custom look…"); self.save_btn.clicked.connect(self._save_custom)
        self.update_btn = QPushButton("Update custom look"); self.update_btn.clicked.connect(self._update_custom)
        btns = QHBoxLayout(); btns.addWidget(self.reset_btn); btns.addWidget(self.save_btn, 1)
        lay.addSpacing(10); lay.addWidget(self.edited_label); lay.addLayout(btns); lay.addWidget(self.update_btn)
        lay.addStretch(1)

        scroll = QScrollArea(); scroll.setWidget(inner); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        dock.setWidget(scroll)
        dock.setMinimumWidth(290)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    @staticmethod
    def _blank(w, h):
        pm = QPixmap(w, h); pm.fill(QColor(theme.RAISED)); return pm

    # ------------------------------------------------------------------ looks list
    def _populate_looks(self, *_):
        text = self.search.text().strip().lower()
        mode = self.filter.currentText()
        self.tree.blockSignals(True)
        self.tree.clear()
        groups: dict[str, QTreeWidgetItem] = {}
        bold = QFont(self.tree.font()); bold.setBold(True)
        current_item = None
        for look in self.store.looks():
            fav = self.store.is_favourite(look["id"])
            if text and text not in look["name"].lower() and text not in look["brand"].lower():
                continue
            if mode == "★ Favourites" and not fav:
                continue
            if mode == "Custom" and look["brand"] != "Custom":
                continue
            if mode not in ("All looks", "★ Favourites", "Custom") and look["brand"] != mode:
                continue
            group = groups.get(look["brand"])
            if group is None:
                group = QTreeWidgetItem(self.tree, [look["brand"], ""])
                group.setFont(0, bold)
                group.setFlags(Qt.ItemIsEnabled)
                group.setForeground(0, QColor(theme.MUTED))
                group.setExpanded(True)
                groups[look["brand"]] = group
            item = QTreeWidgetItem(group, [look["name"], "★" if fav else "☆"])
            item.setData(0, LOOK_ROLE, look["id"])
            item.setForeground(1, QColor(theme.ACCENT if fav else theme.MUTED))
            item.setToolTip(1, "Remove from favourites" if fav else "Add to favourites")
            item.setIcon(0, self.look_icons.get(look["id"], QIcon()))
            if self.look and look["id"] == self.look["id"]:
                current_item = item
        self.tree.expandAll()
        if current_item:
            self.tree.setCurrentItem(current_item)
        self.tree.blockSignals(False)
        if not groups:
            empty = QTreeWidgetItem(self.tree, ["No favourites yet" if mode == "★ Favourites" else "No looks match", ""])
            empty.setFlags(Qt.NoItemFlags)

    def _look_clicked(self, item, column, keyboard=False):
        if item is None:
            return
        look_id = item.data(0, LOOK_ROLE)
        if not look_id:
            return
        if column == 1 and not keyboard:
            self.store.toggle_favourite(look_id)
            self._refresh_fav_marks()
            return
        if self.look and look_id == self.look["id"]:
            return
        look = self.store.look(look_id)
        if look:
            self.choose_look(look)

    def _refresh_fav_marks(self):
        it = QTreeWidgetItemIterator(self.tree)
        while it.value():
            item = it.value()
            lid = item.data(0, LOOK_ROLE)
            if lid:
                fav = self.store.is_favourite(lid)
                item.setText(1, "★" if fav else "☆")
                item.setForeground(1, QColor(theme.ACCENT if fav else theme.MUTED))
            it += 1
        if self.look:
            self._set_fav_button(self.store.is_favourite(self.look["id"]))
        if self.filter.currentText() == "★ Favourites":
            self._populate_looks()

    def _set_fav_button(self, fav: bool):
        self.fav_btn.setText("★ In favourites" if fav else "☆ Add to favourites")
        self.fav_btn.setStyleSheet(f"color: {theme.ACCENT};" if fav else "")

    def _toggle_current_favourite(self):
        if self.look:
            self.store.toggle_favourite(self.look["id"])
            self._refresh_fav_marks()

    def _look_menu(self, pos):
        item = self.tree.itemAt(pos)
        lid = item.data(0, LOOK_ROLE) if item else None
        look = self.store.look(lid) if lid else None
        if not look:
            return
        menu = QMenu(self)
        fav = self.store.is_favourite(lid)
        menu.addAction("Remove from favourites" if fav else "Add to favourites",
                       lambda: (self.store.toggle_favourite(lid), self._refresh_fav_marks()))
        menu.addAction("Save as .cube…", lambda: self._export_cube(look))
        if not look.get("builtin"):
            menu.addSeparator()
            menu.addAction("Rename…", lambda: self._rename_custom(look))
            menu.addAction("Delete", lambda: self._delete_custom(look))
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------ choosing and editing a look
    def choose_look(self, look: dict):
        self.look = look
        self.base_params = resolve(look["params"])
        self.params = copy.deepcopy(self.base_params)
        self.store.set("last_look", look["id"])
        self.look_title.setText(look["name"])
        self.look_brand.setText(look["brand"] if look.get("builtin") else "Custom look")
        self._set_fav_button(self.store.is_favourite(look["id"]))
        self._sync_sliders()
        self._update_edited()
        self._schedule_render()

    def _sync_sliders(self):
        for key, s in self.sliders.items():
            s.default = float(self.base_params[key])
            s.set_value(float(self.params[key]))
        self.mono_box.blockSignals(True)
        self.mono_box.setChecked(bool(self.params["mono"]))
        self.mono_box.blockSignals(False)

    def _param_changed(self, key, value):
        self.params[key] = value
        self._update_edited()
        self._schedule_render()

    def _strength_changed(self, _key, value):
        self.strength = value / 100.0
        self._schedule_render()

    def _edited(self) -> bool:
        return self.params != self.base_params

    def _update_edited(self):
        edited = self._edited()
        self.edited_label.setVisible(edited)
        self.reset_btn.setEnabled(edited)
        is_custom = bool(self.look) and not self.look.get("builtin")
        self.update_btn.setVisible(is_custom)
        self.update_btn.setEnabled(is_custom and edited)

    def _reset(self):
        self.params = copy.deepcopy(self.base_params)
        self._sync_sliders()
        self._update_edited()
        self._schedule_render()

    def _save_custom(self):
        default = f"{self.look['name']} (custom)" if self.look else "My look"
        name, ok = QInputDialog.getText(self, "Save custom look", "Name for this look:", text=default)
        if not ok or not name.strip():
            return
        look = self.store.add_custom(name, self.params, self.look["id"] if self.look else None)
        self.filter.setCurrentIndex(0)
        self.look_icons.pop(look["id"], None)
        self.choose_look(look)
        self._populate_looks()
        self._refresh_icons()
        self.statusBar().showMessage(f"Saved “{look['name']}” to your custom looks.", 5000)

    def _update_custom(self):
        if not self.look or self.look.get("builtin"):
            return
        for l in self.store.data["custom"]:
            if l["id"] == self.look["id"]:
                l["params"] = copy.deepcopy(self.params)
        self.store.save()
        self.choose_look(self.store.look(self.look["id"]))
        self._refresh_icons()
        self.statusBar().showMessage("Custom look updated.", 4000)

    def _rename_custom(self, look):
        name, ok = QInputDialog.getText(self, "Rename look", "New name:", text=look["name"])
        if ok and name.strip():
            self.store.rename_custom(look["id"], name)
            if self.look and self.look["id"] == look["id"]:
                self.look = self.store.look(look["id"])
                self.look_title.setText(self.look["name"])
            self._populate_looks()

    def _delete_custom(self, look):
        if QMessageBox.question(self, "Delete look", f"Delete “{look['name']}”? This can't be undone.") != QMessageBox.Yes:
            return
        self.store.delete_custom(look["id"])
        if self.look and self.look["id"] == look["id"]:
            self.choose_look(self.store.look("sony-standard"))
        self._populate_looks()

    # ------------------------------------------------------------------ photos
    def _ask_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Open a folder of photos", self.store.get("last_folder", ""))
        if d:
            self.open_folder(d)

    def _ask_files(self):
        exts = " ".join(f"*{e}" for e in sorted(imageio.SUPPORTED))
        files, _ = QFileDialog.getOpenFileNames(self, "Open photos", self.store.get("last_folder", ""),
                                                f"Photos ({exts} {exts.upper()})")
        if files:
            self.set_files(files)

    def _dropped(self, paths):
        if len(paths) == 1 and os.path.isdir(paths[0]):
            self.open_folder(paths[0])
            return
        files = []
        for p in paths:
            files += imageio.list_photos(p) if os.path.isdir(p) else ([p] if imageio.is_supported(p) else [])
        if files:
            self.set_files(files)
        else:
            self.statusBar().showMessage("None of those files are photos Emulsa can open.", 5000)

    def open_folder(self, folder):
        files = imageio.list_photos(folder)
        self.store.set("last_folder", folder)
        if not files:
            self.set_files([])
            self.preview.clear("No photos in this folder. Emulsa opens JPEG, PNG, TIFF and RAW files.")
            self.statusBar().showMessage(folder)
            return
        self.set_files(files)
        self.statusBar().showMessage(f"{len(files)} photos in {folder}")

    def set_files(self, files):
        self.files = list(files)
        if files:
            self.store.set("last_folder", os.path.dirname(files[0]))
        self.filmstrip.blockSignals(True)
        self.filmstrip.clear()
        self.thumbs.clear()
        for path in self.files:
            item = QListWidgetItem(self._placeholder, "")
            item.setData(PATH_ROLE, path)
            item.setToolTip(os.path.basename(path))
            item.setSizeHint(QSize(128, 92))
            self.filmstrip.addItem(item)
            self.thumbs[path] = item
            job = thumbnail_job(path, 240)
            job.signals.done.connect(self._thumb_ready)
            self.pool.start(job, priority=-1)
        self.filmstrip.blockSignals(False)
        if self.files:
            self.filmstrip.setCurrentRow(0)
        else:
            self.current = None
            self.preview_arr = None

    def _thumb_ready(self, path, qimg):
        item = self.thumbs.get(path)
        if item is not None:
            item.setIcon(QIcon(QPixmap.fromImage(qimg)))

    def _photo_changed(self, item, _prev=None):
        if item is None:
            return
        path = item.data(PATH_ROLE)
        if path == self.current:
            return
        self.current = path
        self.preview.busy = True
        self.preview.update()
        self.statusBar().showMessage(f"Opening {os.path.basename(path)}…")
        job = preview_job(path)
        job.signals.done.connect(self._preview_ready)
        job.signals.failed.connect(lambda p, msg: self._preview_failed(p, msg))
        self.pool.start(job, priority=5)

    def _preview_ready(self, path, arr):
        if path != self.current:
            return
        self.preview_arr = arr
        fw = imageio.full_width(path)
        self.grain_scale = arr.shape[1] / fw if fw else 0.3
        self.preview.set_images(original=to_qimage(arr))
        self.preview.graded = None
        self.statusBar().showMessage(f"{os.path.basename(path)}  ·  {self.filmstrip.currentRow() + 1} of {len(self.files)}")
        self._render()
        self._refresh_icons()

    def _preview_failed(self, path, msg):
        if path == self.current:
            self.preview.clear(f"Couldn't open {os.path.basename(path)}.\n{msg}")
            self.statusBar().showMessage(f"Couldn't open {os.path.basename(path)}: {msg}")

    # ------------------------------------------------------------------ rendering
    def _schedule_render(self):
        if self.preview_arr is not None:
            self.render_timer.start()

    def _render(self):
        if self.preview_arr is None:
            return
        self.render_token += 1
        self.preview.busy = True
        self.preview.update()
        job = render_job(self.render_token, self.preview_arr, copy.deepcopy(self.params), self.strength, self.grain_scale)
        job.signals.done.connect(self._render_ready)
        self.pool.start(job, priority=10)

    def _render_ready(self, token, qimg):
        if token != self.render_token:
            return
        self.preview.busy = False
        self.preview.set_images(graded=qimg)

    def _refresh_icons(self):
        if self.preview_arr is None:
            return
        self.icons_token += 1
        h, w = self.preview_arr.shape[:2]
        tw = 108
        small = Image.fromarray((self.preview_arr * 255 + 0.5).astype(np.uint8)).resize((tw, max(1, round(h * tw / w))), Image.BILINEAR)
        small = np.asarray(small, dtype=np.float32) / 255.0
        job = look_icons_job(self.icons_token, small, self.store.looks())
        job.signals.done.connect(self._icons_ready)
        self.pool.start(job, priority=-2)

    def _icons_ready(self, token, icons):
        if token != self.icons_token:
            return
        self.look_icons = {lid: QIcon(QPixmap.fromImage(q)) for lid, q in icons.items()}
        it = QTreeWidgetItemIterator(self.tree)
        while it.value():
            item = it.value()
            lid = item.data(0, LOOK_ROLE)
            if lid in self.look_icons:
                item.setIcon(0, self.look_icons[lid])
            it += 1

    # ------------------------------------------------------------------ export
    def _selected_files(self):
        return [i.data(PATH_ROLE) for i in self.filmstrip.selectedItems()]

    def _export(self):
        if not self.files:
            self.statusBar().showMessage("Open some photos first.", 4000)
            return
        look = dict(self.look, name=self.look["name"] + (" (edited)" if self._edited() else ""))
        ExportDialog(self, self.store, self.files, self._selected_files(), look,
                     copy.deepcopy(self.params), self.strength).exec()

    def _export_cube(self, look=None):
        look = look if isinstance(look, dict) else None
        params = look["params"] if look else self.params
        name = look["name"] if look else (self.look["name"] if self.look else "look")
        start = os.path.join(self.store.get("export_dir") or os.path.expanduser("~"), slug(name) + ".cube")
        path, _ = QFileDialog.getSaveFileName(self, "Save look as .cube", start, "Cube LUT (*.cube)")
        if not path:
            return
        write_cube(path, params, name)
        note = " Grain and vignette aren't part of a LUT." if resolve(params)["grain"] or resolve(params)["vignette"] else ""
        self.statusBar().showMessage(f"Saved {os.path.basename(path)}.{note}", 6000)

    # ------------------------------------------------------------------ window events
    def eventFilter(self, obj, e):
        # hold \ anywhere in the window to see the original, like Lightroom
        if e.type() in (QEvent.KeyPress, QEvent.KeyRelease) and e.key() == Qt.Key_Backslash \
                and self.isActiveWindow() and not isinstance(QApplication.focusWidget(), QLineEdit):
            if not e.isAutoRepeat():
                self.preview.set_show_original(e.type() == QEvent.KeyPress or self.before_act.isChecked())
            return True
        return super().eventFilter(obj, e)

    def closeEvent(self, e):
        self.store.set("geometry", bytes(self.saveGeometry().toBase64()).decode())
        self.store.set("window_state", bytes(self.saveState().toBase64()).decode())
        super().closeEvent(e)

