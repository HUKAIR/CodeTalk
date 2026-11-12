import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from codetalk import brief
from codetalk.cache import Cache


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


class TestOpenLoopNoise(unittest.TestCase):
    def test_drops_insufficient_material_and_blank(self):
        c = Cache(":memory:")
        c.put_narrative("realsha", "P", "m", {"open_loops": [
            "真的未闭环项", "材料不足", "材料不足(commit 被截断)", "   "]})
        loops = c.recent_open_loops("P")
        self.assertIn("真的未闭环项", loops)
        self.assertFalse(any(str(l).strip().startswith("材料不足") for l in loops))
        self.assertFalse(any(not str(l).strip() for l in loops))  # 无空白项


class TestBreadcrumbCoverage(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        _git(["init", "-q"], self.dir)
        _git(["config", "user.email", "t@t"], self.dir)
        _git(["config", "user.name", "t"], self.dir)
        p = Path(self.dir) / "a.py"
        p.write_text("1\n")
        _git(["add", "."], self.dir)
        _git(["commit", "-q", "-m", "c1\n\nVibe-Decision: 决策一"], self.dir)
        p.write_text("2\n")
        _git(["add", "."], self.dir)
        _git(["commit", "-q", "-m", "c2 无决策记录"], self.dir)
        p.write_text("3\n")
        _git(["add", "."], self.dir)
        _git(["commit", "-q", "-m", "c3\n\nVibe-Rejected: 不采用全局状态"], self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_coverage_counts(self):
        self.assertEqual(brief._breadcrumb_coverage(self.dir), (2, 3))

    def test_build_brief_has_coverage_section(self):
        out = brief.build_brief(Cache(":memory:"), "P", self.dir)
        self.assertIn("决策记录", out)


if __name__ == "__main__":
    unittest.main()
