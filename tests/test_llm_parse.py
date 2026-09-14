# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import LlmConfig
from app.models import Cue, new_cue_id
from app.services.cue_utils import split_long_cues
from app.services.llm_client import LlmClient, LlmError


class ParseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.llm = LlmClient(LlmConfig())

    def test_plain_array(self) -> None:
        out = self.llm._parse_string_list('["a", "b"]', expected=2)
        self.assertEqual(out, ["a", "b"])

    def test_markdown_fence(self) -> None:
        raw = '```json\n["一", "二", "三"]\n```'
        out = self.llm._parse_string_list(raw, expected=3)
        self.assertEqual(out, ["一", "二", "三"])

    def test_trailing_comma(self) -> None:
        out = self.llm._parse_string_list('["a", "b",]', expected=2)
        self.assertEqual(out, ["a", "b"])

    def test_object_items(self) -> None:
        raw = '[{"target":"你好"},{"text":"天气好"}]'
        out = self.llm._parse_string_list(raw, expected=2)
        self.assertEqual(out, ["你好", "天气好"])

    def test_wrapped_object(self) -> None:
        raw = '{"translations":["x","y"]}'
        out = self.llm._parse_string_list(raw, expected=2)
        self.assertEqual(out, ["x", "y"])

    def test_numbered_pipe(self) -> None:
        raw = "1|你好。\n2|今天天气真好。\n3|接下来怎么办？"
        out = self.llm._parse_string_list(raw, expected=3)
        self.assertEqual(out, ["你好。", "今天天气真好。", "接下来怎么办？"])

    def test_truncated_json_repaired(self) -> None:
        raw = '[\n"甲",\n"乙",\n"丙'
        out = self.llm._parse_string_list(raw, expected=3)
        self.assertEqual(out, ["甲", "乙", "丙"])

    def test_empty_raises(self) -> None:
        with self.assertRaises(LlmError):
            self.llm._parse_string_list("", expected=1)

    def test_count_mismatch(self) -> None:
        with self.assertRaises(LlmError):
            self.llm._parse_string_list('["a"]', expected=2)


class CueSplitTests(unittest.TestCase):
    def test_split_long_runon(self) -> None:
        text = "あ" * 120
        cues = [
            Cue(id=new_cue_id(), start_ms=0, end_ms=12000, source_text=text),
        ]
        out = split_long_cues(cues, max_chars=40)
        self.assertGreater(len(out), 1)
        self.assertEqual("".join(c.source_text for c in out), text)
        self.assertEqual(out[0].start_ms, 0)
        self.assertEqual(out[-1].end_ms, 12000)

    def test_keep_short(self) -> None:
        cues = [Cue(id=new_cue_id(), start_ms=0, end_ms=1000, source_text="こんにちは。")]
        out = split_long_cues(cues)
        self.assertEqual(len(out), 1)

    def test_no_cut_before_particle_ha(self) -> None:
        from app.services.cue_utils import split_japanese_text

        text = (
            "ら世界は大きくも小さくもない電気を消えた真っ暗な私の部屋"
            "暗がりで顔は見えないけど闇の中でお母さんは笑顔で私を見つめる"
            "小さいだけの世界なんてない大きいだけの世界なんてない"
            "世界は回るぐるぐるぐるぐ"
        )
        parts = split_japanese_text(text, max_chars=34)
        joined = "".join(parts)
        self.assertEqual(joined, text)
        for p in parts:
            self.assertLessEqual(len(p), 46)  # 允许略超，但不硬切助词
            self.assertFalse(p.startswith("は"), msg=p)
        # お母さん|は 不应被拆开
        blob = "｜".join(parts)
        self.assertNotIn("お母さん｜は", blob)
        self.assertTrue(any("お母さんは" in p for p in parts), parts)

    def test_merge_particle_fragment(self) -> None:
        from app.services.cue_utils import merge_fragmented_cues

        cues = [
            Cue(id="1", start_ms=0, end_ms=1000, source_text="塀の上に薄くまった年老いた猫。"),
            Cue(id="2", start_ms=1000, end_ms=1200, source_text="がいました。"),
        ]
        merged = merge_fragmented_cues(cues)
        self.assertEqual(len(merged), 1)
        self.assertIn("猫がいました", merged[0].source_text)

    def test_user_example_split_cues(self) -> None:
        text1 = (
            "ら世界は大きくも小さくもない電気を消えた真っ暗な私の部屋"
            "暗がりで顔は見えないけど闇の中でお母さん"
        )
        text2 = (
            "は笑顔で私を見つめる小さいだけの世界なんてない"
            "大きいだけの世界なんてない世界は回るぐるぐるぐるぐ"
        )
        cues = [
            Cue(id="a", start_ms=0, end_ms=5000, source_text=text1),
            Cue(id="b", start_ms=5000, end_ms=10000, source_text=text2),
        ]
        out = split_long_cues(cues, max_chars=34)
        joined = "".join(c.source_text for c in out)
        self.assertEqual(joined, text1 + text2)
        for c in out:
            self.assertFalse(c.source_text.startswith("は"), msg=c.source_text)
            self.assertLessEqual(len(c.source_text), 48)
        self.assertTrue(any("お母さんは" in c.source_text for c in out), [c.source_text for c in out])



if __name__ == "__main__":
    unittest.main()
