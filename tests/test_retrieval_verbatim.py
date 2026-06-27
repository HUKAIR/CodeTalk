"""retrieval._citation 的 verbatim 纯原话字段(供逐字高亮,区别于 render_hit 脚手架)。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vibetrace import retrieval  # noqa: E402


class TestCitationVerbatim(unittest.TestCase):
    def test_verbatim_pure_quotes_no_scaffolding(self):
        hit = {"sha": "a" * 40, "kind": "commit", "why": "因为要支持流式",
               "decisions": ["用显式循环重试"],
               "evidence": [{"prompts": ["把重试改成循环"], "excerpts": ["原话片段甲"]}],
               "test_refs": [], "pr_refs": []}
        c = retrieval._citation(3, hit)
        self.assertIn("verbatim", c)
        vb = c["verbatim"]
        self.assertIn("用显式循环重试", vb)
        self.assertIn("把重试改成循环", vb)
        self.assertIn("因为要支持流式", vb)
        self.assertIn("原话片段甲", vb)
        self.assertNotIn("决策:", vb)            # 无脚手架标签
        self.assertNotIn(hit["sha"][:7], vb)       # 无 sha
        self.assertIn("evidence", c)               # 展示字段仍在

    def test_verbatim_empty_hit_no_crash(self):
        # 无原话字段 → 空串,不崩(直测 _verbatim,避开 render_hit 对 text 的依赖)
        self.assertEqual(retrieval._verbatim({"sha": "b" * 40, "kind": "commit"}), "")


if __name__ == "__main__":
    unittest.main()
