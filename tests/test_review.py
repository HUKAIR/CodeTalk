"""vibetrace review:统一 diff 解析 + 逐改动块零-LLM 历史决策溯源。纯本地 git,无 key/网络。"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vibetrace import review as review_mod
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


if __name__ == "__main__":
    unittest.main()
