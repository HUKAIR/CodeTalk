import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from vibetrace import enrich


def _commit():
    return {"sha": "abc1234567", "author": "x", "subject": "s", "body": "",
            "date": datetime(2026, 6, 20, tzinfo=timezone.utc),
            "stat": "", "diff_excerpt": "", "files": [], "matches": []}


class TestProjectContext(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)

    def test_prefers_claude_md(self):
        (Path(self.d) / "CLAUDE.md").write_text("项目约束XYZ", encoding="utf-8")
        (Path(self.d) / "README.md").write_text("readme内容", encoding="utf-8")
        ctx = enrich._project_context(self.d)
        self.assertIn("项目约束XYZ", ctx)
        self.assertNotIn("readme内容", ctx)        # CLAUDE.md 优先

    def test_falls_back_to_readme(self):
        (Path(self.d) / "README.md").write_text("只有readme", encoding="utf-8")
        self.assertIn("只有readme", enrich._project_context(self.d))

    def test_empty_when_neither(self):
        self.assertEqual(enrich._project_context(self.d), "")

    def test_truncated_to_limit(self):
        (Path(self.d) / "CLAUDE.md").write_text("A" * 9000, encoding="utf-8")
        self.assertLessEqual(len(enrich._project_context(self.d)), 4000)


class TestCommitPromptContext(unittest.TestCase):
    def test_includes_project_context(self):
        out = enrich._commit_prompt(_commit(), "我的项目背景ABC")
        self.assertIn("我的项目背景ABC", out)
        self.assertIn("项目背景", out)

    def test_omits_when_no_context(self):
        self.assertNotIn("项目背景", enrich._commit_prompt(_commit(), ""))


if __name__ == "__main__":
    unittest.main()
