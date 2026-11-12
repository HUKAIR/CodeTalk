"""digest 收尾接地覆盖提示(零 LLM)的纯函数单测。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from codetalk.digest import coverage_nudge  # noqa: E402


class TestCoverageNudge(unittest.TestCase):
    def test_full_coverage_no_nudge(self):
        self.assertIsNone(coverage_nudge(85, 85))

    def test_empty_repo_no_nudge(self):
        self.assertIsNone(coverage_nudge(0, 0))

    def test_gap_produces_nudge(self):
        msg = coverage_nudge(85, 78)
        self.assertIsNotNone(msg)
        self.assertIn("78/85", msg)
        self.assertIn("91.8%", msg)
        self.assertIn("7 个", msg)
        self.assertIn("codetalk enrich", msg)

    def test_labeled_narrative_coverage_not_grounding(self):
        # 必须叫「叙事覆盖」(enrich 补的是叙事),不得用「接地覆盖」——后者是
        # grounding_hitrate.py 的「叙事 OR 面包屑」口径,混用会重演指标打架。
        msg = coverage_nudge(85, 78)
        self.assertIn("叙事覆盖", msg)
        self.assertNotIn("接地覆盖", msg)

    def test_over_count_guarded(self):
        # narrated > total(理论不该发生)不崩、不给负数 → 视为无缺口
        self.assertIsNone(coverage_nudge(5, 7))


if __name__ == "__main__":
    unittest.main()
