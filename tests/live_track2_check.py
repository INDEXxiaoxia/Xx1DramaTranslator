# -*- coding: utf-8 -*-
"""先只测 LLM 解析（用日语样句），再测曲目2前30秒 ASR+翻译。"""
from __future__ import annotations

import json
import sys
import traceback
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import ConfigStore
from app.models import Cue, new_cue_id
from app.services.asr_client import AsrClient
from app.services.llm_client import LlmClient, LlmError


def slice_wav(src: Path, out: Path, seconds: float = 30.0) -> None:
    with wave.open(str(src), "rb") as wf:
        nch = wf.getnchannels()
        sw = wf.getsampwidth()
        sr = wf.getframerate()
        n = int(sr * seconds)
        frames = wf.readframes(n)
    with wave.open(str(out), "wb") as out_wf:
        out_wf.setnchannels(nch)
        out_wf.setsampwidth(sw)
        out_wf.setframerate(sr)
        out_wf.writeframes(frames)


def test_llm_parse(llm: LlmClient, source_lang: str, target_lang: str) -> None:
    cues = [
        Cue(id=new_cue_id(), start_ms=0, end_ms=1000, source_text="こんにちは。"),
        Cue(id=new_cue_id(), start_ms=1000, end_ms=2500, source_text="今日はいい天気ですね。"),
        Cue(id=new_cue_id(), start_ms=2500, end_ms=4000, source_text="これからどうするつもり？"),
    ]
    system = (
        f"你是专业的{source_lang}到{target_lang}字幕翻译器。"
        "必须逐条翻译，保持输入条目数量与顺序完全一致。"
        "只输出 JSON 数组，每个元素是对应条目的译文字符串，不要输出其它说明。"
    )
    user = {
        "additional_prompt": "",
        "context": [],
        "items": [{"id": c.id, "text": c.source_text} for c in cues],
    }
    raw = llm.chat(system, json.dumps(user, ensure_ascii=False))
    print("RAW1 >>>")
    print(repr(raw[:800]))
    print("<<<")
    (ROOT / "tests" / "_last_llm_raw.txt").write_text(raw, encoding="utf-8")
    parsed = llm._parse_string_list(raw, expected=len(cues))
    print("parse1 OK:", parsed)

    # 正式 API
    out = llm.translate_batch(
        cues,
        source_lang=source_lang,
        target_lang=target_lang,
        prompt_snapshot="",
        context_cues=[],
    )
    print("translate_batch OK:", out)


def main() -> int:
    cfg = ConfigStore(ROOT / "config.json").load_config()
    llm = LlmClient(cfg.llm)
    print("=== A: LLM sample parse ===")
    try:
        test_llm_parse(llm, cfg.source_lang, cfg.target_lang)
    except Exception as exc:
        print("LLM FAIL:", exc)
        traceback.print_exc()
        # 继续跑 ASR，但最终失败

    wavs = sorted(ROOT.glob("02*.wav"))
    if not wavs:
        print("FAIL: no 02 wav")
        return 1
    wav = wavs[0]
    print("=== B: ASR+translate first 30s of", wav.name, "===")
    tmp = ROOT / "tests" / "_track2_30s.wav"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    slice_wav(wav, tmp, 30.0)
    print("sliced:", tmp, "bytes=", tmp.stat().st_size)

    asr = AsrClient(cfg.asr, timeout=600)
    try:
        cues = asr.recognize_file(
            tmp,
            language="ja",
            progress_cb=lambda m: print("  asr:", m),
        )
    finally:
        asr.cleanup()

    print("ASR cues:", len(cues))
    for c in cues[:8]:
        print(f"  [{c.start_ms}-{c.end_ms}] {c.source_text}")
    if not cues:
        print("FAIL: empty ASR")
        return 2

    sample = cues[: min(8, len(cues))]
    try:
        tr = llm.translate_batch(
            sample,
            source_lang=cfg.source_lang,
            target_lang=cfg.target_lang,
            prompt_snapshot="",
            context_cues=[],
        )
        print("ASR translate OK:")
        for a, b in zip(sample, tr):
            print(" ", a.source_text, "=>", b)
    except Exception as exc:
        print("ASR translate FAIL:", exc)
        traceback.print_exc()
        return 3

    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
