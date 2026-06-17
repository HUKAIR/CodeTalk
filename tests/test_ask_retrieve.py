import unittest
from unittest import mock

from vibetrace import ask
from vibetrace.cache import Cache


class TestRetrieve(unittest.TestCase):
    def test_assembles_cached_narrative_and_breadcrumbs(self):
        cache = Cache(":memory:")
        cache.put_narrative("sha1aaaabbbb", "P", "m",
                            {"why": "因为要省依赖", "decisions": ["LLM决定"],
                             "risks": [], "open_loops": []})
        with mock.patch.object(ask, "line_log",
                               lambda *a: (["sha1aaaabbbb"], None)), \
             mock.patch.object(ask, "commit_body",
                               lambda p, s: "Vibe-Watch: 并发待验证"):
            ctx, shas, state = ask._retrieve(".", "f.py", 1, 5, cache)
        self.assertIn("sha1aaa", ctx)        # 短 sha
        self.assertIn("因为要省依赖", ctx)     # 缓存叙事 why
        self.assertIn("LLM决定", ctx)         # 缓存决策
        self.assertIn("并发待验证", ctx)       # 面包屑 watch
        self.assertEqual(state, "sha1aaaabbbb")

    def test_line_log_failure_falls_back_to_file_log(self):
        cache = Cache(":memory:")
        called = {}

        def fake_file_log(*a):
            called["hit"] = True
            return ([], None)

        with mock.patch.object(ask, "line_log", lambda *a: ([], "boom")), \
             mock.patch.object(ask, "file_log", fake_file_log), \
             mock.patch.object(ask, "commit_body", lambda p, s: ""):
            ctx, shas, state = ask._retrieve(".", "f.py", 1, 5, cache)
        self.assertTrue(called.get("hit"))
        self.assertEqual(ctx, "")


if __name__ == "__main__":
    unittest.main()
