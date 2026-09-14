from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal, QTimer
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer


_VIRTUAL_MARKERS = (
    "todesk",
    "cable input",
    "cable output",
    "vb-audio",
    "vb cable",
    "virtual",
    "steam streaming",
    "nvidia broadcast",
)


def _is_virtual_device(name: str) -> bool:
    low = (name or "").lower()
    return any(m in low for m in _VIRTUAL_MARKERS)


def pick_audio_output_device():
    """优先系统默认；若默认是虚拟声卡则改选真实设备。"""
    devices = list(QMediaDevices.audioOutputs())
    default = QMediaDevices.defaultAudioOutput()
    if not default.isNull() and not _is_virtual_device(default.description()):
        return default
    for dev in devices:
        if not _is_virtual_device(dev.description()):
            return dev
    return default


class AudioPlayer(QObject):
    position_changed = Signal(int)
    duration_changed = Signal(int)
    playing_changed = Signal(bool)
    media_status_changed = Signal(object)
    error_occurred = Signal(str)
    output_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)
        self._volume = 1.0
        self._playback_rate = 1.0
        self._path: str | None = None
        self._ensure_output()

        self._player.positionChanged.connect(self._on_position)
        self._player.durationChanged.connect(self.duration_changed.emit)
        self._player.playbackStateChanged.connect(self._on_state)
        self._player.mediaStatusChanged.connect(self.media_status_changed.emit)
        self._player.errorOccurred.connect(self._on_error)
        try:
            QMediaDevices.audioOutputsChanged.connect(self._on_devices_changed)
        except Exception:
            pass

        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._tick)

    def _ensure_output(self) -> None:
        device = pick_audio_output_device()
        if not device.isNull():
            self._audio.setDevice(device)
            self.output_changed.emit(device.description())
        self._audio.setMuted(False)
        self._audio.setVolume(float(self._volume))
        # 部分 Qt 版本 setSource 后需重新挂接
        self._player.setAudioOutput(self._audio)
        self._apply_playback_rate()

    def load(self, path: str) -> None:
        self._path = path
        self._ensure_output()
        local = str(Path(path).resolve())
        self._player.setSource(QUrl.fromLocalFile(local))
        self._ensure_output()

    def play(self) -> None:
        self._ensure_output()
        if self._player.source().isEmpty() and self._path:
            self.load(self._path)
            self._ensure_output()
        self._player.play()
        self._apply_playback_rate()
        self._timer.start()

    def pause(self) -> None:
        self._player.pause()
        self._timer.stop()
        self.position_changed.emit(int(self._player.position()))

    def stop(self) -> None:
        self._player.stop()
        self._timer.stop()

    def toggle(self) -> None:
        if self.is_playing():
            self.pause()
        else:
            self.play()

    def seek(self, position_ms: int) -> None:
        self._player.setPosition(max(0, int(position_ms)))
        self.position_changed.emit(int(self._player.position()))

    def set_volume(self, volume: float) -> None:
        self._volume = max(0.0, min(1.0, float(volume)))
        self._audio.setMuted(False)
        self._audio.setVolume(self._volume)

    def set_playback_rate(self, rate: float) -> None:
        self._playback_rate = max(0.25, min(4.0, float(rate)))
        self._apply_playback_rate()

    def playback_rate(self) -> float:
        return float(self._playback_rate)

    def _apply_playback_rate(self) -> None:
        try:
            self._player.setPlaybackRate(self._playback_rate)
        except Exception:
            pass

    def volume(self) -> float:
        return float(self._volume)

    def output_name(self) -> str:
        try:
            return self._audio.device().description()
        except Exception:
            return ""

    def position(self) -> int:
        return int(self._player.position())

    def duration(self) -> int:
        return int(self._player.duration())

    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def _on_position(self, pos: int) -> None:
        self.position_changed.emit(int(pos))

    def _on_state(self, state) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.playing_changed.emit(playing)
        if playing:
            self._timer.start()
        else:
            self._timer.stop()

    def _on_error(self, *_args) -> None:
        msg = self._player.errorString() or "音频播放失败"
        self.error_occurred.emit(msg)

    def _on_devices_changed(self) -> None:
        was_playing = self.is_playing()
        pos = self.position()
        self._ensure_output()
        if was_playing:
            self._player.setPosition(pos)
            self._player.play()

    def _tick(self) -> None:
        if self.is_playing():
            self.position_changed.emit(int(self._player.position()))
