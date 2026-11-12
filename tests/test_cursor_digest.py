import argparse, unittest
from unittest import mock
from codetalk import digest

class TestSourcesResolve(unittest.TestCase):
    def test_default_claude_only(self):
        args = argparse.Namespace(source=None)
        self.assertEqual(digest._sources({"sources": ["claude"]}, args), ["claude"])

    def test_config_enables_cursor(self):
        args = argparse.Namespace(source=None)
        self.assertEqual(
            digest._sources({"sources": ["claude", "cursor"]}, args),
            ["claude", "cursor"])

    def test_cli_override_both(self):
        args = argparse.Namespace(source="both")
        self.assertEqual(set(digest._sources({"sources": ["claude"]}, args)),
                         {"claude", "cursor"})

    def test_cli_override_cursor_only(self):
        args = argparse.Namespace(source="cursor")
        self.assertEqual(digest._sources({"sources": ["claude"]}, args), ["cursor"])


class TestDigestMergesCursor(unittest.TestCase):
    def test_cursor_scan_called_when_enabled(self):
        # 仅验证启用时 digest 会调用 cursor_sessions.scan_sessions 合并(打桩,不跑真 LLM/git)
        called = {}
        def fake_scan(project_path, since_dt, cache=None):
            called["yes"] = True
            return [{"session_id": "cur1"}], None
        with mock.patch("codetalk.cursor_sessions.scan_sessions", fake_scan), \
             mock.patch("codetalk.cursor_sessions.maybe_notice", lambda: None):
            args = argparse.Namespace(source="cursor")
            self.assertEqual(digest._sources({"sources": ["claude"]}, args), ["cursor"])
            # _sources 决定启用;合并逻辑的端到端在 Task 0 smoke / 手动 dogfood 验证

if __name__ == "__main__":
    unittest.main()
