import unittest
from unittest import mock

from codetalk import ask, gitlog


class TestSinceArgs(unittest.TestCase):
    def test_none_yields_empty(self):
        self.assertEqual(ask._since_args(None), [])
        self.assertEqual(ask._since_args(""), [])

    def test_relative_date_becomes_since_flag(self):
        self.assertEqual(ask._since_args("3 days ago"), ["--since=3 days ago"])

    def test_absolute_date_becomes_since_flag(self):
        self.assertEqual(ask._since_args("2026-06-18"), ["--since=2026-06-18"])

    def test_commit_range_passed_as_revrange(self):
        self.assertEqual(ask._since_args("abc123..def456"), ["abc123..def456"])

    def test_triple_dot_range_passed_as_revrange(self):
        self.assertEqual(ask._since_args("abc...def"), ["abc...def"])


class TestRetrieveSince(unittest.TestCase):
    def test_since_forwarded_to_line_log(self):
        seen = {}

        def fake_line_log(pp, file, start, end, extra=None):
            seen["extra"] = extra
            return [], None

        with mock.patch.object(ask, "line_log", fake_line_log), \
             mock.patch.object(ask, "file_log", lambda *a, **k: ([], None)), \
             mock.patch.object(gitlog, "commit_body", lambda p, s: ""):
            ask._retrieve(".", "f.py", 1, 5, mock.MagicMock(),
                          since="2 days ago")
        self.assertEqual(seen["extra"], ["--since=2 days ago"])

    def test_since_forwarded_to_file_log_when_no_lines(self):
        seen = {}

        def fake_file_log(pp, file, extra=None):
            seen["extra"] = extra
            return [], None

        with mock.patch.object(ask, "file_log", fake_file_log), \
             mock.patch.object(gitlog, "commit_body", lambda p, s: ""):
            ask._retrieve(".", "f.py", None, None, mock.MagicMock(),
                          since="a..b")
        self.assertEqual(seen["extra"], ["a..b"])


class TestCacheKeyIncludesSince(unittest.TestCase):
    """缓存键含 since:同 file/行/question/code_state、不同 since → 不互相命中。"""

    class _FakeLLM:
        model = "fake"

        def __init__(self):
            self.calls = 0

        def narrate(self, *a, **k):
            self.calls += 1
            return {"answer": f"答案{self.calls}", "cited_shas": [], "unsure": ""}

    def test_different_since_does_not_hit_each_other(self):
        from codetalk.cache import Cache
        cache, llm = Cache(":memory:"), self._FakeLLM()
        # _retrieve 与 since 无关地返回同样 ctx/code_state,隔离出缓存键的 since 维度
        with mock.patch.object(
                ask, "_retrieve",
                lambda *a, **k: ("[s] 决策:x", ["shaX"], "shaX", [], [], [])):
            ask.answer_question(cache, llm, ".", "P", "f.py:1-2", "Q",
                                since="2 days ago")
            ask.answer_question(cache, llm, ".", "P", "f.py:1-2", "Q",
                                since="a..b")
        self.assertEqual(llm.calls, 2)        # 不同 since → 两次都调 LLM,未互相命中

    def test_same_since_hits_cache(self):
        from codetalk.cache import Cache
        cache, llm = Cache(":memory:"), self._FakeLLM()
        with mock.patch.object(
                ask, "_retrieve",
                lambda *a, **k: ("[s] 决策:x", ["shaX"], "shaX", [], [], [])):
            ask.answer_question(cache, llm, ".", "P", "f.py:1-2", "Q",
                                since="2 days ago")
            ask.answer_question(cache, llm, ".", "P", "f.py:1-2", "Q",
                                since="2 days ago")
        self.assertEqual(llm.calls, 1)        # 同 since → 第二次命中缓存


if __name__ == "__main__":
    unittest.main()
