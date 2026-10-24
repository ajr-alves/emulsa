"""The look assistant panel: a chat that floats over the photo, opened from the corner bubble."""
from __future__ import annotations

import os

import numpy as np
from PySide6.QtCore import QEvent, QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QStackedWidget,
                               QToolButton, QVBoxLayout, QWidget)

from .. import assistant, imageio
from . import icons, theme
from .workers import Job, pil_to_qimage

KEY_URL = "https://platform.claude.com/"


class ChatPanel(QFrame):
    """Signals carry everything the main window needs; the panel never touches the photo itself."""
    look_proposed = Signal(str, dict)     # name, engine parameters
    undo_requested = Signal()
    save_requested = Signal()
    closed = Signal()

    def __init__(self, store, context_provider, parent=None):
        """``context_provider()`` returns (photo with current look as float RGB or None, current params)."""
        super().__init__(parent)
        self.setObjectName("chatPanel")
        self.store = store
        self.context_provider = context_provider
        self.keys = assistant.KeyStore()
        self.conversation: assistant.Conversation | None = None
        self.pending_refs: list[tuple[str, np.ndarray]] = []
        self.busy = False
        self.pool = QThreadPool.globalInstance()
        self.setFixedWidth(380)
        self.setMinimumHeight(420)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(36); shadow.setOffset(0, 8); shadow.setColor(QColor(0, 0, 0, 60))
        self.setGraphicsEffect(shadow)

        # header
        self.title = QLabel("Look assistant"); self.title.setObjectName("appName")
        self.settings_btn = QToolButton(); self.settings_btn.setToolTip("API key and model")
        self.settings_btn.setAccessibleName("Assistant settings")
        self.settings_btn.clicked.connect(lambda: self._show_setup())
        self.new_btn = QToolButton(); self.new_btn.setToolTip("Start a new conversation")
        self.new_btn.setAccessibleName("New conversation")
        self.new_btn.clicked.connect(self._new_chat)
        self.close_btn = QToolButton(); self.close_btn.setToolTip("Close"); self.close_btn.setAccessibleName("Close assistant")
        self.close_btn.clicked.connect(self.closed.emit)
        head = QHBoxLayout(); head.setContentsMargins(16, 12, 10, 8)
        head.addWidget(self.title, 1); head.addWidget(self.new_btn); head.addWidget(self.settings_btn); head.addWidget(self.close_btn)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_setup())
        self.stack.addWidget(self._build_chat())

        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        lay.addLayout(head); lay.addWidget(self.stack, 1)
        self.refresh_theme()
        if self.keys.get():
            self.stack.setCurrentIndex(1)
            self._greet()
        else:
            self._show_setup(focus=False)

    # ------------------------------------------------------------------ setup page
    def _build_setup(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w); lay.setContentsMargins(16, 4, 16, 16); lay.setSpacing(10)
        intro = QLabel("Describe a look, or show the assistant a photo whose colours you like, and it builds "
                       "the look for you. It runs on Claude, using your own Anthropic API key.")
        intro.setWordWrap(True)
        how = QLabel(f'Get a key from the <a href="{KEY_URL}">Claude Console</a> under API keys. '
                     "Usage is billed to your Anthropic account, usually a few cents per message.")
        how.setWordWrap(True); how.setOpenExternalLinks(True); how.setObjectName("subtle")
        self.key_edit = QLineEdit(); self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("Paste your API key (sk-ant-…)")
        self.key_edit.setAccessibleName("Anthropic API key")
        self.key_status = QLabel(); self.key_status.setObjectName("subtle")
        self.model_box = QComboBox()
        for mid, label in assistant.MODELS:
            self.model_box.addItem(label, mid)
        current = self.store.get("assistant_model", assistant.DEFAULT_MODEL)
        idx = self.model_box.findData(current)
        self.model_box.setCurrentIndex(max(0, idx))
        privacy = QFrame(); privacy.setObjectName("notice")
        pl = QVBoxLayout(privacy); pl.setContentsMargins(12, 10, 12, 10)
        storage = ("your system keychain" if self.keys.persistent else
                   "memory until you close Emulsa (no system keychain was found)")
        note = QLabel("Privacy: when you send a message, a smaller copy of the current photo and any reference "
                      f"photos you attach go to Anthropic to answer it. Your key is kept in {storage}, "
                      "never in Emulsa's settings file.")
        note.setWordWrap(True); note.setObjectName("subtle")
        pl.addWidget(note)
        self.save_key_btn = QPushButton("Save and start"); self.save_key_btn.setObjectName("primary")
        self.save_key_btn.clicked.connect(self._save_key)
        self.remove_key_btn = QPushButton("Remove key"); self.remove_key_btn.setObjectName("link")
        self.remove_key_btn.clicked.connect(self._remove_key)
        btns = QHBoxLayout(); btns.addWidget(self.remove_key_btn); btns.addStretch(1); btns.addWidget(self.save_key_btn)
        model_label = QLabel("Model"); model_label.setObjectName("caption")
        key_label = QLabel("API key"); key_label.setObjectName("caption")
        for x in (intro, how, key_label, self.key_edit, self.key_status, model_label, self.model_box, privacy):
            lay.addWidget(x)
        lay.addStretch(1); lay.addLayout(btns)
        self.key_edit.returnPressed.connect(self._save_key)
        return w

    def _show_setup(self, focus: bool = True):
        key = self.keys.get()
        self.key_edit.clear()
        self.key_status.setText(f"Saved key: {assistant.mask_key(key)}" if key else "No key saved yet.")
        self.remove_key_btn.setVisible(bool(key) and not os.environ.get("ANTHROPIC_API_KEY"))
        self.save_key_btn.setText("Save" if key else "Save and start")
        self.stack.setCurrentIndex(0)
        if focus:
            self.key_edit.setFocus()

    def _save_key(self):
        key = self.key_edit.text().strip()
        if key:
            if len(key) < 20 or any(ch.isspace() for ch in key):
                self.key_status.setText("That doesn't look like an API key. Copy the whole key from the Console.")
                return
            self.keys.set(key)
        elif not self.keys.get():
            self.key_status.setText("Paste a key first.")
            return
        self.key_edit.clear()
        self.store.set("assistant_model", self.model_box.currentData())
        self.conversation = None  # a new key or model starts a fresh conversation
        self.stack.setCurrentIndex(1)
        if not self.messages_layout.count() - 1:
            self._greet()
        self.input.setFocus()

    def _remove_key(self):
        self.keys.clear()
        self.conversation = None
        self._show_setup()

    # ------------------------------------------------------------------ chat page
    def _build_chat(self) -> QWidget:
        w = QWidget()
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        self.messages_layout = QVBoxLayout(inner)
        self.messages_layout.setContentsMargins(16, 4, 16, 8); self.messages_layout.setSpacing(10)
        self.messages_layout.addStretch(1)
        self.scroll.setWidget(inner)

        self.attach_row = QHBoxLayout(); self.attach_row.setSpacing(6)
        self.attach_box = QWidget(); self.attach_box.setLayout(self.attach_row); self.attach_box.hide()
        self.attach_row.setContentsMargins(14, 0, 14, 0)

        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("Describe a look, or attach a reference photo…")
        self.input.setFixedHeight(64)
        self.input.setAccessibleName("Message to the look assistant")
        self.input.installEventFilter(self)
        self.attach_btn = QToolButton(); self.attach_btn.setToolTip("Attach a reference photo")
        self.attach_btn.setAccessibleName("Attach reference photo")
        self.attach_btn.clicked.connect(self._attach)
        self.send_btn = QPushButton(); self.send_btn.setObjectName("primary"); self.send_btn.setToolTip("Send (Enter)")
        self.send_btn.setAccessibleName("Send message")
        self.send_btn.setFixedSize(34, 34)
        self.send_btn.clicked.connect(self._send)
        row = QHBoxLayout(); row.setContentsMargins(12, 6, 12, 12); row.setSpacing(6)
        row.addWidget(self.attach_btn, 0, Qt.AlignBottom); row.addWidget(self.input, 1); row.addWidget(self.send_btn, 0, Qt.AlignBottom)

        lay = QVBoxLayout(w); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(4)
        lay.addWidget(self.scroll, 1); lay.addWidget(self.attach_box); lay.addLayout(row)
        self.setAcceptDrops(True)
        return w

    def _greet(self):
        self._add_text("Tell me the look you're after, like “warm 70s film with faded blacks”, or attach a "
                       "photo whose colours you want and I'll match it on your photo.", "bubbleBot")

    def _new_chat(self):
        self.conversation = None
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._clear_refs()
        if self.keys.get():
            self.stack.setCurrentIndex(1)
            self._greet()

    def eventFilter(self, obj, e):
        if obj is self.input and e.type() == QEvent.KeyPress and e.key() in (Qt.Key_Return, Qt.Key_Enter) \
                and not (e.modifiers() & Qt.ShiftModifier):
            self._send()
            return True
        return super().eventFilter(obj, e)

    # attachments ---------------------------------------------------------
    def _attach(self):
        exts = " ".join(f"*{e}" for e in sorted(imageio.SUPPORTED))
        files, _ = QFileDialog.getOpenFileNames(self, "Choose reference photos", "", f"Photos ({exts} {exts.upper()})")
        self.add_references(files)

    def add_references(self, paths):
        for path in paths:
            if len(self.pending_refs) >= 4:
                self._add_text("You can attach up to 4 reference photos per message.", "bubbleError")
                break
            if not imageio.is_supported(path):
                continue
            try:
                arr = imageio.load_preview(path, assistant.MAX_SIDE)
            except Exception as exc:
                self._add_text(f"Couldn't open {os.path.basename(path)}: {exc}", "bubbleError")
                continue
            self.pending_refs.append((path, arr))
        self._render_refs()

    def _render_refs(self):
        while self.attach_row.count():
            item = self.attach_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, (path, arr) in enumerate(self.pending_refs):
            thumb = QToolButton()
            pm = QPixmap.fromImage(_thumb(arr, 56))
            thumb.setIcon(QIcon(pm)); thumb.setIconSize(pm.size())
            thumb.setToolTip(f"{os.path.basename(path)}. Click to remove.")
            thumb.setAccessibleName(f"Remove {os.path.basename(path)}")
            thumb.clicked.connect(lambda _=False, i=i: self._remove_ref(i))
            self.attach_row.addWidget(thumb)
        self.attach_row.addStretch(1)
        self.attach_box.setVisible(bool(self.pending_refs))

    def _remove_ref(self, i):
        if 0 <= i < len(self.pending_refs):
            self.pending_refs.pop(i)
        self._render_refs()

    def _clear_refs(self):
        self.pending_refs = []
        self._render_refs()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.add_references([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])

    # sending ---------------------------------------------------------------
    def _send(self):
        if self.busy:
            return
        text = self.input.toPlainText().strip()
        refs = [arr for _, arr in self.pending_refs]
        if not text and not refs:
            return
        key = self.keys.get()
        if not key:
            self._show_setup()
            return
        photo, params = self.context_provider()
        if self.conversation is None:
            try:
                self.conversation = assistant.Conversation(key, self.store.get("assistant_model", assistant.DEFAULT_MODEL))
            except Exception:
                self._add_text("The assistant couldn't start. Reinstall Emulsa or try again.", "bubbleError")
                return
        self._add_user(text, [arr for _, arr in self.pending_refs])
        self.input.clear()
        self._clear_refs()
        self._set_busy(True)
        conv = self.conversation
        job = Job("chat", lambda: conv.send(text, photo, refs, params))
        job.signals.done.connect(self._on_reply)
        job.signals.failed.connect(self._on_error)
        self.pool.start(job)

    def _on_reply(self, _key, result):
        self._set_busy(False)
        message, look, name = result
        if message:
            self._add_text(message, "bubbleBot")
        if look is not None:
            self._add_look_card(name)
            self.look_proposed.emit(name, look)

    def _on_error(self, _key, exc):
        self._set_busy(False)
        self._add_text(assistant.friendly_error(exc), "bubbleError")

    def _set_busy(self, on: bool):
        self.busy = on
        self.send_btn.setEnabled(not on)
        self.input.setReadOnly(on)
        if on:
            self.thinking = QLabel("Thinking…"); self.thinking.setObjectName("subtle")
            self._append(self.thinking)
        elif getattr(self, "thinking", None) is not None:
            self.thinking._row.deleteLater()
            self.thinking = None

    # message widgets -------------------------------------------------------
    def _append(self, w: QWidget, align=Qt.AlignLeft):
        # wrap in a row with a stretch: word-wrapped labels only get the right height when the
        # layout, not an alignment flag, decides their width
        row = QWidget()
        hl = QHBoxLayout(row); hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(0)
        if align == Qt.AlignRight:
            hl.addStretch(1); hl.addWidget(w, 0)
        elif isinstance(w, QLabel) and w.wordWrap():
            hl.addWidget(w, 1)          # the assistant's text uses the full width of the panel
        else:
            hl.addWidget(w, 0); hl.addStretch(1)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, row)
        w._row = row
        QTimer.singleShot(30, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))
        QTimer.singleShot(120, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))

    def _add_text(self, text: str, kind: str):
        lab = QLabel()
        lab.setTextFormat(Qt.PlainText)   # replies are shown as text, never interpreted as HTML
        lab.setText(text)
        lab.setWordWrap(True)
        lab.setObjectName(kind)
        lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lab.setMaximumWidth(300 if kind == "bubbleUser" else 330)
        lab.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self._append(lab, Qt.AlignRight if kind == "bubbleUser" else Qt.AlignLeft)

    def _add_user(self, text: str, refs):
        if refs:
            row = QWidget(); hl = QHBoxLayout(row); hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(4)
            for arr in refs:
                lab = QLabel(); lab.setPixmap(QPixmap.fromImage(_thumb(arr, 72)))
                hl.addWidget(lab)
            self._append(row, Qt.AlignRight)
        if text:
            self._add_text(text, "bubbleUser")

    def _add_look_card(self, name: str):
        card = QFrame(); card.setObjectName("lookCard"); card.setMaximumWidth(330)
        lay = QVBoxLayout(card); lay.setContentsMargins(12, 10, 12, 10); lay.setSpacing(6)
        title = QLabel(); title.setTextFormat(Qt.PlainText); title.setText(f"Applied “{name}”")
        title.setStyleSheet("font-weight: 600;")
        sub = QLabel("It's on your photo now. Keep tweaking it here or with the sliders.")
        sub.setWordWrap(True); sub.setObjectName("subtle")
        undo = QPushButton("Undo"); undo.setObjectName("secondary"); undo.clicked.connect(self.undo_requested.emit)
        save = QPushButton("Save look"); save.setObjectName("secondary"); save.clicked.connect(self.save_requested.emit)
        btns = QHBoxLayout(); btns.addWidget(undo); btns.addWidget(save); btns.addStretch(1)
        lay.addWidget(title); lay.addWidget(sub); lay.addLayout(btns)
        self._append(card)

    def refresh_theme(self):
        self.settings_btn.setIcon(icons.icon("settings", 16))
        self.new_btn.setIcon(icons.icon("plus", 16))
        self.close_btn.setIcon(icons.icon("close", 16))
        self.attach_btn.setIcon(icons.icon("image", 18))
        self.send_btn.setIcon(icons.icon("send", 16, theme.c("accent_text")))


def _thumb(arr: np.ndarray, size: int):
    from PIL import Image
    img = Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8))
    img.thumbnail((size, size), Image.LANCZOS)
    return pil_to_qimage(img)
