from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
import wave

import numpy as np


@dataclass
class AudioSegmentRef:
    path: Path
    offset_ms: int
    duration_ms: int


class AudioSplitter:
    """Prefer whole-file recognition; split on silence when over limit."""

    def __init__(
        self,
        max_seconds: int = 14400,
        chunk_seconds: int = 1800,
        silence_thresh_db: float = -40.0,
        min_silence_ms: int = 400,
        search_window_sec: float = 30.0,
    ) -> None:
        self.max_seconds = max_seconds
        self.chunk_seconds = chunk_seconds
        self.silence_thresh_db = silence_thresh_db
        self.min_silence_ms = min_silence_ms
        self.search_window_sec = search_window_sec
        self._temp_dir: tempfile.TemporaryDirectory[str] | None = None

    def cleanup(self) -> None:
        if self._temp_dir is not None:
            self._temp_dir.cleanup()
            self._temp_dir = None

    def prepare_segments(
        self,
        audio_path: str | Path,
        duration_ms: int,
        force_split: bool = False,
        progress_cb=None,
    ) -> list[AudioSegmentRef]:
        audio_path = Path(audio_path)
        duration_sec = duration_ms / 1000.0
        if not force_split and duration_sec <= self.max_seconds:
            if progress_cb:
                progress_cb("正在识别 整段")
            return [
                AudioSegmentRef(
                    path=audio_path,
                    offset_ms=0,
                    duration_ms=duration_ms,
                )
            ]

        if progress_cb:
            progress_cb("正在切分…")

        samples, sample_rate = self._load_mono_samples(audio_path)
        total_ms = int(len(samples) / sample_rate * 1000)
        chunk_ms = self.chunk_seconds * 1000
        if chunk_ms <= 0:
            chunk_ms = 1800 * 1000

        cut_points = [0]
        cursor = chunk_ms
        while cursor < total_ms:
            cut = self._find_silence_cut(samples, sample_rate, cursor, total_ms)
            if cut <= cut_points[-1] + 5_000:
                cut = min(cursor, total_ms)
            if cut >= total_ms - 1000:
                break
            cut_points.append(cut)
            cursor = cut + chunk_ms
        cut_points.append(total_ms)

        if self._temp_dir is None:
            self._temp_dir = tempfile.TemporaryDirectory(prefix="xx1_asr_")
        out_dir = Path(self._temp_dir.name)

        segments: list[AudioSegmentRef] = []
        n = len(cut_points) - 1
        for i in range(n):
            start_ms = cut_points[i]
            end_ms = cut_points[i + 1]
            if progress_cb:
                progress_cb(f"正在切分 第 {i + 1}/{n} 段")
            out_path = out_dir / f"seg_{i:04d}.wav"
            self._write_wav_slice(samples, sample_rate, start_ms, end_ms, out_path)
            segments.append(
                AudioSegmentRef(
                    path=out_path,
                    offset_ms=start_ms,
                    duration_ms=end_ms - start_ms,
                )
            )
        return segments

    def _load_mono_samples(self, path: Path) -> tuple[np.ndarray, int]:
        suffix = path.suffix.lower()
        if suffix == ".wav":
            with wave.open(str(path), "rb") as wf:
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                sample_rate = wf.getframerate()
                raw = wf.readframes(wf.getnframes())
            if sampwidth == 1:
                data = np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0
                data /= 128.0
            elif sampwidth == 2:
                data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            elif sampwidth == 4:
                data = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
            else:
                raise RuntimeError(f"不支持的 WAV 位深: {sampwidth}")
            if n_channels > 1:
                data = data.reshape(-1, n_channels).mean(axis=1)
            return data, sample_rate

        try:
            from pydub import AudioSegment
        except ImportError as exc:
            raise RuntimeError("缺少 pydub，无法读取该音频格式") from exc

        seg = AudioSegment.from_file(str(path))
        seg = seg.set_channels(1)
        sample_rate = seg.frame_rate
        samples = np.array(seg.get_array_of_samples()).astype(np.float32)
        max_val = float(1 << (8 * seg.sample_width - 1))
        samples /= max_val
        return samples, sample_rate

    def _find_silence_cut(
        self,
        samples: np.ndarray,
        sample_rate: int,
        target_ms: int,
        total_ms: int,
    ) -> int:
        window_ms = int(self.search_window_sec * 1000)
        start_ms = max(0, target_ms - window_ms)
        end_ms = min(total_ms, target_ms + window_ms)
        start_idx = int(start_ms / 1000 * sample_rate)
        end_idx = int(end_ms / 1000 * sample_rate)
        if end_idx <= start_idx:
            return target_ms

        frame = max(1, int(sample_rate * 0.02))
        best_cut = target_ms
        best_score = -1.0
        min_silence_frames = max(1, int(self.min_silence_ms / 20))
        thresh = 10 ** (self.silence_thresh_db / 20.0)

        i = start_idx
        while i + frame * min_silence_frames <= end_idx:
            chunk = samples[i : i + frame * min_silence_frames]
            rms = float(np.sqrt(np.mean(chunk * chunk) + 1e-12))
            if rms < thresh:
                cut_ms = int((i + len(chunk) // 2) / sample_rate * 1000)
                score = 1.0 / (1.0 + abs(cut_ms - target_ms))
                if score > best_score:
                    best_score = score
                    best_cut = cut_ms
                i += frame * min_silence_frames
            else:
                i += frame
        return best_cut

    def _write_wav_slice(
        self,
        samples: np.ndarray,
        sample_rate: int,
        start_ms: int,
        end_ms: int,
        out_path: Path,
    ) -> None:
        start_idx = int(start_ms / 1000 * sample_rate)
        end_idx = int(end_ms / 1000 * sample_rate)
        slice_data = samples[start_idx:end_idx]
        pcm = np.clip(slice_data * 32767.0, -32768, 32767).astype(np.int16)
        with wave.open(str(out_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm.tobytes())
