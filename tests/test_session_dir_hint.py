"""会话目录缺失报错的因果句:recap/doctor/drift/prompts 共用出口统一补『为什么 + 会怎样』。"""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from codetalk import doctor, recap, sessions

CAUSE_SNIPPET = "还没有 Claude Code 会话记录"
APPEAR_SNIPPET = "~/.claude/projects"


class TestSessionDirHint(unittest.TestCase):
    def setUp(self):
        self.empty = Path(tempfile.mkdtemp())        # 空 CLAUDE_PROJECTS:任何项目都无会话目录
        self.addCleanup(shutil.rmtree, self.empty, True)

    def test_scan_sessions_error_has_cause(self):
        # drift/prompts/digest 都经 sessions.scan_sessions 这一个出口
        with mock.patch.object(sessions, "CLAUDE_PROJECTS", self.empty):
            _, err = sessions.scan_sessions("/tmp/no-such-proj", None)
        self.assertIn("会话目录不存在", err)
        self.assertIn(CAUSE_SNIPPET, err)
        self.assertIn(APPEAR_SNIPPET, err)

    def test_recap_pick_session_error_has_cause(self):
        with mock.patch.object(recap, "CLAUDE_PROJECTS", self.empty):
            _, err = recap._pick_session("/tmp/no-such-proj")
        self.assertIn(CAUSE_SNIPPET, err)
        self.assertIn(APPEAR_SNIPPET, err)

    def test_doctor_session_summary_has_cause(self):
        with mock.patch.object(sessions, "CLAUDE_PROJECTS", self.empty):
            line = doctor._session_summary("/tmp/no-such-proj")
        self.assertIn(CAUSE_SNIPPET, line)
        self.assertIn(APPEAR_SNIPPET, line)


if __name__ == "__main__":
    unittest.main()
