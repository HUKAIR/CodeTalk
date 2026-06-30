"""Task 1: session summary 加 source 标签(claude/cursor)。

source 标签贯穿后续 evidence 写入与展示,区分原话来自哪个工具。
Claude summary["source"]=="claude";Cursor summary["source"]=="cursor"。
"""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from codetalk import cursor_sessions, sessions


def _line(obj):
    return json.dumps(obj, ensure_ascii=False) + "\n"


class TestClaudeSourceTag(unittest.TestCase):
    def setUp(self):
        self._orig = sessions.CLAUDE_PROJECTS
        self.addCleanup(lambda: setattr(sessions, "CLAUDE_PROJECTS",
                                        self._orig))

    def _scan(self, tmp):
        sessions.CLAUDE_PROJECTS = Path(tmp)
        return sessions.scan_sessions("/repo", None)

    def test_scan_sessions_tags_source_claude(self):
        with TemporaryDirectory() as tmp:
            slug = sessions.project_slug("/repo")
            root = Path(tmp) / slug
            root.mkdir(parents=True)
            rec = {"type": "user", "uuid": "u1", "sessionId": "sess-A",
                   "timestamp": "2026-06-21T10:00:00.000Z",
                   "isSidechain": False,
                   "message": {"role": "user", "content": "请帮我重构解析"}}
            (root / "sess-A.jsonl").write_text(_line(rec), encoding="utf-8")
            summaries, err = self._scan(tmp)
            self.assertIsNone(err)
            self.assertTrue(summaries)
            for s in summaries:
                self.assertEqual(s["source"], "claude")


class TestCursorSourceTag(unittest.TestCase):
    def test_blank_summary_tags_source_cursor(self):
        self.assertEqual(cursor_sessions._blank_summary("x")["source"],
                         "cursor")


if __name__ == "__main__":
    unittest.main()
