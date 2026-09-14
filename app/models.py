from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any
import uuid


class TrackStatus(str, Enum):
    IDLE = "idle"
    QUEUED = "queued"
    SPLITTING = "splitting"
    RECOGNIZING = "recognizing"
    TRANSLATING = "translating"
    PROOFREADING = "proofreading"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def label(self) -> str:
        return {
            TrackStatus.IDLE: "未翻译",
            TrackStatus.QUEUED: "排队中",
            TrackStatus.SPLITTING: "切分中",
            TrackStatus.RECOGNIZING: "识别中",
            TrackStatus.TRANSLATING: "翻译中",
            TrackStatus.PROOFREADING: "统校中",
            TrackStatus.DONE: "已完成",
            TrackStatus.FAILED: "失败",
            TrackStatus.CANCELLED: "已取消",
        }[self]

    @property
    def is_busy(self) -> bool:
        return self in {
            TrackStatus.QUEUED,
            TrackStatus.SPLITTING,
            TrackStatus.RECOGNIZING,
            TrackStatus.TRANSLATING,
            TrackStatus.PROOFREADING,
        }

    @property
    def is_active_pipeline(self) -> bool:
        return self in {
            TrackStatus.SPLITTING,
            TrackStatus.RECOGNIZING,
            TrackStatus.TRANSLATING,
            TrackStatus.PROOFREADING,
        }


@dataclass
class Cue:
    id: str
    start_ms: int
    end_ms: int
    source_text: str = ""
    target_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Cue":
        return Cue(
            id=str(data.get("id") or uuid.uuid4()),
            start_ms=int(data.get("start_ms", 0)),
            end_ms=int(data.get("end_ms", 0)),
            source_text=str(data.get("source_text", "")),
            target_text=str(data.get("target_text", "")),
        )


@dataclass
class TrackItem:
    id: str
    path: str
    display_name: str
    duration_ms: int = 0
    position_ms: int = 0
    status: TrackStatus = TrackStatus.IDLE
    progress_text: str = "正在等待翻译任务开始"
    error_message: str = ""
    prompt_snapshot: str = ""
    warning_message: str = ""
    cues: list[Cue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "display_name": self.display_name,
            "duration_ms": self.duration_ms,
            "position_ms": self.position_ms,
            "status": self.status.value,
            "progress_text": self.progress_text,
            "error_message": self.error_message,
            "prompt_snapshot": self.prompt_snapshot,
            "warning_message": self.warning_message,
            "cues": [c.to_dict() for c in self.cues],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "TrackItem":
        status_raw = data.get("status", TrackStatus.IDLE.value)
        try:
            status = TrackStatus(status_raw)
        except ValueError:
            status = TrackStatus.IDLE
        # Interrupted pipeline states become cancelled on reload
        if status.is_busy:
            status = TrackStatus.CANCELLED
            progress = "任务已中断，可重新开始"
        else:
            progress = str(data.get("progress_text", "正在等待翻译任务开始"))
        return TrackItem(
            id=str(data.get("id") or uuid.uuid4()),
            path=str(data.get("path", "")),
            display_name=str(data.get("display_name", "")),
            duration_ms=int(data.get("duration_ms", 0)),
            position_ms=int(data.get("position_ms", 0)),
            status=status,
            progress_text=progress,
            error_message=str(data.get("error_message", "")),
            prompt_snapshot=str(data.get("prompt_snapshot", "")),
            warning_message=str(data.get("warning_message", "")),
            cues=[Cue.from_dict(c) for c in data.get("cues", [])],
        )


def new_track_id() -> str:
    return str(uuid.uuid4())


def new_cue_id() -> str:
    return str(uuid.uuid4())
