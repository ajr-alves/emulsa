"""The export queue: exports run one after another in the background while you keep working.

``ExportQueue`` holds the jobs and runs them; ``QueueButton`` sits in the top bar and opens
``QueuePanel``, which lists each job with its progress and a way to cancel it or open its folder.
"""
from __future__ import annotations

import itertools
import os

from PySide6.QtCore import QObject, QPoint, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QScrollArea, QToolButton,
                               QVBoxLayout, QWidget)

from ..exporter import ExportSpec, export_photos
from . import icons

QUEUED, RUNNING, DONE, CANCELLED = "queued", "running", "done", "cancelled"
_ids = itertools.count(1)


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


class ExportJob:
    """One export: a look applied to a set of photos, and how far it has got."""

    def __init__(self, spec: ExportSpec):
        self.id = next(_ids)
        self.spec = spec
        self.state = QUEUED
        self.done = 0           # photos processed so far, exported or failed
        self.exported = 0
        self.errors: list = []
        self.current = ""       # file name being exported right now
        self.stop_requested = False

    @property
    def total(self) -> int:
        return len(self.spec.files)

    @property
    def active(self) -> bool:
        return self.state in (QUEUED, RUNNING)

    def summary(self) -> str:
        """One line saying where this job is, for the queue panel."""
        if self.state == QUEUED:
            return f"{plural(self.total, 'photo')}, waiting to start"
        if self.state == RUNNING:
            name = f": {self.current}" if self.current else ""
            return f"Exporting {self.done + 1 if self.current else self.done} of {self.total}{name}"
        if self.state == CANCELLED:
            return f"Cancelled after {self.exported} of {self.total}" if self.exported else "Cancelled"
        if self.errors:
            failed = "; ".join(f"{n} ({e})" for n, e in self.errors[:2])
            more = f" and {len(self.errors) - 2} more" if len(self.errors) > 2 else ""
            return f"Exported {self.exported} of {self.total}. Couldn't export {failed}{more}."
        return f"Exported {plural(self.exported, 'photo')}"


class _Worker(QThread):
    progress = Signal(int, int, str)
    finished_job = Signal(int, list)

    def __init__(self, job: ExportJob):
        super().__init__()
        self.job = job

    def run(self):
        count, errors = export_photos(self.job.spec, progress=self.progress.emit,
                                      should_stop=lambda: self.job.stop_requested)
        self.finished_job.emit(count, errors)


class ExportQueue(QObject):
    """Runs export jobs one at a time, in the order they were added."""
    changed = Signal()
    job_finished = Signal(object)   # ExportJob

    def __init__(self, parent=None):
        super().__init__(parent)
        self.jobs: list[ExportJob] = []
        self._worker: _Worker | None = None

    # ---------------------------------------------------------------- state
    def active_jobs(self) -> list[ExportJob]:
        return [j for j in self.jobs if j.active]

    def photos_left(self) -> int:
        return sum(j.total - j.done for j in self.active_jobs())

    def progress(self) -> tuple[int, int]:
        """(photos done, photos in total) across the jobs still running or waiting."""
        jobs = self.active_jobs()
        return sum(j.done for j in jobs), sum(j.total for j in jobs)

    # ---------------------------------------------------------------- control
    def add(self, spec: ExportSpec) -> ExportJob:
        job = ExportJob(spec)
        self.jobs.append(job)
        self._start_next()
        self.changed.emit()
        return job

    def cancel(self, job: ExportJob) -> None:
        if job.state == QUEUED:
            job.state = CANCELLED
            self.changed.emit()
            self.job_finished.emit(job)
        elif job.state == RUNNING:
            job.stop_requested = True     # the worker stops before its next photo

    def cancel_all(self, wait_ms: int = 0) -> None:
        for job in list(self.jobs):
            self.cancel(job)
        if wait_ms and self._worker is not None:
            self._worker.wait(wait_ms)

    def clear_finished(self) -> None:
        self.jobs = [j for j in self.jobs if j.active]
        self.changed.emit()

    def _start_next(self) -> None:
        if self._worker is not None:
            return
        job = next((j for j in self.jobs if j.state == QUEUED), None)
        if job is None:
            return
        try:
            os.makedirs(job.spec.out_dir, exist_ok=True)
        except OSError as exc:
            job.state, job.errors = DONE, [(job.spec.out_dir, exc.strerror or str(exc))]
            self.job_finished.emit(job)
            self._start_next()
            return
        job.state = RUNNING
        self._worker = _Worker(job)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_job.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, done: int, _total: int, name: str) -> None:
        job = self._worker.job if self._worker else None
        if job is not None:
            job.done, job.current = done, name
            self.changed.emit()

    def _on_finished(self, count: int, errors: list) -> None:
        worker, self._worker = self._worker, None
        job = worker.job
        worker.wait()
        worker.deleteLater()
        job.exported, job.errors, job.current = count, errors, ""
        job.state = CANCELLED if job.stop_requested and job.done < job.total else DONE
        self.job_finished.emit(job)
        self._start_next()
        self.changed.emit()


# -------------------------------------------------------------------- the top-bar button and its panel
class QueueButton(QToolButton):
    """Shows export progress in the top bar. Hidden while the queue is empty; click to see the jobs."""

    def __init__(self, queue: ExportQueue, parent=None):
        super().__init__(parent)
        self.queue = queue
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.setAccessibleName("Export queue")
        self.panel = QueuePanel(queue, self)
        self.clicked.connect(self._toggle_panel)
        queue.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        done, total = self.queue.progress()
        if total:
            self.setText(f"{done} of {total} exported")
            self.setToolTip("Exports running in the background. Click to see them.")
        else:
            self.setText("Exports")
            self.setToolTip("Finished exports")
        self.setIcon(icons.icon("export", 16, "accent" if total else "muted"))
        self.setVisible(bool(self.queue.jobs))
        if not self.queue.jobs:
            self.panel.hide()

    def _toggle_panel(self):
        if self.panel.isVisible():
            self.panel.hide()
            return
        self.panel.rebuild()
        self.panel.adjustSize()
        below = self.mapToGlobal(QPoint(self.width(), self.height() + 6))
        self.panel.move(below.x() - self.panel.width(), below.y())
        self.panel.show()


class _JobRow(QWidget):
    def __init__(self, queue: ExportQueue, job: ExportJob, parent=None):
        super().__init__(parent)
        self.queue, self.job = queue, job
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 4, 0, 4); lay.setSpacing(4)
        top = QHBoxLayout(); top.setSpacing(8)
        self.title = QLabel(job.spec.look_name); self.title.setObjectName("updateTitle")
        self.title.setTextFormat(Qt.PlainText)
        self.action = QPushButton(); self.action.setObjectName("link")
        self.action.clicked.connect(self._act)
        top.addWidget(self.title, 1); top.addWidget(self.action)
        self.bar = QProgressBar(); self.bar.setRange(0, max(1, job.total))
        self.text = QLabel(); self.text.setObjectName("subtle"); self.text.setWordWrap(True)
        self.text.setTextFormat(Qt.PlainText)
        lay.addLayout(top); lay.addWidget(self.bar); lay.addWidget(self.text)
        self.refresh()

    def refresh(self):
        job = self.job
        self.bar.setValue(job.done)
        self.bar.setVisible(job.active)
        self.text.setText(job.summary())
        if job.active:
            self.action.setText("Cancel")
            self.action.setToolTip("Stop this export. Photos already saved are kept.")
        else:
            self.action.setText("Show in folder")
            self.action.setToolTip(job.spec.out_dir)
        self.action.setVisible(job.active or os.path.isdir(job.spec.out_dir))

    def _act(self):
        if self.job.active:
            self.queue.cancel(self.job)
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.job.spec.out_dir))


class QueuePanel(QFrame):
    """A small popup listing the export jobs, newest first."""

    def __init__(self, queue: ExportQueue, anchor: QWidget):
        super().__init__(anchor, Qt.Popup)
        self.queue = queue
        self.setObjectName("chatPanel")
        self.setFixedWidth(340)
        lay = QVBoxLayout(self); lay.setContentsMargins(14, 12, 14, 12); lay.setSpacing(8)
        head = QHBoxLayout()
        title = QLabel("Exports"); title.setObjectName("updateTitle")
        self.clear_btn = QPushButton("Clear finished"); self.clear_btn.setObjectName("link")
        self.clear_btn.clicked.connect(queue.clear_finished)
        head.addWidget(title, 1); head.addWidget(self.clear_btn)
        self.list = QWidget()
        self.rows_lay = QVBoxLayout(self.list); self.rows_lay.setContentsMargins(0, 0, 0, 0); self.rows_lay.setSpacing(10)
        scroll = QScrollArea(); scroll.setWidget(self.list); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMaximumHeight(380)
        self.scroll = scroll
        lay.addLayout(head); lay.addWidget(scroll)
        self.rows: dict[int, _JobRow] = {}
        queue.changed.connect(self._changed)

    def rebuild(self):
        while self.rows_lay.count():
            w = self.rows_lay.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        self.rows = {}
        for job in reversed(self.queue.jobs):
            row = _JobRow(self.queue, job)
            self.rows[job.id] = row
            self.rows_lay.addWidget(row)
        self.rows_lay.addStretch(1)
        self.clear_btn.setVisible(any(not j.active for j in self.queue.jobs))
        n = len(self.queue.jobs)
        self.scroll.setMinimumHeight(min(380, 82 * n))

    def _changed(self):
        if not self.isVisible():
            return
        if set(self.rows) != {j.id for j in self.queue.jobs}:
            self.rebuild()
            self.adjustSize()
            return
        for row in self.rows.values():
            row.refresh()
        self.clear_btn.setVisible(any(not j.active for j in self.queue.jobs))
