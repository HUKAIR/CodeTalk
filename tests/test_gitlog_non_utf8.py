"""容错红线:非-UTF-8 内容的老仓(考古典型目标)不得让 git 输出解码崩溃。"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from codetalk.gitlog import collect_commits


def _git(args, cwd, **kw):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, **kw)


class TestNonUtf8Repo(unittest.TestCase):
    def test_latin1_diff_does_not_crash(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        _git(["init", "-q"], d)
        _git(["config", "user.email", "t@t"], d)
        _git(["config", "user.name", "t"], d)
        # 非-UTF-8 字节内容(latin-1 é/è);strict 解码会抛 UnicodeDecodeError
        (Path(d) / "legacy.txt").write_bytes(b"caf\xe9 na\xefve\n")
        _git(["add", "."], d)
        _git(["commit", "-q", "-m", "add legacy"], d)

        commits, err = collect_commits(d, "30 years ago", 3000)
        self.assertIsNone(err)          # 降级,不崩;替换字符无害
        self.assertEqual(len(commits), 1)


if __name__ == "__main__":
    unittest.main()
