"""The main window: looks in the sidebar, the photo in the middle, adjustments in the inspector,
a filmstrip below and the look assistant in the corner."""
from __future__ import annotations

import copy
import os
import sys

import numpy as np
from PIL import Image
from PySide6.QtCore import QByteArray, QEvent, QPoint, QSize, Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction, QActionGroup, QFont, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QFileDialog, QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QLineEdit, QListView, QListWidget,
                               QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea,
                               QToolButton, QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator, QVBoxLayout,
                               QWidget)

from .. import __version__, imageio
from ..engine import resolve, write_cube
from ..looks import slug
from ..store import Store
from . import icons, theme
from .chat import ChatPanel
from .export_dialog import ExportDialog
from .widgets import AdjustSlider, AssistantBubble, PreviewView, Section
from .workers import look_icons_job, preview_job, render_job, thumbnail_job, to_qimage

LOOK_ROLE = Qt.UserRole + 1
PATH_ROLE = Qt.UserRole + 2
ASSISTANT_ID = "assistant"
MAC = sys.platform == "darwin"

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


def shortcut_text(seq: str) -> str:
    return QKeySequence(seq).toString(QKeySequence.NativeText)


class MainWindow(QMainWindow):
    def __init__(self, store: Store | None = None):
        super().__init__()
        self.setWindowTitle("Emulsa")
        self.resize(1440, 900)
        self.setMinimumSize(960, 600)
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
        self.filter_mode = "all"
        self.undo_state: tuple | None = None

        self.render_timer = QTimer(self, singleShot=True, interval=40, timeout=self._render)
        self.toast_timer = QTimer(self, singleShot=True, interval=3500, timeout=lambda: self.toast.hide())

        root = QWidget(); root.setObjectName("root")
        lay = QHBoxLayout(root); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        lay.addWidget(self._build_sidebar())
        lay.addWidget(self._build_center(), 1)
        lay.addWidget(self._build_inspector())
        self.setCentralWidget(root)
        self._build_actions()

        geo = self.store.get("geometry")
        if geo:
            self.restoreGeometry(QByteArray.fromBase64(geo.encode()))
        self.sidebar.setVisible(self.store.get("show_sidebar", True))
        self.inspector.setVisible(self.store.get("show_inspector", True))

        QApplication.instance().installEventFilter(self)
        hints = QApplication.instance().styleHints()
        if hasattr(hints, "colorSchemeChanged"):  # Qt 6.5+: follow the system switching light/dark
            hints.colorSchemeChanged.connect(lambda *_: self._theme_changed())

        self._populate_looks()
        first = self.store.look(self.store.get("last_look", "")) or self.store.look("sony-standard") or self.store.looks()[0]
        self.choose_look(first)
        self.refresh_theme()
        last = self.store.get("last_folder")
        if last and os.path.isdir(last):
            QTimer.singleShot(0, lambda: self.open_folder(last))

    # ================================================================== layout
    def _build_sidebar(self) -> QWidget:
        self.sidebar = QWidget(); self.sidebar.setObjectName("sidebar"); self.sidebar.setFixedWidth(272)
        lay = QVBoxLayout(self.sidebar); lay.setContentsMargins(12, 12, 8, 8); lay.setSpacing(8)

        logo = QLabel()
        logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "emulsa.png")
        if os.path.exists(logo_path):
            logo.setPixmap(QPixmap(logo_path).scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        name = QLabel("Emulsa"); name.setObjectName("appName")
        self.more_btn = QToolButton(); self.more_btn.setToolTip("Menu"); self.more_btn.setAccessibleName("Menu")
        self.more_btn.setPopupMode(QToolButton.InstantPopup)
        head = QHBoxLayout(); head.setSpacing(8); head.setContentsMargins(4, 0, 0, 0)
        head.addWidget(logo); head.addWidget(name, 1); head.addWidget(self.more_btn)

        self.folder_btn = QPushButton("Open a folder")
        self.folder_btn.setToolTip(f"Open a folder of photos ({shortcut_text('Ctrl+O')})")
        self.folder_btn.setStyleSheet("text-align: left; padding: 7px 8px;")
        self.folder_btn.clicked.connect(self._ask_folder)

        self.search = QLineEdit(); self.search.setObjectName("search"); self.search.setPlaceholderText("Search looks")
        self.search.setClearButtonEnabled(True); self.search.setAccessibleName("Search looks")
        self.search.textChanged.connect(self._populate_looks)

        chips = QHBoxLayout(); chips.setSpacing(4); chips.setContentsMargins(0, 0, 0, 0)
        self.chip_group = QButtonGroup(self); self.chip_group.setExclusive(True)
        for mode, text in (("all", "All"), ("fav", "Favourites"), ("custom", "Yours")):
            b = QToolButton(); b.setObjectName("chip"); b.setText(text); b.setCheckable(True)
            b.setChecked(mode == "all")
            b.clicked.connect(lambda _=False, m=mode: self._set_filter(m))
            self.chip_group.addButton(b); chips.addWidget(b)
        chips.addStretch(1)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(2)
        self.tree.setIconSize(QSize(46, 31))
        self.tree.setIndentation(0)
        self.tree.setRootIsDecorated(False)
        self.tree.setAnimated(True)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.tree.header().resizeSection(1, 26)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tree.setAccessibleName("Looks")
        self.tree.itemClicked.connect(self._look_clicked)
        self.tree.currentItemChanged.connect(lambda cur, _: self._look_clicked(cur, 0, keyboard=True))
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._look_menu)

        lay.addLayout(head); lay.addSpacing(4); lay.addWidget(self.folder_btn); lay.addWidget(self.search)
        lay.addLayout(chips); lay.addWidget(self.tree, 1)
        return self.sidebar

    def _build_center(self) -> QWidget:
        center = QWidget()
        lay = QVBoxLayout(center); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

        top = QWidget(); top.setObjectName("topbar"); top.setFixedHeight(48)
        tl = QHBoxLayout(top); tl.setContentsMargins(14, 0, 12, 0); tl.setSpacing(6)
        self.photo_name = QLabel(""); self.photo_name.setObjectName("photoName")
        self.compare_btn = QToolButton(); self.compare_btn.setCheckable(True)
        self.compare_btn.setToolTip("Compare with the original (or hold \\)")
        self.compare_btn.setAccessibleName("Compare with original")
        self.compare_btn.toggled.connect(lambda on: self.preview.set_show_original(on))
        self.export_btn = QPushButton("Export"); self.export_btn.setObjectName("primary")
        self.export_btn.setToolTip(f"Export photos with this look ({shortcut_text('Ctrl+E')})")
        self.export_btn.clicked.connect(self._export)
        tl.addWidget(self.photo_name, 1); tl.addWidget(self.compare_btn); tl.addSpacing(4); tl.addWidget(self.export_btn)

        self.canvas = QWidget()
        cl = QVBoxLayout(self.canvas); cl.setContentsMargins(0, 0, 0, 0)
        self.preview = PreviewView()
        self.preview.files_dropped.connect(self._dropped)
        cl.addWidget(self.preview)
        self.canvas.installEventFilter(self)

        self.toast = QLabel(self.canvas); self.toast.hide()
        self.toast.setWordWrap(True)
        self.toast.setTextFormat(Qt.PlainText)

        self.bubble = AssistantBubble(self.canvas)
        self.bubble.toggled.connect(self._toggle_chat)
        self.chat = ChatPanel(self.store, self._chat_context, self.canvas)
        self.chat.hide()
        self.chat.closed.connect(lambda: self.bubble.setChecked(False))
        self.chat.look_proposed.connect(self._apply_assistant_look)
        self.chat.undo_requested.connect(self._undo_assistant_look)
        self.chat.save_requested.connect(self._save_custom)

        self.filmstrip = QListWidget()
        self.filmstrip.setObjectName("filmstrip")
        self.filmstrip.setViewMode(QListView.IconMode)
        self.filmstrip.setFlow(QListView.LeftToRight)
        self.filmstrip.setWrapping(False)
        self.filmstrip.setMovement(QListView.Static)
        self.filmstrip.setIconSize(QSize(96, 64))
        self.filmstrip.setFixedHeight(88)
        self.filmstrip.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.filmstrip.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.filmstrip.currentItemChanged.connect(self._photo_changed)
        self.filmstrip.setAccessibleName("Photos")
        self.filmstrip.hide()

        lay.addWidget(top); lay.addWidget(self.canvas, 1); lay.addWidget(self.filmstrip)
        self._placeholder = QIcon(self._blank(96, 64))
        return center

    def _build_inspector(self) -> QWidget:
        self.inspector = QWidget(); self.inspector.setObjectName("inspector"); self.inspector.setFixedWidth(300)
        inner = QWidget(); inner.setObjectName("inspector")
        lay = QVBoxLayout(inner); lay.setContentsMargins(18, 16, 18, 16); lay.setSpacing(4)

        self.look_title = QLabel(); self.look_title.setObjectName("title"); self.look_title.setWordWrap(True)
        self.look_title.setTextFormat(Qt.PlainText)
        self.fav_btn = QToolButton(); self.fav_btn.setAccessibleName("Favourite")
        self.fav_btn.clicked.connect(self._toggle_current_favourite)
        title_row = QHBoxLayout(); title_row.addWidget(self.look_title, 1); title_row.addWidget(self.fav_btn, 0, Qt.AlignTop)
        self.look_brand = QLabel(); self.look_brand.setObjectName("subtle")
        lay.addLayout(title_row); lay.addWidget(self.look_brand); lay.addSpacing(12)

        self.strength_slider = AdjustSlider("strength", "Strength", 0, 100, 1, "{:.0f}%")
        self.strength_slider.default = 100
        self.strength_slider.set_value(100)
        self.strength_slider.changed.connect(self._strength_changed)
        lay.addWidget(self.strength_slider); lay.addSpacing(6)

        self.sliders: dict[str, AdjustSlider] = {}
        self.sections: list[Section] = []
        open_sections = self.store.get("open_sections", ["Light", "Colour", "Film"])
        for name, items in SLIDERS:
            sec = Section(name, expanded=name in open_sections)
            sec.head.toggled.connect(self._remember_sections)
            for key, text, lo, hi, step, fmt in items:
                s = AdjustSlider(key, text, lo, hi, step, fmt)
                s.changed.connect(self._param_changed)
                self.sliders[key] = s
                sec.add(s)
            if name == "Colour":
                self.mono_box = QCheckBox("Black && white")
                self.mono_box.toggled.connect(lambda on: self._param_changed("mono", on))
                sec.add(self.mono_box)
            self.sections.append(sec)
            lay.addWidget(sec)
        lay.addStretch(1)

        self.reset_btn = QPushButton("Reset"); self.reset_btn.setObjectName("link"); self.reset_btn.clicked.connect(self._reset)
        self.save_btn = QPushButton("Save look"); self.save_btn.setObjectName("secondary"); self.save_btn.clicked.connect(self._save_custom)
        self.update_btn = QPushButton("Update"); self.update_btn.setObjectName("secondary"); self.update_btn.clicked.connect(self._update_custom)
        self.update_btn.setToolTip("Save these changes to your custom look")
        foot = QHBoxLayout(); foot.addWidget(self.reset_btn); foot.addStretch(1); foot.addWidget(self.update_btn); foot.addWidget(self.save_btn)
        lay.addLayout(foot)

        scroll = QScrollArea(); scroll.setWidget(inner); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        wrap = QVBoxLayout(self.inspector); wrap.setContentsMargins(0, 0, 0, 0); wrap.addWidget(scroll)
        return self.inspector

    def _build_actions(self):
        def act(text, slot, shortcut=None, checkable=False):
            a = QAction(text, self)
            a.triggered.connect(slot)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.setCheckable(checkable)
            self.addAction(a)   # shortcuts work even where no menu is shown
            return a

        self.a_open = act("Open Folder…", self._ask_folder, "Ctrl+O")
        self.a_add = act("Add Photos…", self._ask_files, "Ctrl+Shift+O")
        self.a_export = act("Export…", self._export, "Ctrl+E")
        self.a_cube = act("Save Look as .cube…", self._export_cube, "Ctrl+Shift+E")
        self.a_fav = act("Favourite Look", self._toggle_current_favourite, "F")
        self.a_assistant = act("Look Assistant", lambda: self.bubble.toggle(), "Ctrl+K")
        self.a_sidebar = act("Show Looks", lambda on: self._set_panel(self.sidebar, "show_sidebar", on), "Ctrl+Alt+1", True)
        self.a_inspector = act("Show Adjustments", lambda on: self._set_panel(self.inspector, "show_inspector", on), "Ctrl+Alt+2", True)
        self.a_sidebar.setChecked(self.store.get("show_sidebar", True))
        self.a_inspector.setChecked(self.store.get("show_inspector", True))
        self.a_about = act("About Emulsa", self._about)

        appearance = QMenu("Appearance", self)
        group = QActionGroup(self)
        for mode, text in (("system", "Match System"), ("light", "Light"), ("dark", "Dark")):
            a = QAction(text, self, checkable=True)
            a.setChecked(self.store.get("appearance", "system") == mode)
            a.triggered.connect(lambda _=False, m=mode: self._set_appearance(m))
            group.addAction(a); appearance.addAction(a)

        menu = QMenu(self)
        for a in (self.a_open, self.a_add, None, self.a_export, self.a_cube, None, self.a_assistant,
                  self.a_sidebar, self.a_inspector):
            menu.addSeparator() if a is None else menu.addAction(a)
        menu.addMenu(appearance); menu.addSeparator(); menu.addAction(self.a_about)
        self.more_btn.setMenu(menu)

        if MAC:  # the Mac menu bar, where Mac users expect these
            bar = self.menuBar()
            f = bar.addMenu("File")
            for a in (self.a_open, self.a_add, None, self.a_export, self.a_cube):
                f.addSeparator() if a is None else f.addAction(a)
            v = bar.addMenu("View")
            for a in (self.a_assistant, self.a_sidebar, self.a_inspector):
                v.addAction(a)
            v.addMenu(appearance)
            h = bar.addMenu("Help")
            self.a_about.setMenuRole(QAction.AboutRole)
            h.addAction(self.a_about)
        else:
            self.menuBar().hide()

    @staticmethod
    def _blank(w, h):
        pm = QPixmap(w, h); pm.fill(theme.qc("hover")); return pm

    # ================================================================== theme and panels
    def refresh_theme(self):
        self.more_btn.setIcon(icons.icon("more", 18))
        self.folder_btn.setIcon(icons.icon("folder", 16))
        self.compare_btn.setIcon(icons.icon("compare", 18))
        for sec in self.sections:
            sec.refresh_icons()
        self.chat.refresh_theme()
        self._placeholder = QIcon(self._blank(96, 64))
        self.toast.setStyleSheet(f"background: {theme.c('text')}; color: {theme.c('bg')}; border-radius: 8px; padding: 8px 12px;")
        if self.look:
            self._set_fav_button(self.store.is_favourite(self.look["id"]))
        for s in self.sliders.values():
            s._update_label()
        self._populate_looks()
        self.preview.update()

    def _theme_changed(self):
        theme.apply()
        self.refresh_theme()

    def _set_appearance(self, mode):
        self.store.set("appearance", mode)
        theme.apply(mode)
        self.refresh_theme()

    def _set_panel(self, panel, key, on):
        panel.setVisible(on)
        self.store.set(key, on)

    def _remember_sections(self, *_):
        self.store.set("open_sections", [s.head.text() for s in self.sections if s.head.isChecked()])

    def show_toast(self, text: str, ms: int = 3500):
        self.toast.setText(text)
        self.toast.setMaximumWidth(min(520, self.canvas.width() - 40))
        self.toast.adjustSize()
        self._place_overlays()
        self.toast.show(); self.toast.raise_()
        self.toast_timer.start(ms)

    def _place_overlays(self):
        w, h = self.canvas.width(), self.canvas.height()
        self.bubble.move(w - self.bubble.width() - 18, h - self.bubble.height() - 18)
        ph = min(620, h - self.bubble.height() - 50)
        self.chat.setFixedHeight(max(380, ph))
        self.chat.move(max(10, w - self.chat.width() - 18), max(10, h - self.chat.height() - self.bubble.height() - 30))
        self.toast.move((w - self.toast.width()) // 2, 16)
        self.bubble.raise_()

    def _toggle_chat(self, on):
        self.chat.setVisible(on)
        if on:
            self._place_overlays()
            self.chat.raise_(); self.bubble.raise_()
            (self.chat.input if self.chat.stack.currentIndex() == 1 else self.chat.key_edit).setFocus()

    # ================================================================== looks list
    def _set_filter(self, mode):
        self.filter_mode = mode
        self._populate_looks()

    def _populate_looks(self, *_):
        text = self.search.text().strip().lower()
        self.tree.blockSignals(True)
        self.tree.clear()
        groups: dict[str, QTreeWidgetItem] = {}
        cap = QFont(self.tree.font()); cap.setPointSizeF(max(8.0, cap.pointSizeF() - 1.5)); cap.setBold(True)
        current_item = None
        for look in self.store.looks():
            fav = self.store.is_favourite(look["id"])
            if text and text not in look["name"].lower() and text not in look["brand"].lower():
                continue
            if self.filter_mode == "fav" and not fav:
                continue
            if self.filter_mode == "custom" and look["brand"] != "Custom":
                continue
            brand = "Your looks" if look["brand"] == "Custom" else look["brand"]
            group = groups.get(brand)
            if group is None:
                group = QTreeWidgetItem(self.tree, [brand.upper(), ""])
                group.setFont(0, cap)
                group.setFlags(Qt.ItemIsEnabled)
                group.setForeground(0, theme.qc("muted"))
                group.setSizeHint(0, QSize(10, 30))
                groups[brand] = group
            item = QTreeWidgetItem(group, [look["name"], ""])
            item.setData(0, LOOK_ROLE, look["id"])
            item.setIcon(0, self.look_icons.get(look["id"], QIcon()))
            item.setText(1, "★" if fav else "")
            item.setForeground(1, theme.qc("accent"))
            item.setTextAlignment(1, Qt.AlignCenter)
            item.setToolTip(1, "Favourite. Press F to remove." if fav else "")
            if self.look and look["id"] == self.look["id"]:
                current_item = item
        self.tree.expandAll()
        if current_item:
            self.tree.setCurrentItem(current_item)
        self.tree.blockSignals(False)
        if not groups:
            msg = {"fav": "No favourites yet.\nSelect a look and press F.",
                   "custom": "No looks of your own yet.\nAdjust one and choose Save look."}.get(self.filter_mode, "No looks match.")
            empty = QTreeWidgetItem(self.tree, [msg, ""])
            empty.setFlags(Qt.NoItemFlags)
            empty.setForeground(0, theme.qc("muted"))

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
            self.undo_state = None
            self.choose_look(look)

    def _refresh_fav_marks(self):
        it = QTreeWidgetItemIterator(self.tree)
        while it.value():
            item = it.value()
            lid = item.data(0, LOOK_ROLE)
            if lid:
                item.setText(1, "★" if self.store.is_favourite(lid) else "")
            it += 1
        if self.look:
            self._set_fav_button(self.store.is_favourite(self.look["id"]))
        if self.filter_mode == "fav":
            self._populate_looks()

    def _set_fav_button(self, fav: bool):
        is_assistant = bool(self.look) and self.look["id"] == ASSISTANT_ID
        self.fav_btn.setVisible(not is_assistant)
        self.fav_btn.setIcon(icons.icon("star-filled" if fav else "star", 18, "accent" if fav else "muted"))
        self.fav_btn.setToolTip(("Remove from favourites" if fav else "Add to favourites") + " (F)")

    def _toggle_current_favourite(self):
        if self.look and self.look["id"] != ASSISTANT_ID:
            fav = self.store.toggle_favourite(self.look["id"])
            self._refresh_fav_marks()
            self.show_toast(f"Added “{self.look['name']}” to favourites." if fav else "Removed from favourites.")

    def _look_menu(self, pos):
        item = self.tree.itemAt(pos)
        lid = item.data(0, LOOK_ROLE) if item else None
        look = self.store.look(lid) if lid else None
        if not look:
            return
        menu = QMenu(self)
        fav = self.store.is_favourite(lid)
        menu.addAction("Remove from Favourites" if fav else "Add to Favourites",
                       lambda: (self.store.toggle_favourite(lid), self._refresh_fav_marks()))
        menu.addAction("Save as .cube…", lambda: self._export_cube(look))
        if not look.get("builtin"):
            menu.addSeparator()
            menu.addAction("Rename…", lambda: self._rename_custom(look))
            menu.addAction("Delete", lambda: self._delete_custom(look))
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    # ================================================================== choosing and editing a look
    def choose_look(self, look: dict):
        self.look = look
        self.base_params = resolve(look["params"])
        self.params = copy.deepcopy(self.base_params)
        if look["id"] != ASSISTANT_ID:
            self.store.set("last_look", look["id"])
        self.look_title.setText(look["name"])
        brand = {"Custom": "Your look", "Assistant": "Made by the look assistant"}.get(look["brand"], look["brand"])
        self.look_brand.setText(brand)
        self._set_fav_button(self.store.is_favourite(look["id"]))
        self._sync_sliders()
        self._update_edited()
        self._select_in_tree(look["id"])
        self._schedule_render()

    def _select_in_tree(self, look_id):
        self.tree.blockSignals(True)
        self.tree.clearSelection()
        it = QTreeWidgetItemIterator(self.tree)
        while it.value():
            if it.value().data(0, LOOK_ROLE) == look_id:
                self.tree.setCurrentItem(it.value())
                self.tree.scrollToItem(it.value())
                break
            it += 1
        self.tree.blockSignals(False)

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
        self.reset_btn.setEnabled(edited)
        is_custom = bool(self.look) and not self.look.get("builtin")
        self.update_btn.setVisible(is_custom and edited)
        self.save_btn.setText("Save as new" if is_custom and edited else "Save look")

    def _reset(self):
        self.params = copy.deepcopy(self.base_params)
        self._sync_sliders()
        self._update_edited()
        self._schedule_render()

    def _save_custom(self):
        if not self.look:
            return
        default = self.look["name"] if self.look["id"] == ASSISTANT_ID else f"{self.look['name']} (mine)"
        name, ok = QInputDialog.getText(self, "Save look", "Name:", text=default)
        if not ok or not name.strip():
            return
        look = self.store.add_custom(name, self.params, self.look["id"])
        self.look_icons.pop(look["id"], None)
        self.undo_state = None
        self.choose_look(look)
        self._populate_looks()
        self._refresh_icons()
        self.show_toast(f"Saved “{look['name']}” to your looks.")

    def _update_custom(self):
        if not self.look or self.look.get("builtin"):
            return
        for l in self.store.data["custom"]:
            if l["id"] == self.look["id"]:
                l["params"] = copy.deepcopy(self.params)
        self.store.save()
        self.choose_look(self.store.look(self.look["id"]))
        self._refresh_icons()
        self.show_toast("Look updated.")

    def _rename_custom(self, look):
        name, ok = QInputDialog.getText(self, "Rename look", "Name:", text=look["name"])
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

    # ================================================================== the look assistant
    def _chat_context(self):
        """A screen-sized copy of the photo with the current look, and the current settings."""
        params = copy.deepcopy(self.params)
        if self.preview_arr is None:
            return None, params
        h, w = self.preview_arr.shape[:2]
        s = min(1.0, 1024 / max(h, w))
        small = self.preview_arr if s >= 1 else np.asarray(
            Image.fromarray((self.preview_arr * 255 + 0.5).astype(np.uint8)).resize((round(w * s), round(h * s)), Image.BILINEAR),
            dtype=np.float32) / 255.0
        from ..engine import render
        return render(small, params, strength=self.strength, scale=0.2), params

    def _apply_assistant_look(self, name, params):
        if self.undo_state is None or (self.look and self.look["id"] != ASSISTANT_ID):
            self.undo_state = (self.look, copy.deepcopy(self.params))
        self.choose_look({"id": ASSISTANT_ID, "name": name, "brand": "Assistant", "params": params, "builtin": True})
        self.tree.clearSelection()

    def _undo_assistant_look(self):
        if not self.undo_state:
            self.show_toast("Nothing to undo.")
            return
        look, params = self.undo_state
        self.undo_state = None
        self.choose_look(look)
        self.params = params
        self._sync_sliders(); self._update_edited(); self._schedule_render()
        self._populate_looks()
        self.show_toast(f"Back to “{look['name']}”.")

    # ================================================================== photos
    def _ask_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Open a folder of photos", self.store.get("last_folder", ""))
        if d:
            self.open_folder(d)

    def _ask_files(self):
        exts = " ".join(f"*{e}" for e in sorted(imageio.SUPPORTED))
        files, _ = QFileDialog.getOpenFileNames(self, "Add photos", self.store.get("last_folder", ""),
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
            self.show_toast("None of those are photos Emulsa can open.")

    def open_folder(self, folder):
        files = imageio.list_photos(folder)
        self.store.set("last_folder", folder)
        self.folder_btn.setText(os.path.basename(os.path.normpath(folder)) or folder)
        self.folder_btn.setToolTip(folder)
        if not files:
            self.set_files([])
            self.preview.clear("No photos in this folder", "Emulsa opens JPEG, PNG, TIFF and RAW files.")
            return
        self.set_files(files)

    def set_files(self, files):
        self.files = list(files)
        if files:
            folder = os.path.dirname(files[0])
            self.store.set("last_folder", folder)
            self.folder_btn.setText(os.path.basename(os.path.normpath(folder)) or folder)
            self.folder_btn.setToolTip(folder)
        self.filmstrip.blockSignals(True)
        self.filmstrip.clear()
        self.thumbs.clear()
        for path in self.files:
            item = QListWidgetItem(self._placeholder, "")
            item.setData(PATH_ROLE, path)
            item.setToolTip(os.path.basename(path))
            item.setSizeHint(QSize(104, 74))
            self.filmstrip.addItem(item)
            self.thumbs[path] = item
            job = thumbnail_job(path, 200)
            job.signals.done.connect(self._thumb_ready)
            self.pool.start(job, priority=-1)
        self.filmstrip.blockSignals(False)
        self.filmstrip.setVisible(len(self.files) > 1)
        if self.files:
            self.filmstrip.setCurrentRow(0)
            self._photo_changed(self.filmstrip.currentItem())
        else:
            self.current = None
            self.preview_arr = None
            self.photo_name.setText("")

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
        self.photo_name.setText(f"Opening {os.path.basename(path)}…")
        job = preview_job(path)
        job.signals.done.connect(self._preview_ready)
        job.signals.failed.connect(self._preview_failed)
        self.pool.start(job, priority=5)

    def _preview_ready(self, path, arr):
        if path != self.current:
            return
        self.preview_arr = arr
        fw = imageio.full_width(path)
        self.grain_scale = arr.shape[1] / fw if fw else 0.3
        self.preview.set_images(original=to_qimage(arr))
        self.preview.graded = None
        n = f"   {self.filmstrip.currentRow() + 1} of {len(self.files)}" if len(self.files) > 1 else ""
        self.photo_name.setText(f"{os.path.basename(path)}{n}")
        self._render()
        self._refresh_icons()

    def _preview_failed(self, path, exc):
        if path == self.current:
            self.preview.clear(f"Couldn't open {os.path.basename(path)}", str(exc))
            self.photo_name.setText("")

    # ================================================================== rendering
    def _schedule_render(self):
        if self.preview_arr is not None:
            self.render_timer.start()

    def _render(self):
        if self.preview_arr is None:
            return
        self.render_token += 1
        job = render_job(self.render_token, self.preview_arr, copy.deepcopy(self.params), self.strength, self.grain_scale)
        job.signals.done.connect(self._render_ready)
        self.pool.start(job, priority=10)

    def _render_ready(self, token, qimg):
        if token != self.render_token:
            return
        self.preview.set_images(graded=qimg)

    def _refresh_icons(self):
        if self.preview_arr is None:
            return
        self.icons_token += 1
        h, w = self.preview_arr.shape[:2]
        tw = 92
        small = Image.fromarray((self.preview_arr * 255 + 0.5).astype(np.uint8)).resize((tw, max(1, round(h * tw / w))), Image.BILINEAR)
        small = np.asarray(small, dtype=np.float32) / 255.0
        job = look_icons_job(self.icons_token, small, self.store.looks())
        job.signals.done.connect(self._icons_ready)
        self.pool.start(job, priority=-2)

    def _icons_ready(self, token, imgs):
        if token != self.icons_token:
            return
        self.look_icons = {lid: QIcon(QPixmap.fromImage(q)) for lid, q in imgs.items()}
        it = QTreeWidgetItemIterator(self.tree)
        while it.value():
            item = it.value()
            lid = item.data(0, LOOK_ROLE)
            if lid in self.look_icons:
                item.setIcon(0, self.look_icons[lid])
            it += 1

    # ================================================================== export
    def _selected_files(self):
        sel = [i.data(PATH_ROLE) for i in self.filmstrip.selectedItems()]
        return sel or ([self.current] if self.current else [])

    def _export(self):
        if not self.files:
            self.show_toast("Open some photos first.")
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
        p = resolve(params)
        note = " Grain and vignette aren't part of a LUT." if p["grain"] or p["vignette"] else ""
        self.show_toast(f"Saved {os.path.basename(path)}.{note}")

    def _about(self):
        QMessageBox.about(self, "About Emulsa",
                          f"<b>Emulsa {__version__}</b><br>Film looks for your photos.<br><br>"
                          "Looks based on Recipe Lab v1.7.0 by André Domingues.<br>MIT licence.")

    # ================================================================== window events
    def eventFilter(self, obj, e):
        if obj is self.canvas and e.type() == QEvent.Resize:
            self._place_overlays()
        # hold \ anywhere in the window to see the original
        elif e.type() in (QEvent.KeyPress, QEvent.KeyRelease) and getattr(e, "key", lambda: None)() == Qt.Key_Backslash \
                and self.isActiveWindow() and not isinstance(QApplication.focusWidget(), (QLineEdit,)) \
                and QApplication.focusWidget() is not getattr(self.chat, "input", None):
            if not e.isAutoRepeat():
                self.preview.set_show_original(e.type() == QEvent.KeyPress or self.compare_btn.isChecked())
            return True
        return super().eventFilter(obj, e)

    def closeEvent(self, e):
        self.store.set("geometry", bytes(self.saveGeometry().toBase64()).decode())
        super().closeEvent(e)
