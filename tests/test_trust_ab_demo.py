"""A/B 信任对照 demo:确定性部分(真实记录组装 / 无-LLM 降级)。LLM 反推侧是 I/O,不测。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from codetalk.cache import Cache  # noqa: E402
from scripts.trust_ab_demo import _llm_guess, _real_record  # noqa: E402


class TestRealRecord(unittest.TestCase):
    def test_combines_narrative_and_breadcrumbs(self):
        cache = Cache(":memory:")
        sha = "a" * 40
        cache.put_narrative(sha, "P", "m", {
            "why": "流式不断连才改显式循环", "decisions": ["用显式循环"],
            "rejected": ["装饰器重试"]})
        body = "Vibe-Decision: 保留退避上限\nVibe-Rejected: 无限重试"
        rec = _real_record(cache, sha, body)
        joined = "\n".join(rec)
        self.assertIn("Why: 流式不断连才改显式循环", joined)
        self.assertIn("Decision: 用显式循环", joined)
        self.assertIn("Rejected: 装饰器重试", joined)
        self.assertIn("Breadcrumb: 保留退避上限", joined)
        self.assertIn("Rejected: 无限重试", joined)

    def test_no_record_returns_empty(self):
        cache = Cache(":memory:")
        self.assertEqual(_real_record(cache, "b" * 40, ""), [])

    def test_breadcrumb_dedup_against_narrative(self):
        cache = Cache(":memory:")
        sha = "c" * 40
        cache.put_narrative(sha, "P", "m", {"decisions": ["用显式循环"]})
        # 面包屑里同一条 Rejected 不重复计入(_real_record 的去重)
        rec = _real_record(cache, sha, "Vibe-Rejected: 装饰器")
        self.assertEqual(sum(1 for r in rec if r == "Rejected: 装饰器"), 1)


class TestLlmGuessDegrade(unittest.TestCase):
    def test_no_llm_returns_none(self):
        self.assertIsNone(_llm_guess(None, "diff"))

    def test_empty_diff_returns_none(self):
        self.assertIsNone(_llm_guess(object(), ""))


class TestEmitHtml(unittest.TestCase):
    def test_emits_valid_redacted_page(self):
        import tempfile
        from unittest import mock
        import scripts.trust_ab_demo as d
        cache = Cache(":memory:")
        sha = "a" * 40
        cache.put_narrative(sha, "P", "m",
                            {"why": "key sk-abcdef0123456789ABCDEF leaked",
                             "decisions": ["用显式循环"]})
        sample = [{"sha": sha, "subject": "feat: x", "date": "2026-07-02",
                   "body": "Vibe-Decision: 保留退避"}]
        out = Path(tempfile.mkdtemp()) / "ab.html"
        with mock.patch.object(d, "_llm_guess", return_value="AI 猜:兼容"), \
             mock.patch.object(d, "commit_diff", return_value="+code"):
            n = d._emit_html(Path("."), sample, cache, object(), str(out))
        html = out.read_text(encoding="utf-8")
        self.assertEqual(n, 1)
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertNotIn("$data", html)                 # 占位已消费
        self.assertNotIn("$project", html)
        self.assertNotIn("sk-abcdef0123456789ABCDEF", html)   # 出口脱敏
        self.assertIn("[REDACTED]", html)
        self.assertIn('"real"', html)                   # A/B 数据已注入


if __name__ == "__main__":
    unittest.main()
