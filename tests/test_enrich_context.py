import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from codetalk import enrich
from codetalk.cache import Cache


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


def _sha(cwd):
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


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
    """项目背景已移出 _commit_prompt(每 commit 重传),改走 cache_prefix(缓存前缀)。
    语义不变:项目背景仍被送达 LLM,只是落在带 cache_control 的稳定前缀里。"""

    def test_commit_prompt_no_longer_carries_project_context(self):
        out = enrich._commit_prompt(_commit())
        self.assertNotIn("项目背景", out)

    def test_project_context_threaded_via_cache_prefix(self):
        captured = {}

        class _FakeLLM:
            model = "m"

            def narrate(self, prompt, **kw):
                captured["cache_prefix"] = kw.get("cache_prefix", "")
                return {"what": "x", "why": "y", "decisions": [],
                        "risks": [], "open_loops": []}

        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        (Path(d) / "CLAUDE.md").write_text("我的项目背景ABC", encoding="utf-8")
        enrich.enrich_commits([_commit()], _FakeLLM(), Cache(":memory:"), d)
        self.assertIn("我的项目背景ABC", captured["cache_prefix"])


class TestPriorContext(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)
        _git(["init", "-q"], self.d)
        _git(["config", "user.email", "t@t"], self.d)
        _git(["config", "user.name", "t"], self.d)
        a = Path(self.d) / "a.py"
        a.write_text("v1\n"); _git(["add", "."], self.d)
        _git(["commit", "-q", "-m", "A"], self.d)
        self.shaA = _sha(self.d)
        a.write_text("v2\n"); _git(["add", "."], self.d)
        _git(["commit", "-q", "-m", "B"], self.d)
        self.shaB = _sha(self.d)
        self.cache = Cache(":memory:")

    def test_includes_prior_what_when_cached(self):
        self.cache.put_narrative(self.shaA, self.d, "m",
                                 {"what": "上次给 a.py 加了 v1 逻辑"})
        ctx = enrich._prior_context(
            self.d, {"sha": self.shaB, "files": ["a.py"]}, self.cache)
        self.assertIn("上次给 a.py 加了 v1 逻辑", ctx)
        self.assertIn(self.shaA[:7], ctx)

    def test_empty_when_prior_uncached(self):
        ctx = enrich._prior_context(
            self.d, {"sha": self.shaB, "files": ["a.py"]}, self.cache)
        self.assertEqual(ctx, "")          # 前置存在但未缓存叙事

    def test_empty_when_no_prior(self):
        self.cache.put_narrative(self.shaA, self.d, "m", {"what": "x"})
        ctx = enrich._prior_context(
            self.d, {"sha": self.shaA, "files": ["a.py"]}, self.cache)
        self.assertEqual(ctx, "")          # A 无前置


if __name__ == "__main__":
    unittest.main()
