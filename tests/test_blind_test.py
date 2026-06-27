"""护城河盲测脚本:确定性部分(泄漏标 / 选 commit / 并排格式)。LLM 反推侧是 I/O,不在此测。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.blind_test import (  # noqa: E402
    _real_why, format_comparison, leakage, pick_commits)


class TestLeakage(unittest.TestCase):
    def test_why_in_diff_flagged_contaminated(self):
        ratio, label = leakage("用乐观锁避免写超时", "+# 用乐观锁避免写超时\n+def save(): pass")
        self.assertGreaterEqual(ratio, 0.6)
        self.assertIn("夹带", label)

    def test_why_absent_flagged_must_fabricate(self):
        ratio, label = leakage("因为流式响应不断连才改显式循环",
                               "+def retry(x):\n+    return x + 1\n")
        self.assertLess(ratio, 0.25)
        self.assertIn("查无", label)

    def test_empty_why_safe(self):
        self.assertEqual(leakage("", "diff")[0], 0.0)


class TestRealWhy(unittest.TestCase):
    def test_combines_decision_and_rejected(self):
        body = "Vibe-Decision: 用乐观锁\nVibe-Rejected: 悲观锁太重"
        real = _real_why(body)
        self.assertIn("用乐观锁", real)
        self.assertIn("(否决)悲观锁太重", real)


class TestPickCommits(unittest.TestCase):
    def test_filters_breadcrumbless_takes_newest_first(self):
        commits = [{"sha": "a" * 40, "body": "no crumb", "subject": "x"},
                   {"sha": "b" * 40, "body": "Vibe-Decision: d", "subject": "y"},
                   {"sha": "c" * 40, "body": "Vibe-Rejected: r", "subject": "z"}]
        picked = pick_commits(commits, 5)
        shas = [c["sha"] for c in picked]
        self.assertNotIn("a" * 40, shas)         # 无面包屑 → 排除
        self.assertEqual(shas[0], "c" * 40)      # 新→旧

    def test_respects_n(self):
        commits = [{"sha": str(i) * 40, "body": "Vibe-Decision: d", "subject": "s"}
                   for i in range(5)]
        self.assertEqual(len(pick_commits(commits, 2)), 2)


class TestFormat(unittest.TestCase):
    def test_shows_both_sides_and_human_verdict(self):
        out = format_comparison({"sha": "a" * 40, "subject": "s", "date": "2026-06-27"},
                                ["真实:用乐观锁"], "反推:大概为性能", 0.1, "diff 查无(...)")
        self.assertIn("真实:用乐观锁", out)
        self.assertIn("反推:大概为性能", out)
        self.assertIn("你来判", out)             # 不自动判对错
        self.assertIn("diff 查无", out)


if __name__ == "__main__":
    unittest.main()
