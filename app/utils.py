from __future__ import annotations

import re
from pathlib import Path

from mutagen import File as MutagenFile


AUDIO_EXTENSIONS = {".mp3", ".wav"}


def is_audio_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in AUDIO_EXTENSIONS


def probe_duration_ms(path: str | Path) -> int:
    path = Path(path)
    try:
        audio = MutagenFile(path)
        if audio is not None and getattr(audio, "info", None) is not None:
            length = getattr(audio.info, "length", None)
            if length is not None:
                return max(0, int(float(length) * 1000))
    except Exception:
        pass

    if path.suffix.lower() == ".wav":
        try:
            import wave

            with wave.open(str(path), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate() or 1
                return int(frames / rate * 1000)
        except Exception:
            return 0
    return 0


def format_time(ms: int) -> str:
    ms = max(0, int(ms))
    total_sec = ms // 1000
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


def format_cue_time(ms: int) -> str:
    """字幕时间编辑用：带毫秒，如 1:23.456 / 1:02:03.456。"""
    ms = max(0, int(ms))
    h = ms // 3600000
    rem = ms % 3600000
    m = rem // 60000
    rem %= 60000
    s = rem // 1000
    milli = rem % 1000
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}.{milli:03d}"
    return f"{m:d}:{s:02d}.{milli:03d}"


def parse_cue_time(text: str) -> int | None:
    """解析字幕时间；支持 1:23 / 1:23.456 / 1:02:03,456 等。失败返回 None。"""
    s = (text or "").strip()
    if not s:
        return None
    s = s.replace(",", ".")
    # h:mm:ss(.mmm)
    m = re.fullmatch(r"(\d+):(\d{1,2}):(\d{1,2})(?:\.(\d{1,3}))?", s)
    if m:
        h = int(m.group(1))
        mm = int(m.group(2))
        ss = int(m.group(3))
        frac = (m.group(4) or "0").ljust(3, "0")[:3]
        if mm >= 60 or ss >= 60:
            return None
        return ((h * 60 + mm) * 60 + ss) * 1000 + int(frac)
    # m:ss(.mmm) — 分钟可超过 59
    m = re.fullmatch(r"(\d+):(\d{1,2})(?:\.(\d{1,3}))?", s)
    if m:
        mm = int(m.group(1))
        ss = int(m.group(2))
        frac = (m.group(3) or "0").ljust(3, "0")[:3]
        if ss >= 60:
            return None
        return (mm * 60 + ss) * 1000 + int(frac)
    # 纯秒
    m2 = re.fullmatch(r"(\d+)(?:\.(\d{1,3}))?", s)
    if not m2:
        return None
    sec = int(m2.group(1))
    frac = (m2.group(2) or "0").ljust(3, "0")[:3]
    return sec * 1000 + int(frac)


def ms_to_srt_timestamp(ms: int) -> str:
    ms = max(0, int(ms))
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    milli = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def ms_to_ass_timestamp(ms: int) -> str:
    ms = max(0, int(ms))
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    cs = (ms % 1000) // 10
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"
