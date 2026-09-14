from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, QThread

from app.config import AppConfig
from app.models import TrackItem
from app.services.pipeline import TranslationPipeline, retranslate_cue


class PipelineWorker(QObject):
    progress = Signal(str, str)  # track_id, message
    finished = Signal(str)  # track_id
    failed = Signal(str, str)  # track_id, error
    cancelled = Signal(str)

    def __init__(self, config: AppConfig, track: TrackItem) -> None:
        super().__init__()
        self.config = config
        self.track = track
        self._cancel = False

    def request_cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        pipeline = TranslationPipeline(self.config)

        def progress_cb(msg: str) -> None:
            self.track.progress_text = msg
            self.progress.emit(self.track.id, msg)

        def cancel_check() -> bool:
            return self._cancel

        try:
            pipeline.run(self.track, progress_cb=progress_cb, cancel_check=cancel_check)
            if self._cancel:
                self.cancelled.emit(self.track.id)
            else:
                self.finished.emit(self.track.id)
        except InterruptedError:
            self.cancelled.emit(self.track.id)
        except Exception as exc:
            self.failed.emit(self.track.id, str(exc))


class RetranslateWorker(QObject):
    finished = Signal(str, str)  # cue_id, text
    failed = Signal(str)

    def __init__(self, config: AppConfig, track: TrackItem, cue_id: str) -> None:
        super().__init__()
        self.config = config
        self.track = track
        self.cue_id = cue_id

    def run(self) -> None:
        try:
            text = retranslate_cue(self.config, self.track, self.cue_id)
            self.finished.emit(self.cue_id, text)
        except Exception as exc:
            self.failed.emit(str(exc))


class WorkerHost:
    """Owns QThread lifecycle for one pipeline job."""

    def __init__(self) -> None:
        self.thread: QThread | None = None
        self.worker: PipelineWorker | None = None

    @property
    def busy(self) -> bool:
        return self.thread is not None and self.thread.isRunning()

    def start(self, worker: PipelineWorker) -> None:
        self.stop_join()
        self.worker = worker
        self.thread = QThread()
        worker.moveToThread(self.thread)
        self.thread.started.connect(worker.run)
        self.thread.start()

    def cancel(self) -> None:
        if self.worker:
            self.worker.request_cancel()

    def stop_join(self) -> None:
        if self.thread is not None:
            if self.worker:
                self.worker.request_cancel()
            self.thread.quit()
            self.thread.wait(3000)
            self.thread = None
            self.worker = None
