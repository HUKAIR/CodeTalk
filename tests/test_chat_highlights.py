"""chat.answer / answer_stream 返回带 highlights(逐字命中切段);零-LLM 降级亦带该键。"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vibetrace import chat  # noqa: E402
from vibetrace.cache import Cache  # noqa: E402


class TestChatHighlights(unittest.TestCase):
    def test_answer_has_highlights_key(self):
        # 空 cache + llm=None → 降级、无材料、无 citations → highlights 为 [](键必在)
        with tempfile.TemporaryDirectory() as d:
            out = chat.answer(Cache(":memory:"), None, Path(d), "为什么这么写",
                              now="2026-06-27T00:00:00+00:00")
        self.assertIn("highlights", out)
        self.assertIsInstance(out["highlights"], list)

    def test_answer_stream_done_has_highlights(self):
        with tempfile.TemporaryDirectory() as d:
            done = None
            for ev in chat.answer_stream(Cache(":memory:"), None, Path(d), "问",
                                         now="2026-06-27T00:00:00+00:00"):
                if ev.get("type") == "done":
                    done = ev
        self.assertIsNotNone(done)
        self.assertIn("highlights", done)
        self.assertIsInstance(done["highlights"], list)


if __name__ == "__main__":
    unittest.main()
