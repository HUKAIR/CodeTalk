import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from vibetrace.gitlog import line_log, file_log, commit_body


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


if __name__ == "__main__":
    unittest.main()
