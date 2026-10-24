"""Batch export: apply the current look to many photos at once."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QProgressBar, QPushButton, QRadioButton, QSpinBox, QVBoxLayout)

from ..looks import slug
from .workers import ExportThread

SIZES = [("Original size", None), ("6000 px long edge", 6000), ("4000 px long edge", 4000),
         ("2048 px long edge", 2048), ("1080 px long edge (Instagram)", 1080)]


class ExportDialog(QDialog):
    def __init__(self, parent, store, all_files, selected_files, look, params, strength):
        super().__init__(parent)
        self.setWindowTitle("Export photos")
        self.setMinimumWidth(480)
        self.store, self.all_files, self.selected_files = store, all_files, selected_files
        self.look, self.params, self.strength = look, params, strength
        self.thread = None

        title = QLabel(f"Apply <b>{look['name']}</b> and save copies.")
        title.setTextFormat(Qt.RichText)
        note = QLabel("Your original files are never changed.")
        note.setObjectName("hint")

        self.sel_radio = QRadioButton(f"Selected photos ({len(selected_files)})")
        self.all_radio = QRadioButton(f"All photos in the folder ({len(all_files)})")
        group = QButtonGroup(self)
        group.addButton(self.sel_radio); group.addButton(self.all_radio)
        (self.sel_radio if selected_files else self.all_radio).setChecked(True)
        self.sel_radio.setEnabled(bool(selected_files))

        default_dir = store.get("export_dir") or (os.path.join(os.path.dirname(all_files[0]), "Emulsa")
                                                  if all_files else os.path.expanduser("~"))
        self.dir_edit = QLineEdit(default_dir)
        browse = QPushButton("Choose…")
        browse.clicked.connect(self._browse)
        dir_row = QHBoxLayout(); dir_row.addWidget(self.dir_edit, 1); dir_row.addWidget(browse)

        self.fmt = QComboBox(); self.fmt.addItems(["JPEG", "TIFF", "PNG"])
        self.fmt.setCurrentText(store.get("export_format", "JPEG"))
        self.quality = QSpinBox(); self.quality.setRange(60, 100)
        self.quality.setValue(int(store.get("export_quality", 92))); self.quality.setSuffix(" %")
        self.fmt.currentTextChanged.connect(lambda t: self.quality.setEnabled(t == "JPEG"))
        self.quality.setEnabled(self.fmt.currentText() == "JPEG")
        self.size = QComboBox()
        for label, _ in SIZES:
            self.size.addItem(label)
        self.size.setCurrentIndex(int(store.get("export_size", 0)))
        self.suffix = QLineEdit("_" + slug(look["name"]))

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.addRow("Photos", self.sel_radio); form.addRow("", self.all_radio)
        form.addRow("Save to", dir_row)
        form.addRow("Format", self.fmt); form.addRow("JPEG quality", self.quality)
        form.addRow("Size", self.size); form.addRow("Add to file name", self.suffix)

        self.progress = QProgressBar(); self.progress.hide()
        self.status = QLabel(""); self.status.setObjectName("hint")
        self.cancel_btn = QPushButton("Cancel"); self.cancel_btn.clicked.connect(self._cancel)
        self.go_btn = QPushButton("Export"); self.go_btn.setObjectName("primary"); self.go_btn.clicked.connect(self._start)
        buttons = QHBoxLayout(); buttons.addWidget(self.status, 1); buttons.addWidget(self.cancel_btn); buttons.addWidget(self.go_btn)

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(title); lay.addWidget(note); lay.addLayout(form); lay.addWidget(self.progress); lay.addLayout(buttons)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Save exports to", self.dir_edit.text())
        if d:
            self.dir_edit.setText(d)

    def _files(self):
        return self.selected_files if self.sel_radio.isChecked() else self.all_files

    def _start(self):
        files = self._files()
        out_dir = self.dir_edit.text().strip()
        if not files:
            self.status.setText("There are no photos to export.")
            return
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as exc:
            self.status.setText(f"Can't use that folder: {exc.strerror}. Choose another one.")
            return
        for k, v in (("export_dir", out_dir), ("export_format", self.fmt.currentText()),
                     ("export_quality", self.quality.value()), ("export_size", self.size.currentIndex())):
            self.store.set(k, v)
        self.go_btn.setEnabled(False)
        self.progress.setRange(0, len(files)); self.progress.setValue(0); self.progress.show()
        self.thread = ExportThread(files, self.params, self.strength, out_dir, self.fmt.currentText(),
                                   self.quality.value(), SIZES[self.size.currentIndex()][1], self.suffix.text())
        self.thread.progress.connect(self._on_progress)
        self.thread.finished_all.connect(self._on_done)
        self.thread.start()

    def _on_progress(self, done, total, name):
        self.progress.setValue(done)
        self.status.setText(f"Exporting {name}  ({done + 1} of {total})" if name else "Finishing…")

    def _on_done(self, count, errors):
        self.thread = None
        self.cancel_btn.setText("Close")
        self.go_btn.setEnabled(True)
        msg = f"Exported {count} photo{'s' if count != 1 else ''} to {self.dir_edit.text()}."
        if errors:
            msg += f" {len(errors)} failed: " + "; ".join(f"{n} ({e})" for n, e in errors[:3])
        self.status.setText(msg)
        self.status.setWordWrap(True)

    def _cancel(self):
        if self.thread is not None:
            self.thread.cancel()
            self.thread.wait(30000)
        self.reject()

    def closeEvent(self, e):
        if self.thread is not None:
            self.thread.cancel()
            self.thread.wait(30000)
        super().closeEvent(e)
