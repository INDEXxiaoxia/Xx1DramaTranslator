"""定位本机 ffmpeg，并给 pydub 配置转换器。

官方 Windows essentials / full 静态包体积通常数十 MB 到上百 MB，
不适合打进仓库与单文件 exe；因此采用「就近查找 + 明确中文提示」。
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


class FfmpegMissingError(RuntimeError):
    """本机找不到可用的 ffmpeg。"""


def _candidate_dirs() -> list[Path]:
    dirs: list[Path] = []
    # 1) 环境变量指定的文件或目录
    env = (os.environ.get("XX1_FFMPEG") or os.environ.get("FFMPEG_BINARY") or "").strip()
    if env:
        p = Path(env)
        dirs.append(p if p.is_dir() else p.parent)

    # 2) 打包后的临时目录 / exe 同目录
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            dirs.append(Path(meipass))
            dirs.append(Path(meipass) / "ffmpeg")
            dirs.append(Path(meipass) / "vendor" / "ffmpeg")
        exe_dir = Path(sys.executable).resolve().parent
        dirs.append(exe_dir)
        dirs.append(exe_dir / "ffmpeg")
        dirs.append(exe_dir / "vendor" / "ffmpeg")

    # 3) 源码运行：项目根 / vendor/ffmpeg
    root = Path(__file__).resolve().parents[2]
    dirs.append(root)
    dirs.append(root / "vendor" / "ffmpeg")
    dirs.append(root / "ffmpeg")
    return dirs


def find_ffmpeg() -> Path | None:
    """按优先级查找 ffmpeg.exe；找不到返回 None。"""
    for d in _candidate_dirs():
        for name in ("ffmpeg.exe", "ffmpeg"):
            cand = d / name
            if cand.is_file():
                return cand.resolve()

    which = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if which:
        return Path(which).resolve()
    return None


def missing_message() -> str:
    return (
        "处理 MP3 等非 WAV 格式需要本机安装 ffmpeg，当前未找到可用的 ffmpeg。\n\n"
        "可选解决办法（任选其一）：\n"
        "1. 安装后保证命令行能运行 ffmpeg：\n"
        "   winget install --id=Gyan.FFmpeg -e\n"
        "   或到 https://www.gyan.dev/ffmpeg/builds/ 下载 essentials，把 bin 加入 PATH\n"
        "2. 将 ffmpeg.exe 放到本程序 exe / 项目目录旁，或 vendor\\ffmpeg\\ 目录下\n"
        "3. 设置环境变量 XX1_FFMPEG 指向 ffmpeg.exe 的完整路径\n\n"
        "说明：WAV 可直接识别，不依赖 ffmpeg；"
        "官方 ffmpeg 体积较大（数十～上百 MB），故未内置进本程序。"
    )


def ensure_ffmpeg_for_pydub() -> Path:
    """配置 pydub 使用的 ffmpeg；缺失时抛出明确的中文错误。"""
    path = find_ffmpeg()
    if path is None:
        raise FfmpegMissingError(missing_message())

    try:
        from pydub import AudioSegment
    except ImportError as exc:
        raise RuntimeError("缺少 pydub，无法读取该音频格式。请先 pip install pydub。") from exc

    converter = str(path)
    AudioSegment.converter = converter
    # 部分 pydub 版本还会读这些属性
    for attr in ("ffmpeg", "ffprobe"):
        if hasattr(AudioSegment, attr):
            setattr(AudioSegment, attr, converter)

    # ffprobe 若同目录存在则一并指定，利于元数据探测
    probe = path.with_name("ffprobe.exe" if path.suffix.lower() == ".exe" else "ffprobe")
    if probe.is_file() and hasattr(AudioSegment, "ffprobe"):
        AudioSegment.ffprobe = str(probe)

    return path


def decode_error_message(exc: BaseException, audio_path: Path | str) -> str:
    """把 pydub/ffmpeg 底层异常转成可读中文。"""
    text = str(exc) or exc.__class__.__name__
    low = text.lower()
    if isinstance(exc, FileNotFoundError) or "winerror 2" in low or "系统找不到指定的文件" in text:
        return missing_message()
    if "ffmpeg" in low and ("not found" in low or "找不到" in text):
        return missing_message()
    return (
        f"无法解码音频文件：{audio_path}\n"
        f"原因：{text}\n\n"
        "若这是 MP3，请确认已安装 ffmpeg，且文件未损坏；"
        "也可先转换为 WAV 再试。"
    )
