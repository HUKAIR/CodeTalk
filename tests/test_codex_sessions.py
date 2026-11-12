import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from codetalk import codex_sessions
from codetalk.cache import Cache


def _rollout(path, cwd, sid, lines):
    """写一个合成 rollout-*.jsonl(首行 session_meta + 给定记录行)。"""
    recs = [{"timestamp": "2026-06-23T11:00:00Z", "type": "session_meta",
             "payload": {"session_id": sid, "cwd": cwd, "cli_version": "x"}}]
    recs += lines
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n",
                    encoding="utf-8")


def _msg(role, text, ts="2026-06-23T11:01:00Z"):
    return {"timestamp": ts, "type": "response_item",
            "payload": {"type": "message", "role": role,
                        "content": [{"type": "input_text", "text": text}]}}


def _patch(input_text, ts="2026-06-23T11:02:00Z"):
    return {"timestamp": ts, "type": "response_item",
            "payload": {"type": "custom_tool_call", "name": "apply_patch",
                        "input": input_text}}


class TestCodexScan(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.sess = self.root / "sessions" / "2026" / "06" / "23"
        self.sess.mkdir(parents=True)
        self.proj = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.proj, ignore_errors=True)

    def _scan(self, since=None, cache=None):
        with mock.patch.object(codex_sessions, "_sessions_dir",
                               return_value=self.root / "sessions"):
            return codex_sessions.scan_sessions(str(self.proj), since, cache)

    def test_attributes_by_cwd_and_extracts(self):
        cwd = str(self.proj.resolve())
        _rollout(self.sess / "rollout-a.jsonl", cwd, "sid-a", [
            _msg("user", "<environment_context>\n<cwd>" + cwd + "</cwd>\n"),  # 注入块,过滤
            _msg("developer", "system dev instructions"),                    # 非用户,跳
            _msg("user", "把订单状态机重构成显式循环"),                        # 真实指令
            _msg("assistant", "我先梳理状态机结构再改。"),                     # excerpt
            _patch("*** Begin Patch\n*** Update File: order.py\n+x\n*** End Patch\n"),
        ])
        out, err = self._scan()
        self.assertIsNone(err)
        self.assertEqual(len(out), 1)
        s = out[0]
        self.assertEqual(s["source"], "codex")
        self.assertEqual(s["session_id"], "sid-a")
        self.assertEqual(s["prompts"], ["把订单状态机重构成显式循环"])      # 注入块/developer 已滤
        self.assertEqual(s["excerpts"], ["我先梳理状态机结构再改。"])
        self.assertIn(str(self.proj.resolve() / "order.py"), s["files_written"])  # apply_patch 路径(相对→绝对,按 cwd)
        self.assertTrue(s["title"])

    def test_other_project_skipped(self):
        _rollout(self.sess / "rollout-b.jsonl", "/some/other/repo", "sid-b",
                 [_msg("user", "无关项目")])
        out, err = self._scan()
        self.assertIsNone(err)
        self.assertEqual(out, [])

    def test_no_codex_dir_degrades(self):
        with mock.patch.object(codex_sessions, "_sessions_dir",
                               return_value=self.root / "nope"):
            out, err = codex_sessions.scan_sessions(str(self.proj), None)
        self.assertEqual(out, [])
        self.assertIsNotNone(err)

    def test_broken_lines_do_not_crash(self):
        cwd = str(self.proj.resolve())
        p = self.sess / "rollout-c.jsonl"
        _rollout(p, cwd, "sid-c", [_msg("user", "真实指令 c")])
        with p.open("a", encoding="utf-8") as fh:
            fh.write("{ this is not json\n")          # 坏行
        out, err = self._scan()
        self.assertIsNone(err)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["prompts"], ["真实指令 c"])

    def test_secret_in_prompt_redacted(self):
        cwd = str(self.proj.resolve())
        _rollout(self.sess / "rollout-d.jsonl", cwd, "sid-d",
                 [_msg("user", "用 key sk-ABCDEF0123456789ABCD 调一下")])
        out, _ = self._scan()
        joined = " ".join(out[0]["prompts"])              # files_written 是 set,不能 json.dumps
        self.assertNotIn("sk-ABCDEF0123456789ABCD", joined)
        self.assertIn("[REDACTED]", joined)

    def test_cache_roundtrip_no_crash(self):
        cwd = str(self.proj.resolve())
        _rollout(self.sess / "rollout-e.jsonl", cwd, "sid-e",
                 [_msg("user", "缓存往返 e")])
        cache = Cache(":memory:")
        out1, _ = self._scan(cache=cache)
        out2, _ = self._scan(cache=cache)              # 第二次走缓存分支
        self.assertEqual(len(out1), 1)
        self.assertEqual(out2[0]["prompts"], ["缓存往返 e"])

    def test_contract_keys_match_session_summary(self):
        cwd = str(self.proj.resolve())
        _rollout(self.sess / "rollout-f.jsonl", cwd, "sid-f",
                 [_msg("user", "契约 f")])
        out, _ = self._scan()
        for k in ("session_id", "title", "prompts", "excerpts", "files_written",
                  "files_read", "start", "end", "records", "source", "is_subagent",
                  "tokens"):
            self.assertIn(k, out[0])


if __name__ == "__main__":
    unittest.main()
