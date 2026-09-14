# -*- coding: utf-8 -*-
"""曲目2：复用已有 ASR 缓存 → 切句 → 翻译 → 统校。"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import ConfigStore
from app.models import Cue
from app.services.asr_client import AsrClient
from app.services.cue_utils import split_long_cues
from app.services.llm_client import LlmClient
from app.services.pipeline import LANG_HINT


def main() -> int:
    cfg = ConfigStore(ROOT / "config.json").load_config()
    out_dir = ROOT / "tests" / "_live_full"
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = out_dir / "asr_cues.json"

    if cache.exists():
        raw_cues = json.loads(cache.read_text(encoding="utf-8"))
        cues = [
            Cue(
                id=c["id"],
                start_ms=int(c["start"]),
                end_ms=int(c["end"]),
                source_text=c["src"],
            )
            for c in raw_cues
        ]
        print("reuse ASR cache:", len(cues))
    else:
        wav = sorted(ROOT.glob("02*.wav"))[0]
        asr = AsrClient(cfg.asr, timeout=1800)
        lang = LANG_HINT.get(cfg.source_lang, "ja")
        try:
            cues = asr.recognize_file(
                wav, language=lang, progress_cb=lambda m: print("  asr:", m)
            )
        finally:
            asr.cleanup()
        cache.write_text(
            json.dumps(
                [
                    {"id": c.id, "start": c.start_ms, "end": c.end_ms, "src": c.source_text}
                    for c in cues
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print("ASR cues:", len(cues))

    cues = split_long_cues(cues)
    print("after split:", len(cues))

    llm = LlmClient(cfg.llm)
    batch_size = 5
    total = (len(cues) + batch_size - 1) // batch_size
    context: list[Cue] = []
    for bi in range(total):
        batch = cues[bi * batch_size : (bi + 1) * batch_size]
        print(f"translate {bi+1}/{total} n={len(batch)}")
        try:
            translations = llm.translate_batch(
                batch,
                source_lang=cfg.source_lang,
                target_lang=cfg.target_lang,
                prompt_snapshot="",
                context_cues=context,
            )
        except Exception as exc:
            print("FAIL:", exc)
            traceback.print_exc()
            return 3
        for cue, text in zip(batch, translations):
            cue.target_text = text
        context = batch
        print("  ok:", translations[0][:50])

    proof = cues[: min(20, len(cues))]
    revised = llm.proofread_batch(
        proof,
        source_lang=cfg.source_lang,
        target_lang=cfg.target_lang,
        prompt_snapshot="",
    )
    print("proofread:", "OK" if revised else "None/skip")

    out_dir.joinpath("translated.json").write_text(
        json.dumps(
            [
                {
                    "start": c.start_ms,
                    "end": c.end_ms,
                    "src": c.source_text,
                    "tgt": c.target_text,
                }
                for c in cues
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("ALL PASSED cues=", len(cues))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
