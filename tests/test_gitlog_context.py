import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from vibetrace.gitlog import collect_commits


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


class TestRicherDiffContext(unittest.TestCase):
    def test_diff_excerpt_includes_wide_context(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        _git(["init", "-q"], d)
        _git(["config", "user.email", "t@t"], d)
        _git(["config", "user.name", "t"], d)
        lines = [f"x{i} = {i}" for i in range(25)]
        lines[6] = "FARLINE_MARKER = 0"   # 距改动点 6 行:-U3 看不到、-U10 看得到
        lines[12] = "TARGET = 0"
        p = Path(d) / "m.py"
        p.write_text("\n".join(lines) + "\n")
        _git(["add", "."], d)
        _git(["commit", "-q", "-m", "init"], d)
        lines[12] = "TARGET = 1"          # 改第 12 行
        p.write_text("\n".join(lines) + "\n")
        _git(["add", "."], d)
        _git(["commit", "-q", "-m", "edit target"], d)

        commits, err = collect_commits(d, "30 years ago", 3000)
        self.assertIsNone(err)
        diff = commits[-1]["diff_excerpt"]            # oldest-first → 最新是 edit
        self.assertIn("TARGET = 1", diff)             # 改动本身
        self.assertIn("FARLINE_MARKER", diff)         # 6 行外上下文 → 仅宽 -U 可见


if __name__ == "__main__":
    unittest.main()
