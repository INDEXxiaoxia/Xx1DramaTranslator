from __future__ import annotations

from pathlib import Path

from app.models import Cue
from app.utils import ms_to_ass_timestamp, ms_to_srt_timestamp


def export_subtitles(
    cues: list[Cue],
    audio_path: str | Path,
    *,
    fmt: str,
    include_source: bool,
    include_target: bool,
) -> Path:
    if not include_source and not include_target:
        raise ValueError("至少勾选原文或译文之一")
    audio_path = Path(audio_path)
    stem = audio_path.stem
    if include_source and include_target:
        suffix_name = "双语"
    elif include_source:
        suffix_name = "原文"
    else:
        suffix_name = "译文"
    ext = fmt.lower()
    out_path = audio_path.with_name(f"{stem}_{suffix_name}.{ext}")
    if ext == "srt":
        content = _to_srt(cues, include_source, include_target)
    elif ext == "ass":
        content = _to_ass(cues, include_source, include_target)
    else:
        raise ValueError(f"不支持的格式: {fmt}")
    out_path.write_text(content, encoding="utf-8-sig")
    return out_path


def _to_srt(cues: list[Cue], include_source: bool, include_target: bool) -> str:
    blocks: list[str] = []
    for i, cue in enumerate(cues, start=1):
        lines: list[str] = []
        if include_source:
            lines.append(cue.source_text)
        if include_target:
            lines.append(cue.target_text)
        body = "\n".join(lines)
        blocks.append(
            f"{i}\n{ms_to_srt_timestamp(cue.start_ms)} --> {ms_to_srt_timestamp(cue.end_ms)}\n{body}\n"
        )
    return "\n".join(blocks)


def _to_ass(cues: list[Cue], include_source: bool, include_target: bool) -> str:
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Source,Microsoft YaHei,56,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,2,0,8,40,40,60,1
Style: Target,Microsoft YaHei,64,&H0000FFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,2,0,2,40,40,40,1
Style: Default,Microsoft YaHei,60,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,2,0,2,40,40,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for cue in cues:
        start = ms_to_ass_timestamp(cue.start_ms)
        end = ms_to_ass_timestamp(cue.end_ms)
        if include_source and include_target:
            lines.append(
                f"Dialogue: 0,{start},{end},Source,,0,0,0,,{_ass_escape(cue.source_text)}"
            )
            lines.append(
                f"Dialogue: 0,{start},{end},Target,,0,0,0,,{_ass_escape(cue.target_text)}"
            )
        elif include_source:
            lines.append(
                f"Dialogue: 0,{start},{end},Source,,0,0,0,,{_ass_escape(cue.source_text)}"
            )
        else:
            lines.append(
                f"Dialogue: 0,{start},{end},Target,,0,0,0,,{_ass_escape(cue.target_text)}"
            )
    return "\n".join(lines) + "\n"


def _ass_escape(text: str) -> str:
    return text.replace("\n", "\\N")
