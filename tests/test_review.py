"""vibetrace review:统一 diff 解析 + 逐改动块零-LLM 历史决策溯源。纯本地 git,无 key/网络。"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vibetrace import review as review_mod
from vibetrace.blame import collect_graded, segment_has_why
from vibetrace.cache import Cache
from vibetrace.review import parse_unified_diff, review


def _git(a, c):
    subprocess.run(["git", *a], cwd=c, check=True, capture_output=True, text=True)


class TestParseUnifiedDiff(unittest.TestCase):
    def test_extracts_per_hunk_post_image_ranges(self):
        diff = ("diff --git a/foo.py b/foo.py\n--- a/foo.py\n+++ b/foo.py\n"
                "@@ -1,3 +1,4 @@\n a\n+b\n c\n"
                "@@ -10,2 +12,3 @@\n x\n+y\n z\n")
        self.assertEqual(parse_unified_diff(diff),
                         [("foo.py", 1, 4), ("foo.py", 12, 14)])

    def test_single_line_hunk_and_dev_null_skipped(self):
        diff = ("--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+only\n"
                "--- a/gone.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n")
        # new.py 单行 hunk(+1 无 count → 1 行);删除到 /dev/null 的块 cur=None 跳过
        self.assertEqual(parse_unified_diff(diff), [("new.py", 1, 1)])

    def test_empty_or_garbage_no_crash(self):
        self.assertEqual(parse_unified_diff(""), [])
        self.assertEqual(parse_unified_diff("not a diff at all"), [])


class TestReview(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)
        _git(["init", "-q"], self.d)
        _git(["config", "user.email", "t@t"], self.d)
        _git(["config", "user.name", "t"], self.d)
        self.f = Path(self.d) / "a.py"
        self.f.write_text("l1\nl2\nl3\n")
        _git(["add", "."], self.d)
        _git(["commit", "-q", "-m", "feat: 初版\n\nVibe-Decision: 选三行布局便于演示"], self.d)
        self.db = str(Path(self.d) / "cache.db")

    def test_review_grounds_changed_lines_to_real_commit(self):
        self.f.write_text("l1\nCHANGED\nl3\n")          # 改第 2 行(未提交)
        diff = subprocess.run(["git", "-C", self.d, "diff", "HEAD"],
                              capture_output=True, text=True).stdout
        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.db):
            out, err = review(self.d, diff)
        self.assertIsNone(err)
        self.assertIn("a.py", out)                       # 命中文件
        self.assertIn("commit 触达", out)                # 复用 blame 头:有历史
        self.assertIn("选三行布局便于演示", out)          # 引到真实 Vibe-Decision 原话

    def test_review_labels_line_precision(self):
        # 改有历史的行 → 块尾标「溯源精度:行级精确 · 有据」(确定性准度信号)
        self.f.write_text("l1\nCHANGED\nl3\n")
        diff = subprocess.run(["git", "-C", self.d, "diff", "HEAD"],
                              capture_output=True, text=True).stdout
        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.db):
            out, err = review(self.d, diff)
        self.assertIsNone(err)
        self.assertIn("溯源精度:行级精确", out)
        self.assertIn("有据", out)                        # 命中真实 Vibe-Decision

    def test_review_labels_file_precision_on_out_of_range_hunk(self):
        # hunk 行范围超出文件长度 → line_log(-L)失败 → 文件级降级 → 标「文件级降级」
        diff = "--- a/a.py\n+++ b/a.py\n@@ -1 +999 @@\n+x\n"
        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.db):
            out, err = review(self.d, diff)
        self.assertIsNone(err)
        self.assertIn("溯源精度:文件级降级", out)

    def test_review_surfaces_rejected_alternative(self):
        # 带 Vibe-Rejected 的提交 → review/blame 把「否决备选」作一等公民标出(防重引入)
        self.f.write_text("l1\nl2\nl3\nl4\n")            # 第 4 行由带 Vibe-Rejected 的提交引入
        _git(["commit", "-aqm",
              "feat: 加行\n\nVibe-Rejected: 曾想用方案X,放弃因Y"], self.d)
        self.f.write_text("l1\nl2\nl3\nCHANGED4\n")      # 改第 4 行(未提交)
        diff = subprocess.run(["git", "-C", self.d, "diff", "HEAD"],
                              capture_output=True, text=True).stdout
        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.db):
            out, err = review(self.d, diff)
        self.assertIsNone(err)
        self.assertIn("否决备选", out)
        self.assertIn("曾想用方案X,放弃因Y", out)

    def test_review_marks_uncovered_block_as_no_evidence(self):
        # 全新文件的行无 git 历史 → 该块显式标「无据」而非编造
        diff = ("--- /dev/null\n+++ b/brand_new.py\n@@ -0,0 +1,2 @@\n+x\n+y\n")
        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.db):
            out, err = review(self.d, diff)
        self.assertIsNone(err)
        self.assertIn("无据", out)

    def test_review_empty_diff_friendly(self):
        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.db):
            out, err = review(self.d, "")
        self.assertIsNone(err)
        self.assertIn("没有可分析的改动块", out)

    def test_review_default_uses_git_diff_head(self):
        self.f.write_text("l1\nCHANGED2\nl3\n")          # diff_text=None → 内部 git diff HEAD
        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.db):
            out, err = review(self.d)                     # 不传 diff
        self.assertIsNone(err)
        self.assertIn("a.py", out)


class TestSegmentHasWhy(unittest.TestCase):
    def test_why_decisions_evidence_count(self):
        self.assertTrue(segment_has_why({"why": "x"}))
        self.assertTrue(segment_has_why({"decisions": ["d"]}))
        self.assertTrue(segment_has_why({"evidence": [{"source": "c"}]}))
        self.assertTrue(segment_has_why({"rejected": ["曾想用 X"]}))  # 否决备选也是 authored why

    def test_risks_only_and_empty_false(self):
        # Vibe-Watch(risks)是前瞻预测、非『为什么这么写』,不计
        self.assertFalse(segment_has_why(
            {"why": "", "decisions": [], "evidence": [], "risks": ["r"]}))
        self.assertFalse(segment_has_why({}))


class TestCollectGraded(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)
        _git(["init", "-q"], self.d)
        _git(["config", "user.email", "t@t"], self.d)
        _git(["config", "user.name", "t"], self.d)
        (Path(self.d) / "a.py").write_text("l1\nl2\nl3\n")
        _git(["add", "."], self.d)
        _git(["commit", "-q", "-m", "feat: 初版\n\nVibe-Decision: 选三行布局"], self.d)
        self.cache = Cache(str(Path(self.d) / "cache.db"))
        self.addCleanup(self.cache.close)

    def test_line_precision_with_range(self):
        segs, precision = collect_graded(self.cache, self.d, "a.py", 2, 2)
        self.assertEqual(precision, "line")
        self.assertTrue(segs)

    def test_file_precision_without_range(self):
        # 无行范围 → 文件级历史 → precision "file"
        _, precision = collect_graded(self.cache, self.d, "a.py", None, None)
        self.assertEqual(precision, "file")

    def test_none_precision_unknown_file(self):
        segs, precision = collect_graded(self.cache, self.d, "ghost.py", 1, 1)
        self.assertEqual(segs, [])
        self.assertEqual(precision, "none")


if __name__ == "__main__":
    unittest.main()
