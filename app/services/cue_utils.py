from __future__ import annotations

"""把过长/截断错误的 ASR 句重切成适合字幕的短句。"""

import re

from app.models import Cue, new_cue_id


# 下一句若以这些助词开头，多半是上一句被截断
_CONT_START = frozenset("はがをにへとでもでのやへ")
_STRONG_END = frozenset("。！？!?")
_SOFT_PUNCT = frozenset("、，,；;")

# 优先在这些短语之后断开（长匹配优先）
_BREAK_AFTER = (
    "けれども",
    "けれど",
    "ました",
    "でした",
    "です",
    "ます",
    "だった",
    "ましたよ",
    "ましたね",
    "ですよ",
    "ですね",
    "んだよ",
    "んだね",
    "のよ",
    "よね",
    "けど",
    "のに",
    "ので",
    "から",
    "たり",
    "ながら",
    "と言いました",
    "と聞きました",
    "と驚きました",
    "と答えます",
    "と答えました",
    "言いました",
    "聞きました",
    "歩きました",
    "歩いています",
    "歩き出しました",
    "やってきました",
    "会いました",
    "出会いました",
)

# 在这些连接词之前断开（新分句开始）
_BREAK_BEFORE = (
    "そして",
    "すると",
    "それで",
    "それから",
    "だけど",
    "でも",
    "しかし",
    "ところが",
    "今度は",
    "その中に",
    "その度に",
    "なぜか",
    "だから",
    "あれ、",
    "あれ?",
    "え、",
    "ねえ、",
)


def split_long_cues(
    cues: list[Cue],
    *,
    max_chars: int = 42,
    max_duration_ms: int = 12000,
) -> list[Cue]:
    """合并碎片 → 按语义边界重切；时间戳按字符占比分配。
    max_chars 是过长上限，不是目标长度。
    """
    if not cues:
        return []
    merged = merge_fragmented_cues(cues)
    out: list[Cue] = []
    for cue in merged:
        text = cue.source_text.strip()
        if not text:
            continue
        duration = max(0, cue.end_ms - cue.start_ms)
        # 本身不太长：整句保留
        if len(text) <= max_chars and duration <= max_duration_ms:
            out.append(cue)
            continue
        parts = split_japanese_text(text, max_chars=max_chars)
        if len(parts) <= 1:
            out.append(cue)
            continue
        out.extend(_parts_to_cues(parts, cue.start_ms, cue.end_ms))
    return out


def merge_over_short_lines(
    lines: list[str],
    *,
    min_chars: int = 8,
    soft_max: int = 42,
) -> list[str]:
    """仅修复「明显被截断」的行，禁止因字数短就合并两句独立短句。

    只在下列情况并入上一行：
    - 本行以助词开头（は/が/を…），像上一句被切开；
    - 上一行以顿号/逗号结尾，语义未完。
    不会因为「两行都很短」就合并。
    """
    del min_chars  # 保留参数兼容旧调用，但不再按字数阈值合并
    if not lines:
        return []
    out: list[str] = []
    for line in lines:
        s = re.sub(r"\s+", "", line or "")
        if not s:
            continue
        if not out:
            out.append(s)
            continue
        prev = out[-1]
        cont_particle = s[0] in _CONT_START
        prev_open = prev[-1] in _SOFT_PUNCT
        if (cont_particle or prev_open) and len(prev) + len(s) <= soft_max + 12:
            out[-1] = prev + s
            continue
        out.append(s)
    return out


def merge_fragmented_cues(cues: list[Cue], *, max_gap_ms: int = 1200) -> list[Cue]:
    """把被错误截断的相邻条目拼回（如「猫。」+「がいました。」）。"""
    if not cues:
        return []
    ordered = sorted(cues, key=lambda c: c.start_ms)
    merged: list[Cue] = []
    buf = Cue(
        id=ordered[0].id,
        start_ms=ordered[0].start_ms,
        end_ms=ordered[0].end_ms,
        source_text=ordered[0].source_text.strip(),
        target_text=ordered[0].target_text,
    )
    for nxt in ordered[1:]:
        a = buf.source_text.strip()
        b = (nxt.source_text or "").strip()
        gap = max(0, nxt.start_ms - buf.end_ms)
        if _should_merge(a, b, gap, max_gap_ms=max_gap_ms):
            # 被句号误切的半词：去掉中间句号再拼接（一。人 → 一人）
            if b[0] in _CONT_START or _looks_cut_mid_word(a, b):
                a = a.rstrip("。！？!?")
            buf.source_text = a + b
            buf.end_ms = max(buf.end_ms, nxt.end_ms)
        else:
            if buf.source_text.strip():
                merged.append(buf)
            buf = Cue(
                id=nxt.id,
                start_ms=nxt.start_ms,
                end_ms=nxt.end_ms,
                source_text=b,
                target_text=nxt.target_text,
            )
    if buf.source_text.strip():
        merged.append(buf)
    return merged


def _should_merge(a: str, b: str, gap: int, *, max_gap_ms: int) -> bool:
    """ASR 预拼接：只拼明显截断，不把两句完整短句因间隔近就并掉。

    交给大模型前需要连续文本时，无句号的相邻块仍拼接（由模型再切）；
    若两边都以句末标点结束，则保持分开。
    """
    if not a or not b:
        return True
    if gap > max_gap_ms:
        return b[0] in _CONT_START
    if b[0] in _CONT_START:
        return True
    if len(a) >= 2 and a[-1] in _STRONG_END and _looks_cut_mid_word(a, b):
        return True
    # 上一句已有句末标点，且下一句不是助词续接 → 视为不同句，不预合并
    if a[-1] in _STRONG_END:
        return False
    # 无句末标点：拼成连续文本，供模型统一审定切分
    return True


def _looks_cut_mid_word(a: str, b: str) -> bool:
    """上一句以单字+句号结尾，下一句以汉字/假名续上，像被拦腰截断。"""
    core = a.rstrip("。！？!?")
    if not core:
        return False
    # 上一句末尾是单独假名/汉字，下一句不是新句子大写式开头连接词
    last = core[-1]
    if last in "、，,":
        return True
    # 「悲しくなり、一。」+「人涙」
    if last in "一人一二三四五六七八九十" and b and b[0] not in _STRONG_END:
        if b[0] not in _CONT_START and not any(b.startswith(x) for x in _BREAK_BEFORE):
            # 若下一句以常见续接汉字开头
            return True
    return False


def split_japanese_text(text: str, *, max_chars: int = 42) -> list[str]:
    """按日语语义边界切分；max_chars 仅为过长上限。"""
    text = re.sub(r"\s+", "", text or "")
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    breaks = _collect_break_points(text)
    parts: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        remain = n - start
        if remain <= max_chars:
            parts.append(text[start:])
            break
        # 尽量切到接近上限，优先高分断点（句号等），避免碎切
        window_end = start + max_chars
        min_keep = max(12, max_chars // 2)
        best = -1
        best_score = -10**9
        for pos, score in breaks:
            if pos <= start + min_keep:
                continue
            if pos > window_end:
                break
            left = text[start:pos]
            right = text[pos:]
            if _is_bad_line_end(left) or _is_mid_word_cut(left, right):
                continue
            dist = window_end - pos
            adj = score * 20 - dist
            if pos < n and text[pos] in _CONT_START:
                adj -= 100
            if adj > best_score:
                best_score = adj
                best = pos
        if best < 0:
            best = _fallback_cut(text, start, window_end, max_chars=max_chars)
        best = _extend_past_bad_end(text, start, best, max_chars=max_chars)
        chunk = text[start:best].strip()
        if chunk:
            parts.append(chunk)
        start = best
    return merge_over_short_lines(parts, min_chars=8, soft_max=max_chars)


_BAD_LINE_END = (
    "ただ",
    "であ",
    "その",
    "この",
    "あの",
    "そして",
    "それで",
    "すると",
    "だけど",
)


def _polish_parts(parts: list[str], *, max_chars: int) -> list[str]:
    """合并行首助词、行末半截连接，避免语义截断。"""
    if not parts:
        return parts
    out: list[str] = [parts[0]]
    for nxt in parts[1:]:
        prev = out[-1]
        if nxt and nxt[0] in _CONT_START:
            out[-1] = prev + nxt
            continue
        if _is_bad_line_end(prev):
            out[-1] = prev + nxt
            continue
        out.append(nxt)

    # 过长再切；切完继续修边界
    soft_max = int(max_chars * 1.45)
    final: list[str] = []
    for p in out:
        if len(p) <= soft_max:
            final.append(p)
        else:
            final.extend(_split_raw(p, max_chars=max_chars))

    # 第二遍：行末半截 / 跨行半词 继续与下一行合并
    i = 0
    while i < len(final) - 1:
        left, right = final[i], final[i + 1]
        if (
            _is_bad_line_end(left)
            or (right and right[0] in _CONT_START)
            or _is_mid_word_cut(left, right)
        ):
            merged = left + right
            del final[i + 1]
            if len(merged) > soft_max:
                pieces = _split_raw(merged, max_chars=max_chars)
                final[i : i + 1] = pieces
                i += len(pieces)
            else:
                final[i] = merged
            continue
        i += 1
    return final


def _is_bad_line_end(text: str) -> bool:
    if not text:
        return False
    if text[-1] in "はがをにへとでもでのや":
        return True
    if any(text.endswith(x) for x in _BAD_LINE_END):
        return True
    # 「ただ一|人」「今|度は」
    if text.endswith(("一", "今", "ただ一")):
        return True
    return False


def _is_mid_word_cut(left: str, right: str) -> bool:
    if not left or not right:
        return False
    pairs = (
        ("一", "人"),
        ("ただ", "一"),
        ("ただ一", "人"),
        ("今", "度"),
        ("世", "界"),
        ("お母", "さん"),
        ("レインボ", "ー"),
        ("口", "下"),
        ("靴", "下"),
    )
    for a, b in pairs:
        if left.endswith(a) and right.startswith(b):
            return True
    return False


def _split_raw(text: str, *, max_chars: int) -> list[str]:
    breaks = _collect_break_points(text)
    parts: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        if n - start <= max_chars:
            parts.append(text[start:])
            break
        window_end = start + max_chars
        min_keep = max(8, max_chars // 3)
        best = -1
        best_score = -10**9
        for pos, score in breaks:
            if pos <= start + min_keep or pos > window_end:
                if pos > window_end:
                    break
                continue
            left = text[start:pos]
            right = text[pos:]
            if _is_bad_line_end(left) or _is_mid_word_cut(left, right):
                continue
            adj = score * 20 - (window_end - pos)
            if pos < n and text[pos] in _CONT_START:
                adj -= 100
            if adj > best_score:
                best_score = adj
                best = pos
        if best < 0:
            best = _fallback_cut(text, start, window_end, max_chars=max_chars)
        best = _extend_past_bad_end(text, start, best, max_chars=max_chars)
        parts.append(text[start:best])
        start = best
    return [p for p in parts if p]


def _extend_past_bad_end(text: str, start: int, best: int, *, max_chars: int) -> int:
    """若当前切点落在半截词后，向后延长到安全位置。"""
    n = len(text)
    hard = min(n, start + int(max_chars * 1.6))
    while best < hard and best <= n:
        left = text[start:best]
        right = text[best:] if best < n else ""
        if not _is_bad_line_end(left) and not _is_mid_word_cut(left, right):
            if best < n and text[best] in _CONT_START:
                best += 1
                continue
            break
        if best >= n:
            break
        best += 1
    return best


def _collect_break_points(text: str) -> list[tuple[int, int]]:
    """返回 (断点下标=下一句起点, 分数)。分数越高越优先。"""
    scored: dict[int, int] = {}

    def add(pos: int, score: int) -> None:
        if 0 < pos < len(text):
            scored[pos] = max(scored.get(pos, -10**9), score)

    for i, ch in enumerate(text):
        if ch in _STRONG_END:
            add(i + 1, 100)
        elif ch in _SOFT_PUNCT:
            add(i + 1, 70)

    for phrase in sorted(_BREAK_AFTER, key=len, reverse=True):
        start = 0
        while True:
            idx = text.find(phrase, start)
            if idx < 0:
                break
            add(idx + len(phrase), 55 + min(10, len(phrase)))
            start = idx + 1

    for phrase in sorted(_BREAK_BEFORE, key=len, reverse=True):
        start = 0
        while True:
            idx = text.find(phrase, start)
            if idx < 0:
                break
            if idx > 0:
                add(idx, 50 + min(8, len(phrase)))
            start = idx + 1

    # です/ます/た/だ/る 后若紧跟新主语/指示词或汉字分句，可断
    for m in re.finditer(r"(?:です|ます|でした|ました|た|だ)(?=[私君僕彼彼女そこあこ此皆])", text):
        add(m.end(), 45)

    for m in re.finditer(r"(?:です|ます|た|だ|る|す|む|く|ぐ)(?=[\u4e00-\u9fff])", text):
        add(m.end(), 48)

    # 「…ない」「…んない」后开启新分句
    for m in re.finditer(r"(?:んない|ない)(?=[\u4e00-\u9fffあ-ん])", text):
        add(m.end(), 52)

    # 「けど/から」已在 BREAK_AFTER；补「て」连接后的汉字分句（電気を消えた|真っ暗）
    for m in re.finditer(r"て(?=[\u4e00-\u9fff])", text):
        add(m.end(), 35)

    return sorted(scored.items(), key=lambda x: x[0])


def _fallback_cut(text: str, start: int, window_end: int, *, max_chars: int) -> int:
    """无标点时：避免在助词前切断，尽量在用言/名词边界切。"""
    n = len(text)
    # 先尝试在 window_end 附近往前找，不让下一句以助词开头
    for pos in range(min(window_end, n), start + max(6, max_chars // 4), -1):
        if pos >= n:
            continue
        if text[pos] in _CONT_START:
            continue
        # 不要切开「お母さん」等：若 pos 落在词中间很难判断，至少避开助词前
        prev = text[pos - 1]
        # 优先在假名→汉字、汉字→汉字短语边界：…部屋|暗がり
        if prev in _SOFT_PUNCT or prev in _STRONG_END:
            return pos
        if _is_hiragana(prev) and _is_kanji(text[pos]):
            return pos
        if _is_kanji(prev) and _is_hiragana(text[pos]) and text[pos] not in _CONT_START:
            # …部屋暗|がり 较差；…消えた|真っ暗 较好（た+汉字已在 breaks）
            if prev in "えたうくすつぬむゆる":
                return pos
    # 再允许略微超出 max_chars，找到不以助词开头的位置
    hard_limit = min(n, start + int(max_chars * 1.35))
    for pos in range(window_end, hard_limit + 1):
        if pos < n and text[pos] not in _CONT_START:
            return pos
    # 最后：硬切但保证下一句不以助词开头
    pos = min(window_end, n)
    while pos < n and text[pos] in _CONT_START:
        pos += 1
    if pos <= start:
        pos = min(start + max_chars, n)
    return pos


def _is_hiragana(ch: str) -> bool:
    return "あ" <= ch <= "ん" or ch in "ーっャュョぁぃぅぇぉ"


def _is_kanji(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


def _parts_to_cues(parts: list[str], start_ms: int, end_ms: int) -> list[Cue]:
    total_chars = sum(max(1, len(p)) for p in parts)
    span = max(0, end_ms - start_ms)
    cursor = start_ms
    out: list[Cue] = []
    for i, part in enumerate(parts):
        if i == len(parts) - 1:
            end = end_ms
        else:
            share = max(1, len(part)) / total_chars
            end = cursor + max(400, int(span * share))
            end = min(end, end_ms)
        if end <= cursor:
            end = min(end_ms, cursor + 400)
        out.append(
            Cue(
                id=new_cue_id(),
                start_ms=cursor,
                end_ms=end,
                source_text=part,
                target_text="",
            )
        )
        cursor = end
    return out
