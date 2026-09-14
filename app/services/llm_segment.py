from __future__ import annotations

"""ASR 结果 → 字符时间轴 → 大模型语义断句 → 回填时间戳。

断句/合并的最终裁决交给大模型；本地只做：
1) ASR 明显截断碎片的预拼接（助词续接等）
2) 模型失败时的规则兜底
不做「因为短就合并」的机械合并。
"""

import re
from typing import Callable

from app.models import Cue, new_cue_id
from app.services.cue_utils import merge_fragmented_cues, split_long_cues
from app.services.llm_client import LlmClient


CancelCheck = Callable[[], bool]
ProgressCb = Callable[[str], None]

# 仅作过长句上限提示，不是目标字数，也不是合并阈值
DEFAULT_SOFT_MAX = 42


def build_char_timeline(cues: list[Cue]) -> tuple[str, list[tuple[int, int]]]:
    """拼接原文，并为每个字符分配 (start_ms, end_ms)（在原 cue 内线性插值）。"""
    text_parts: list[str] = []
    times: list[tuple[int, int]] = []
    for cue in cues:
        t = (cue.source_text or "").strip()
        if not t:
            continue
        n = len(t)
        span = max(0, cue.end_ms - cue.start_ms)
        for i, ch in enumerate(t):
            if n == 1:
                s, e = cue.start_ms, cue.end_ms
            else:
                s = cue.start_ms + int(span * i / n)
                e = cue.start_ms + int(span * (i + 1) / n)
                e = max(e, s + 1)
            text_parts.append(ch)
            times.append((s, e))
    return "".join(text_parts), times


def lines_to_cues(
    lines: list[str],
    full_text: str,
    char_times: list[tuple[int, int]],
) -> list[Cue] | None:
    """按顺序把断句结果映射回字符时间轴；映射失败返回 None。"""
    if not lines or not full_text or len(full_text) != len(char_times):
        return None
    cursor = 0
    out: list[Cue] = []
    for raw in lines:
        line = (raw or "").strip()
        if not line:
            continue
        compact_line = re.sub(r"\s+", "", line)
        idx = full_text.find(compact_line, cursor)
        if idx < 0:
            return None
        end = idx + len(compact_line)
        if end <= idx or end > len(char_times):
            return None
        start_ms = char_times[idx][0]
        end_ms = char_times[end - 1][1]
        if end_ms <= start_ms:
            end_ms = start_ms + max(300, 40 * len(compact_line))
        out.append(
            Cue(
                id=new_cue_id(),
                start_ms=start_ms,
                end_ms=end_ms,
                source_text=compact_line,
            )
        )
        cursor = end
    if cursor != len(full_text):
        if out and len(full_text) - cursor <= 6:
            tail = full_text[cursor:]
            out[-1].source_text += tail
            out[-1].end_ms = char_times[-1][1]
            return out
        return None
    return out


def segment_cues_with_llm(
    llm: LlmClient,
    cues: list[Cue],
    *,
    source_lang: str = "日语",
    soft_max_chars: int = DEFAULT_SOFT_MAX,
    cancel_check: CancelCheck | None = None,
    progress_cb: ProgressCb | None = None,
) -> list[Cue]:
    """
    用大模型按完整句子/语气停顿断句；成功后原样采用模型分行。
    soft_max_chars 只写入提示作过长上限参考，本地不按字数强制合并。
    """
    # 预拼：只修 ASR 明显截断（助词续行等），再交给模型审定切分
    merged = merge_fragmented_cues(cues)
    full_text, char_times = build_char_timeline(merged)
    if not full_text:
        return merged

    if len(full_text) <= 12:
        return [
            Cue(
                id=new_cue_id(),
                start_ms=char_times[0][0],
                end_ms=char_times[-1][1],
                source_text=full_text,
            )
        ]

    chunk_chars = 520
    chunks: list[tuple[int, int]] = []
    i = 0
    n = len(full_text)
    while i < n:
        j = min(n, i + chunk_chars)
        if j < n:
            window = full_text[i:j]
            cut = max(
                window.rfind("。"),
                window.rfind("！"),
                window.rfind("？"),
                window.rfind("、"),
            )
            if cut >= chunk_chars // 4:
                j = i + cut + 1
        chunks.append((i, j))
        i = j

    all_lines: list[str] = []
    used_fallback = False
    for ci, (a, b) in enumerate(chunks):
        if cancel_check and cancel_check():
            raise InterruptedError("cancelled")
        piece = full_text[a:b]
        if progress_cb:
            progress_cb(f"正在断句 第 {ci + 1}/{len(chunks)} 段")
        try:
            lines = llm.segment_subtitle_text(
                piece,
                source_lang=source_lang,
                soft_max_chars=soft_max_chars,
                cancel_check=cancel_check,
            )
        except InterruptedError:
            raise
        except Exception:
            used_fallback = True
            fallback = split_long_cues(
                [
                    Cue(
                        id=new_cue_id(),
                        start_ms=char_times[a][0],
                        end_ms=char_times[b - 1][1],
                        source_text=piece,
                    )
                ],
                max_chars=soft_max_chars,
            )
            all_lines.extend(c.source_text for c in fallback)
            continue

        joined = re.sub(r"\s+", "", "".join(lines))
        expect = re.sub(r"\s+", "", piece)
        if joined != expect:
            used_fallback = True
            fallback = split_long_cues(
                [
                    Cue(
                        id=new_cue_id(),
                        start_ms=char_times[a][0],
                        end_ms=char_times[b - 1][1],
                        source_text=piece,
                    )
                ],
                max_chars=soft_max_chars,
            )
            all_lines.extend(c.source_text for c in fallback)
        else:
            # 模型结果原样采用，不做短句机械合并
            all_lines.extend(lines)

    if re.sub(r"\s+", "", "".join(all_lines)) != full_text:
        if progress_cb:
            progress_cb("断句结果与原文不一致，改用本地规则…")
        return split_long_cues(merged, max_chars=soft_max_chars)

    mapped = lines_to_cues(all_lines, full_text, char_times)
    if mapped:
        if used_fallback and progress_cb:
            progress_cb("部分片段模型断句失败，已用本地规则补齐")
        return mapped

    if progress_cb:
        progress_cb("断句映射失败，改用本地规则切分…")
    return split_long_cues(merged, max_chars=soft_max_chars)
