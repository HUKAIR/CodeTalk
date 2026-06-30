"""Subagent (sidechain) session inclusion — task 7.

Synthetic fixtures only; the JSONL format is non-official, so these assert
the conservative contract: a file carrying a sidechain marker is parsed and
folded into its parent session, while malformed/auxiliary files degrade
silently instead of crashing.
"""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from codetalk import sessions


def _line(obj):
    return json.dumps(obj, ensure_ascii=False) + "\n"


def _main_record(sid, uuid, ts, **extra):
    rec = {"type": "user", "uuid": uuid, "sessionId": sid,
           "timestamp": ts, "isSidechain": False,
           "message": {"role": "user", "content": "请帮我重构 sessions 解析"}}
    rec.update(extra)
    return rec


def _subagent_records(sid, agent_id, ts):
    """A minimal subagent transcript: orchestrator brief (user, sidechain) +
    an assistant decision + a Write tool_use. All isSidechain:true."""
    return [
        # orchestrator brief — string content but NOT human words; must NOT
        # count as a human prompt
        {"type": "user", "uuid": "u-sub-1", "sessionId": sid,
         "agentId": agent_id, "isSidechain": True, "timestamp": ts,
         "message": {"role": "user",
                     "content": "ORCHESTRATOR BRIEF: implement task X"}},
        # assistant reasoning — decision-bearing, should be captured
        {"type": "assistant", "uuid": "a-sub-1", "sessionId": sid,
         "agentId": agent_id, "isSidechain": True, "timestamp": ts,
         "message": {"id": "msg_sub_1", "model": "claude-opus-4-8",
                     "usage": {"input_tokens": 10, "output_tokens": 5,
                               "cache_read_input_tokens": 0},
                     "content": [{"type": "text",
                                  "text": "我决定采用保守做法,因为这个 JSONL "
                                          "格式是非官方的,字段随时可能变化,所以"
                                          "采用防御式解析、字段缺失即降级跳过、"
                                          "整体绝不崩溃,是最稳妥可靠、最不容易"
                                          "踩坑、最符合规格红线的实现路线选择。"}]}},
        # assistant tool_use Write — file activity to fold into parent session
        {"type": "assistant", "uuid": "a-sub-2", "sessionId": sid,
         "agentId": agent_id, "isSidechain": True, "timestamp": ts,
         "message": {"id": "msg_sub_2", "model": "claude-opus-4-8",
                     "content": [{"type": "tool_use", "id": "toolu_1",
                                  "name": "Write",
                                  "input": {"file_path": "/repo/new_file.py",
                                            "content": "x = 1"}}]}},
    ]


class _Fixture:
    """Build a fake ~/.claude/projects/<slug>/ tree under a temp dir."""

    def __init__(self, tmp, project_path="/repo"):
        self.project_path = project_path
        slug = sessions.project_slug(project_path)
        self.root = Path(tmp) / slug
        self.root.mkdir(parents=True)

    def write_main(self, sid, ts="2026-06-21T10:00:00.000Z"):
        path = self.root / f"{sid}.jsonl"
        path.write_text(_line(_main_record(sid, "u-main-1", ts)),
                        encoding="utf-8")
        return path

    def write_subagent(self, sid, agent_id, ts="2026-06-21T10:05:00.000Z",
                       subdir="subagents"):
        d = self.root / sid / subdir
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"agent-{agent_id}.jsonl"
        path.write_text(
            "".join(_line(r) for r in _subagent_records(sid, agent_id, ts)),
            encoding="utf-8")
        return path

    def write_raw(self, relpath, text):
        path = self.root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


class TestSubagentInclusion(unittest.TestCase):
    def _scan(self, tmp):
        sessions.CLAUDE_PROJECTS = Path(tmp)
        return sessions.scan_sessions("/repo", None)

    def setUp(self):
        self._orig = sessions.CLAUDE_PROJECTS
        self.addCleanup(lambda: setattr(sessions, "CLAUDE_PROJECTS",
                                        self._orig))

    def test_subagent_file_is_included(self):
        with TemporaryDirectory() as tmp:
            fx = _Fixture(tmp)
            fx.write_main("sess-A")
            fx.write_subagent("sess-A", "agent01")
            summaries, err = self._scan(tmp)
            self.assertIsNone(err)
            sub = [s for s in summaries if s.get("is_subagent")]
            self.assertEqual(len(sub), 1, "subagent file must be parsed")

    def test_subagent_session_id_is_parent_not_filename(self):
        with TemporaryDirectory() as tmp:
            fx = _Fixture(tmp)
            fx.write_subagent("sess-A", "agent01")
            summaries, _ = self._scan(tmp)
            sub = [s for s in summaries if s.get("is_subagent")][0]
            # grouped by sessionId field, not the agentId filename stem
            self.assertEqual(sub["session_id"], "sess-A")

    def test_subagent_assistant_excerpt_and_write_captured(self):
        with TemporaryDirectory() as tmp:
            fx = _Fixture(tmp)
            fx.write_subagent("sess-A", "agent01")
            summaries, _ = self._scan(tmp)
            sub = [s for s in summaries if s.get("is_subagent")][0]
            self.assertIn("/repo/new_file.py", sub["files_written"])
            joined = "".join(sub["excerpts"])
            self.assertIn("保守做法", joined)

    def test_subagent_brief_not_counted_as_human_prompt(self):
        with TemporaryDirectory() as tmp:
            fx = _Fixture(tmp)
            fx.write_subagent("sess-A", "agent01")
            summaries, _ = self._scan(tmp)
            sub = [s for s in summaries if s.get("is_subagent")][0]
            self.assertEqual(sub["prompts"], [],
                             "orchestrator brief is not human intent")

    def test_main_session_still_parsed_alongside_subagent(self):
        with TemporaryDirectory() as tmp:
            fx = _Fixture(tmp)
            fx.write_main("sess-A")
            fx.write_subagent("sess-A", "agent01")
            summaries, _ = self._scan(tmp)
            main = [s for s in summaries if not s.get("is_subagent")]
            self.assertEqual(len(main), 1)
            self.assertEqual(main[0]["prompts"], ["请帮我重构 sessions 解析"])


class TestSubagentTolerance(unittest.TestCase):
    def setUp(self):
        self._orig = sessions.CLAUDE_PROJECTS
        self.addCleanup(lambda: setattr(sessions, "CLAUDE_PROJECTS",
                                        self._orig))

    def _scan(self, tmp):
        sessions.CLAUDE_PROJECTS = Path(tmp)
        return sessions.scan_sessions("/repo", None)

    def test_journal_and_meta_files_skipped(self):
        with TemporaryDirectory() as tmp:
            fx = _Fixture(tmp)
            fx.write_subagent("sess-A", "agent01")
            # journal.jsonl is a different schema family — must be ignored
            fx.write_raw("sess-A/subagents/workflows/wf_1/journal.jsonl",
                         _line({"type": "started", "key": "v2:abc",
                                "agentId": "agent01"}))
            # .meta.json sidecar — not a transcript
            fx.write_raw("sess-A/subagents/agent-agent01.meta.json",
                         _line({"agentType": "x", "description": "y"}))
            summaries, err = self._scan(tmp)
            self.assertIsNone(err)
            sub = [s for s in summaries if s.get("is_subagent")]
            self.assertEqual(len(sub), 1)  # only the real transcript

    def test_workflow_nested_subagent_included(self):
        with TemporaryDirectory() as tmp:
            fx = _Fixture(tmp)
            fx.write_subagent("sess-A", "agent01",
                              subdir="subagents/workflows/wf_42")
            summaries, _ = self._scan(tmp)
            sub = [s for s in summaries if s.get("is_subagent")]
            self.assertEqual(len(sub), 1)
            self.assertEqual(sub[0]["session_id"], "sess-A")

    def test_malformed_subagent_does_not_crash(self):
        with TemporaryDirectory() as tmp:
            fx = _Fixture(tmp)
            fx.write_main("sess-A")
            fx.write_raw("sess-A/subagents/agent-bad.jsonl",
                         "{not json at all\n{\"type\": \"user\"}\n")
            # must not raise; main session still returned
            summaries, err = self._scan(tmp)
            self.assertIsNone(err)
            self.assertTrue(any(not s.get("is_subagent") for s in summaries))

    def test_no_subagent_dir_is_fine(self):
        with TemporaryDirectory() as tmp:
            fx = _Fixture(tmp)
            fx.write_main("sess-A")
            summaries, err = self._scan(tmp)
            self.assertIsNone(err)
            self.assertEqual(len(summaries), 1)
            self.assertFalse(summaries[0].get("is_subagent"))


class TestFormatDriftWarning(unittest.TestCase):
    """格式漂移检测:JSONL 记录缺 type/timestamp 关键键时 warn-once,让 Anthropic
    改格式可见而非静默降级。warn-once 标志是模块全局,setUp 须重置。"""

    def setUp(self):
        sessions._format_warned = False
        self.addCleanup(lambda: setattr(sessions, "_format_warned", False))

    def test_warns_on_missing_expected_keys(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "sess.jsonl"
            # 缺 timestamp(只有 type)→ 应触发格式漂移告警
            p.write_text(_line({"type": "user", "foo": "bar"}), encoding="utf-8")
            with self.assertLogs("codetalk", level="WARNING") as cm:
                sessions._parse_file(p)
            self.assertTrue(any("format may have changed" in m for m in cm.output))

    def test_no_warn_on_well_formed_record(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "ok.jsonl"
            p.write_text(_line({"type": "user", "timestamp":
                                "2026-06-30T08:00:00Z", "uuid": "u1"}),
                         encoding="utf-8")
            with self.assertNoLogs("codetalk", level="WARNING"):
                sessions._parse_file(p)

    def test_no_warn_on_non_envelope_record_without_timestamp(self):
        # 回归(round-2 引入的虚警):ai-title / last-prompt / leafUuid 指针等非会话类型
        # 天生无 timestamp,正常每次运行都出现——绝不能据此报"格式漂移"(狼来了会钝化信号)。
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "mix.jsonl"
            p.write_text(
                _line({"type": "ai-title", "aiTitle": "重构 sessions 解析"})
                + _line({"type": "last-prompt", "leafUuid": "u9", "sessionId": "s1"})
                + _line({"type": "user", "timestamp": "2026-06-30T08:00:00Z",
                         "message": {"role": "user", "content": "x"}}),
                encoding="utf-8")
            with self.assertNoLogs("codetalk", level="WARNING"):
                sessions._parse_file(p)

    def test_warns_when_type_field_absent(self):
        # 真漂移信号:每条记录都应有 type;完全缺 type = Anthropic 改了结构。
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "drift.jsonl"
            p.write_text(_line({"role": "user", "content": "无 type 字段"}),
                         encoding="utf-8")
            with self.assertLogs("codetalk", level="WARNING") as cm:
                sessions._parse_file(p)
            self.assertTrue(any("format may have changed" in m for m in cm.output))


if __name__ == "__main__":
    unittest.main()
