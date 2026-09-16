from __future__ import annotations

"""把任意 mp3/wav 转成适合百炼 ASR 的 16k 单声道 WAV，并按体积/时长分块。"""

from dataclasses import dataclass
from pathlib import Path
import tempfile
import wave

import numpy as np


@dataclass
class PreparedChunk:
    path: Path
    offset_ms: int
    duration_ms: int


class AudioPreparer:
    def __init__(
        self,
        target_sr: int = 16000,
        max_chunk_seconds: int = 300,
        max_chunk_mb: float = 18.0,
        silence_thresh_db: float = -40.0,
        min_silence_ms: int = 350,
        search_window_sec: float = 25.0,
    ) -> None:
        self.target_sr = target_sr
        self.max_chunk_seconds = max_chunk_seconds
        self.max_chunk_mb = max_chunk_mb
        self.silence_thresh_db = silence_thresh_db
        self.min_silence_ms = min_silence_ms
        self.search_window_sec = search_window_sec
        self._temp_dir: tempfile.TemporaryDirectory[str] | None = None

    def cleanup(self) -> None:
        if self._temp_dir is not None:
            self._temp_dir.cleanup()
            self._temp_dir = None

    def _ensure_temp(self) -> Path:
        if self._temp_dir is None:
            self._temp_dir = tempfile.TemporaryDirectory(prefix="xx1_asr_prep_")
        return Path(self._temp_dir.name)

    def prepare_chunks(
        self,
        audio_path: str | Path,
        *,
        progress_cb=None,
    ) -> list[PreparedChunk]:
        audio_path = Path(audio_path)
        if progress_cb:
            progress_cb("正在转码为 16k 单声道…")
        samples, sr = self._load_mono(audio_path)
        if sr != self.target_sr:
            samples = self._resample(samples, sr, self.target_sr)
            sr = self.target_sr

        total_samples = len(samples)
        total_ms = int(total_samples / sr * 1000)
        bytes_per_sec = sr * 2
        max_bytes = int(self.max_chunk_mb * 1024 * 1024)
        max_sec_by_size = max(30, int(max_bytes / max(bytes_per_sec, 1)))
        chunk_sec = min(self.max_chunk_seconds, max_sec_by_size)
        target_chunk = chunk_sec * sr
        min_chunk = max(sr * 20, int(target_chunk * 0.35))  # 至少约 20 秒，避免碎块

        # 在目标切点附近找静音，尽量不切断句子
        if progress_cb:
            progress_cb("正在按静音空隙切分…")
        cut_points = [0]
        cursor = target_chunk
        while cursor < total_samples - sr:  # 末尾留 1 秒以上不必再切
            cut = self._find_silence_cut(samples, sr, cursor, total_samples)
            if cut <= cut_points[-1] + min_chunk:
                cut = min(cursor, total_samples)
            if cut >= total_samples - sr:
                break
            cut_points.append(cut)
            cursor = cut + target_chunk
        cut_points.append(total_samples)

        out_dir = self._ensure_temp()
        chunks: list[PreparedChunk] = []
        n = len(cut_points) - 1
        for i in range(n):
            if progress_cb and n > 1:
                progress_cb(f"正在写出分块 第 {i + 1}/{n} 段")
            start = cut_points[i]
            end = cut_points[i + 1]
            if end <= start:
                continue
            part = samples[start:end]
            offset_ms = int(start / sr * 1000)
            duration_ms = int((end - start) / sr * 1000)
            out_path = out_dir / f"chunk_{i:04d}.wav"
            self._write_wav(out_path, part, sr)
            chunks.append(
                PreparedChunk(path=out_path, offset_ms=offset_ms, duration_ms=duration_ms)
            )
        if not chunks:
            raise RuntimeError("音频转码后为空")
        if progress_cb:
            size_mb = sum(c.path.stat().st_size for c in chunks) / 1048576
            progress_cb(
                f"转码完成：{len(chunks)} 块（静音切点），"
                f"共约 {size_mb:.1f}MB（原时长 {total_ms / 60000:.1f} 分钟）"
            )
        return chunks

    def _find_silence_cut(
        self,
        samples: np.ndarray,
        sample_rate: int,
        target_idx: int,
        total_samples: int,
    ) -> int:
        """在目标点前后窗口内找最长/最合适的静音中点；找不到则退回目标点。"""
        window = int(self.search_window_sec * sample_rate)
        start = max(0, target_idx - window)
        end = min(total_samples, target_idx + window)
        if end <= start:
            return target_idx

        frame = max(1, int(sample_rate * 0.02))  # 20ms
        min_silence_frames = max(1, int(self.min_silence_ms / 20))
        thresh = 10 ** (self.silence_thresh_db / 20.0)

        best_cut = target_idx
        best_score = -1.0
        i = start
        while i + frame * min_silence_frames <= end:
            chunk = samples[i : i + frame * min_silence_frames]
            rms = float(np.sqrt(np.mean(chunk * chunk) + 1e-12))
            if rms < thresh:
                cut = i + len(chunk) // 2
                # 越接近目标点越好，静音越长略加分
                dist = abs(cut - target_idx) / max(1, window)
                score = (1.0 - dist) + 0.15 * (len(chunk) / sample_rate)
                if score > best_score:
                    best_score = score
                    best_cut = cut
                i += frame * min_silence_frames
            else:
                i += frame
        return best_cut

    def _load_mono(self, path: Path) -> tuple[np.ndarray, int]:
        suffix = path.suffix.lower()
        if suffix == ".wav":
            try:
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
                elif sampwidth == 3:
                    # 24-bit little endian
                    a = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
                    vals = (
                        a[:, 0].astype(np.int32)
                        | (a[:, 1].astype(np.int32) << 8)
                        | (a[:, 2].astype(np.int32) << 16)
                    )
                    vals = np.where(vals >= 0x800000, vals - 0x1000000, vals)
                    data = vals.astype(np.float32) / 8388608.0
                elif sampwidth == 4:
                    data = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
                else:
                    raise RuntimeError(f"不支持的 WAV 位深: {sampwidth}")
                if n_channels > 1:
                    data = data.reshape(-1, n_channels).mean(axis=1)
                return data, sample_rate
            except Exception:
                pass

        from pydub import AudioSegment

        from app.services.ffmpeg_util import (
            FfmpegMissingError,
            decode_error_message,
            ensure_ffmpeg_for_pydub,
        )

        try:
            ensure_ffmpeg_for_pydub()
            seg = AudioSegment.from_file(str(path))
        except FfmpegMissingError:
            raise
        except Exception as exc:
            raise RuntimeError(decode_error_message(exc, path)) from exc
        seg = seg.set_channels(1)
        sample_rate = seg.frame_rate
        samples = np.array(seg.get_array_of_samples()).astype(np.float32)
        max_val = float(1 << (8 * seg.sample_width - 1))
        samples /= max_val
        return samples, sample_rate

    @staticmethod
    def _resample(samples: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        if orig_sr == target_sr or len(samples) == 0:
            return samples
        duration = len(samples) / float(orig_sr)
        new_len = max(1, int(round(duration * target_sr)))
        x_old = np.linspace(0.0, 1.0, num=len(samples), endpoint=False)
        x_new = np.linspace(0.0, 1.0, num=new_len, endpoint=False)
        return np.interp(x_new, x_old, samples).astype(np.float32)

    @staticmethod
    def _write_wav(path: Path, samples: np.ndarray, sample_rate: int) -> None:
        pcm = np.clip(samples * 32767.0, -32768, 32767).astype(np.int16)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm.tobytes())
