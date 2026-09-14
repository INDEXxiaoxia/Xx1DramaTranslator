# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models import Cue, new_cue_id
from app.services.cue_utils import merge_over_short_lines
from app.services.llm_segment import build_char_timeline, lines_to_cues


class SegmentMapTests(unittest.TestCase):
    def test_timeline_and_map(self) -> None:
        cues = [
            Cue(id=new_cue_id(), start_ms=0, end_ms=1000, source_text="あいう"),
            Cue(id=new_cue_id(), start_ms=1000, end_ms=2000, source_text="えお"),
        ]
        text, times = build_char_timeline(cues)
        self.assertEqual(text, "あいうえお")
        out = lines_to_cues(["あい", "うえお"], text, times)
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual("".join(c.source_text for c in out), text)

    def test_reject_mismatch(self) -> None:
        cues = [Cue(id=new_cue_id(), start_ms=0, end_ms=1000, source_text="あいう")]
        text, times = build_char_timeline(cues)
        self.assertIsNone(lines_to_cues(["あい", "え"], text, times))

    def test_no_mechanical_merge_of_short_sentences(self) -> None:
        """两句虽短但是独立的话，禁止因字数短而合并。"""
        lines = ["短い一句。", "別の短い一句。", "また別の話。"]
        merged = merge_over_short_lines(lines, soft_max=42)
        self.assertEqual(merged, ["短い一句。", "別の短い一句。", "また別の話。"])

    def test_merge_only_particle_continuation(self) -> None:
        lines = ["お母さんの", "は笑顔で見つめる"]
        # 「は」开头才允许并回
        merged = merge_over_short_lines(lines, soft_max=42)
        self.assertEqual(merged, ["お母さんのは笑顔で見つめる"])


if __name__ == "__main__":
    unittest.main()
