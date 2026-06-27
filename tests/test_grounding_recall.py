"""grounding_recall 纯函数:行级接地召回(零 LLM)的取样与判定。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.grounding_recall import (  # noqa: E402
    line_grounded, sample_lines, segment_has_why)


class TestSegmentHasWhy(unittest.TestCase):
    def test_why_counts(self):
        self.assertTrue(segment_has_why({"why": "为了避免崩溃"}))

    def test_decisions_count(self):
        self.assertTrue(segment_has_why({"decisions": ["选 difflib"]}))

    def test_risks_alone_not_why(self):
        # Vibe-Watch(risks)是前瞻预测、非『为什么这么写』,单独不算 why
        self.assertFalse(segment_has_why(
            {"why": "", "decisions": [], "evidence": [], "risks": ["待验证 X"]}))

    def test_evidence_counts(self):
        self.assertTrue(segment_has_why({"evidence": [{"source": "claude"}]}))

    def test_empty_is_false(self):
        self.assertFalse(segment_has_why(
            {"why": "", "decisions": [], "risks": [], "evidence": []}))

    def test_whitespace_why_is_false(self):
        self.assertFalse(segment_has_why({"why": "   "}))


class TestLineGrounded(unittest.TestCase):
    def test_newest_grounded(self):
        # segments 旧→新;末尾(最新)有 why → strict 与 window 均 True
        segs = [{"why": ""}, {"why": "真实理由"}]
        self.assertEqual(line_grounded(segs), (True, True))

    def test_only_older_grounded(self):
        # 仅较旧段有 why、最新段是无 why 的琐碎改动 → window True、strict False
        segs = [{"decisions": ["真决策"]}, {"why": ""}]
        self.assertEqual(line_grounded(segs), (True, False))

    def test_none_grounded(self):
        segs = [{"why": ""}, {"why": "  ", "decisions": []}]
        self.assertEqual(line_grounded(segs), (False, False))

    def test_empty_segments(self):
        self.assertEqual(line_grounded([]), (False, False))


class TestSampleLines(unittest.TestCase):
    def test_deterministic_same_seed(self):
        fl = {"a.py": [1, 2, 3, 4], "b.py": [1, 2]}
        self.assertEqual(sample_lines(fl, 3, seed=7), sample_lines(fl, 3, seed=7))

    def test_cap_respected_and_subset(self):
        fl = {"a.py": [1, 2, 3, 4], "b.py": [1, 2]}
        out = sample_lines(fl, 3, seed=7)
        self.assertEqual(len(out), 3)
        pool = {("a.py", n) for n in (1, 2, 3, 4)} | {("b.py", n) for n in (1, 2)}
        self.assertTrue(set(out) <= pool)

    def test_n_exceeds_pool_returns_all(self):
        fl = {"a.py": [1, 2]}
        self.assertEqual(sample_lines(fl, 99, seed=7), [("a.py", 1), ("a.py", 2)])

    def test_output_sorted(self):
        fl = {"z.py": [9, 1], "a.py": [5]}
        out = sample_lines(fl, 99, seed=7)
        self.assertEqual(out, sorted(out))


if __name__ == "__main__":
    unittest.main()
