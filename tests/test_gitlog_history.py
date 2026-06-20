import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from vibetrace.gitlog import (collect_commit_files, collect_commits,
                              commit_body, file_log, line_log)


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


class TestGitlogHistory(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        _git(["init", "-q"], self.dir)
        _git(["config", "user.email", "t@t"], self.dir)
        _git(["config", "user.name", "t"], self.dir)
        f = Path(self.dir) / "f.py"
        f.write_text("a\nb\nc\n")
        _git(["add", "f.py"], self.dir)
        _git(["commit", "-q", "-m", "c1 初版\n\nVibe-Decision: 初版决定"], self.dir)
        f.write_text("a\nB2\nc\n")  # 改第 2 行
        _git(["add", "f.py"], self.dir)
        _git(["commit", "-q", "-m", "c2 改第二行"], self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_line_log_returns_only_shas_oldest_first(self):
        shas, err = line_log(self.dir, "f.py", 2, 2)
        self.assertIsNone(err)
        self.assertEqual(len(shas), 2)            # 两次 commit 都动过第 2 行
        for s in shas:
            self.assertRegex(s, r"^[0-9a-f]{40}$")  # 确保没混入 diff 文本行
        self.assertIn("初版决定", commit_body(self.dir, shas[0]))  # 旧→新

    def test_file_log_fallback(self):
        shas, err = file_log(self.dir, "f.py")
        self.assertIsNone(err)
        self.assertEqual(len(shas), 2)

    def test_bad_path_degrades_with_error_not_crash(self):
        shas, err = line_log(self.dir, "nope.py", 1, 1)
        self.assertTrue(err)
        self.assertEqual(shas, [])


class TestSkipMergeCommits(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        _git(["init", "-q"], self.dir)
        _git(["config", "user.email", "t@t"], self.dir)
        _git(["config", "user.name", "t"], self.dir)
        f = Path(self.dir) / "a.py"
        f.write_text("base\n")
        _git(["add", "."], self.dir)
        _git(["commit", "-q", "-m", "c1 base"], self.dir)
        _git(["checkout", "-q", "-b", "feat"], self.dir)
        f.write_text("base\nfeat\n")
        _git(["add", "."], self.dir)
        _git(["commit", "-q", "-m", "c2 feat work"], self.dir)
        _git(["checkout", "-q", "-"], self.dir)          # 回主分支
        _git(["merge", "--no-ff", "-q", "-m", "Merge feat", "feat"], self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_collect_commits_excludes_merge(self):
        commits, err = collect_commits(self.dir, "30 years ago", 3000)
        self.assertIsNone(err)
        subs = [c["subject"] for c in commits]
        self.assertIn("c1 base", subs)
        self.assertIn("c2 feat work", subs)
        self.assertNotIn("Merge feat", subs)            # 合并气泡不进叙事

    def test_collect_commit_files_excludes_merge(self):
        commits, err = collect_commit_files(self.dir)
        self.assertIsNone(err)
        subs = [c["subject"] for c in commits]
        self.assertIn("c2 feat work", subs)
        # 子串匹配:合并记录的 subject 带尾部 NUL('Merge feat\x00'),
        # 精确比较会假阳性通过——确保合并整条不进(否则 graph 出空节点)
        self.assertFalse(any("Merge feat" in s for s in subs))


if __name__ == "__main__":
    unittest.main()
