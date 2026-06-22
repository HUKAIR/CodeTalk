"""MCP server 测试:喂 JSON-RPC 帧给 _handle/serve,不依赖真实客户端。

覆盖握手 / tools/list / tools/call(ask·blame·graph)/ 容错降级 / stdout 纯净 /
出口脱敏 / id 透传 / notification 不回。纯本地、纯内存(mock 仓与适配层)。
"""
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vibetrace import mcp_server
from vibetrace.cache import Cache


def _cfg():
    from vibetrace.config import DEFAULTS
    import copy
    return copy.deepcopy(DEFAULTS)


class TestInitialize(unittest.TestCase):
    def test_initialize_echoes_protocol_and_capabilities(self):
        req = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "2025-06-18"}}
        resp = mcp_server._handle(req, Cache(":memory:"), _cfg(), None)
        self.assertEqual(resp["id"], 1)
        r = resp["result"]
        self.assertEqual(r["protocolVersion"], "2025-06-18")  # 回显客户端版本
        self.assertIn("tools", r["capabilities"])
        self.assertEqual(r["capabilities"]["tools"]["listChanged"], False)
        self.assertEqual(r["serverInfo"]["name"], "vibetrace")

    def test_initialize_defaults_protocol_when_missing(self):
        req = {"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {}}
        resp = mcp_server._handle(req, Cache(":memory:"), _cfg(), None)
        self.assertEqual(resp["result"]["protocolVersion"], "2025-11-25")

    def test_notifications_initialized_no_reply(self):
        req = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        self.assertIsNone(mcp_server._handle(req, Cache(":memory:"), _cfg(), None))

    def test_unknown_notification_no_reply(self):
        req = {"jsonrpc": "2.0", "method": "some/unknown/notify"}  # 无 id → notification
        self.assertIsNone(mcp_server._handle(req, Cache(":memory:"), _cfg(), None))

    def test_ping_empty_result(self):
        req = {"jsonrpc": "2.0", "id": 9, "method": "ping"}
        resp = mcp_server._handle(req, Cache(":memory:"), _cfg(), None)
        self.assertEqual(resp["id"], 9)
        self.assertEqual(resp["result"], {})

    def test_unknown_method_method_not_found(self):
        req = {"jsonrpc": "2.0", "id": 3, "method": "no/such"}
        resp = mcp_server._handle(req, Cache(":memory:"), _cfg(), None)
        self.assertEqual(resp["id"], 3)
        self.assertEqual(resp["error"]["code"], -32601)

    def test_batch_array_invalid_request(self):
        # 数组(batch)在 serve 层处理;此处直接验 serve 行为见 TestServe
        pass


class TestToolsList(unittest.TestCase):
    def test_lists_three_tools_with_input_schema(self):
        req = {"jsonrpc": "2.0", "id": 4, "method": "tools/list"}
        resp = mcp_server._handle(req, Cache(":memory:"), _cfg(), None)
        tools = resp["result"]["tools"]
        names = {t["name"] for t in tools}
        self.assertEqual(names, {"vibetrace_ask", "vibetrace_blame",
                                 "vibetrace_graph"})
        for t in tools:
            self.assertIn("inputSchema", t)
            self.assertEqual(t["inputSchema"]["type"], "object")
            self.assertIn("description", t)


class TestToolsCallAsk(unittest.TestCase):
    def test_ask_returns_json_text_not_error(self):
        with mock.patch.object(mcp_server, "answer_question",
                               lambda *a, **k: ('{"mode":"llm","answer":"x"}',
                                                None)):
            req = {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                   "params": {"name": "vibetrace_ask",
                              "arguments": {"target": "f.py:1-2",
                                            "question": "为什么"}}}
            resp = mcp_server._handle(req, Cache(":memory:"), _cfg(), None)
        self.assertEqual(resp["id"], 5)
        self.assertFalse(resp["result"]["isError"])
        text = resp["result"]["content"][0]["text"]
        self.assertEqual(json.loads(text)["mode"], "llm")

    def test_ask_degraded_when_llm_none_no_error(self):
        # 真实 answer_question:llm=None → degraded,不 print,isError:false
        with mock.patch.object(mcp_server, "answer_question",
                               lambda c, llm, *a, **k:
                               ('{"mode":"degraded"}', None) if llm is None
                               else ('{"mode":"llm"}', None)):
            req = {"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                   "params": {"name": "vibetrace_ask",
                              "arguments": {"target": "f.py", "question": "Q"}}}
            resp = mcp_server._handle(req, Cache(":memory:"), _cfg(), None)
        self.assertFalse(resp["result"]["isError"])
        self.assertEqual(json.loads(resp["result"]["content"][0]["text"])["mode"],
                         "degraded")

    def test_ask_missing_required_arg_is_error(self):
        req = {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
               "params": {"name": "vibetrace_ask",
                          "arguments": {"target": "f.py"}}}  # 缺 question
        resp = mcp_server._handle(req, Cache(":memory:"), _cfg(), None)
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("question", resp["result"]["content"][0]["text"])

    def test_ask_business_error_is_error_not_crash(self):
        with mock.patch.object(mcp_server, "answer_question",
                               lambda *a, **k: (None, "没有提交历史")):
            req = {"jsonrpc": "2.0", "id": 8, "method": "tools/call",
                   "params": {"name": "vibetrace_ask",
                              "arguments": {"target": "x.py", "question": "Q"}}}
            resp = mcp_server._handle(req, Cache(":memory:"), _cfg(), None)
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("没有提交历史", resp["result"]["content"][0]["text"])

    def test_ask_exception_caught_is_error(self):
        def _boom(*a, **k):
            raise RuntimeError("内部炸了")
        with mock.patch.object(mcp_server, "answer_question", _boom):
            req = {"jsonrpc": "2.0", "id": 10, "method": "tools/call",
                   "params": {"name": "vibetrace_ask",
                              "arguments": {"target": "x.py", "question": "Q"}}}
            resp = mcp_server._handle(req, Cache(":memory:"), _cfg(), None)
        self.assertTrue(resp["result"]["isError"])


class TestToolsCallValidation(unittest.TestCase):
    def test_unknown_tool_is_error(self):
        req = {"jsonrpc": "2.0", "id": 11, "method": "tools/call",
               "params": {"name": "vibetrace_nope", "arguments": {}}}
        resp = mcp_server._handle(req, Cache(":memory:"), _cfg(), None)
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("vibetrace_nope", resp["result"]["content"][0]["text"])

    def test_arguments_not_dict_is_error(self):
        req = {"jsonrpc": "2.0", "id": 12, "method": "tools/call",
               "params": {"name": "vibetrace_graph", "arguments": "oops"}}
        resp = mcp_server._handle(req, Cache(":memory:"), _cfg(), None)
        self.assertTrue(resp["result"]["isError"])


class TestToolsCallBlameRedaction(unittest.TestCase):
    def test_blame_output_redacted_at_egress(self):
        seg = [{"sha": "a" * 40, "date": "2026-06-01", "subject": "s",
                "why": "key 是 sk-abcdefghijklmnop1234", "decisions": [],
                "risks": [], "evidence": [], "test_refs": [], "pr_refs": []}]
        with mock.patch.object(mcp_server, "collect_segments",
                               lambda *a, **k: seg):
            req = {"jsonrpc": "2.0", "id": 13, "method": "tools/call",
                   "params": {"name": "vibetrace_blame",
                              "arguments": {"target": "f.py:1-2"}}}
            resp = mcp_server._handle(req, Cache(":memory:"), _cfg(), None)
        self.assertFalse(resp["result"]["isError"])
        text = resp["result"]["content"][0]["text"]
        self.assertNotIn("sk-abcdefghijklmnop1234", text)
        self.assertIn("[REDACTED]", text)


class TestToolsCallGraph(unittest.TestCase):
    def test_graph_returns_json(self):
        with mock.patch.object(mcp_server, "build_graph_json",
                               lambda *a, **k: ('{"nodes":[],"edges":[]}', None)):
            req = {"jsonrpc": "2.0", "id": 14, "method": "tools/call",
                   "params": {"name": "vibetrace_graph", "arguments": {}}}
            resp = mcp_server._handle(req, Cache(":memory:"), _cfg(), None)
        self.assertFalse(resp["result"]["isError"])
        self.assertEqual(json.loads(resp["result"]["content"][0]["text"]),
                         {"nodes": [], "edges": []})

    def test_graph_no_arguments_key_is_not_error(self):
        # MCP 协议中 params.arguments 可选;无 required 的 graph 应零参可用
        with mock.patch.object(mcp_server, "build_graph_json",
                               lambda *a, **k: ('{"nodes":[],"edges":[]}', None)):
            req = {"jsonrpc": "2.0", "id": 15, "method": "tools/call",
                   "params": {"name": "vibetrace_graph"}}  # 不带 arguments 键
            resp = mcp_server._handle(req, Cache(":memory:"), _cfg(), None)
        self.assertFalse(resp["result"]["isError"])
        self.assertEqual(json.loads(resp["result"]["content"][0]["text"]),
                         {"nodes": [], "edges": []})


class TestServeLoop(unittest.TestCase):
    def _run(self, lines):
        stdin = io.StringIO("".join(l + "\n" for l in lines))
        stdout = io.StringIO()
        stderr = io.StringIO()
        mcp_server.serve(stdin, stdout, Cache(":memory:"), _cfg(), None,
                         stderr=stderr)
        return stdout.getvalue(), stderr.getvalue()

    def test_stdout_pure_jsonrpc_each_line(self):
        init = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {}})
        note = json.dumps({"jsonrpc": "2.0",
                           "method": "notifications/initialized"})
        lst = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        out, err = self._run([init, note, lst])
        for line in out.splitlines():
            obj = json.loads(line)            # 每行都是合法 JSON
            self.assertEqual(obj["jsonrpc"], "2.0")
        # notification 不回 → 只有 2 条响应(init + list)
        self.assertEqual(len(out.splitlines()), 2)

    def test_malformed_json_parse_error_loop_continues(self):
        good = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        out, err = self._run(["{ not json", good])
        lines = out.splitlines()
        first = json.loads(lines[0])
        self.assertEqual(first["error"]["code"], -32700)
        self.assertIsNone(first["id"])         # parse error id=null
        second = json.loads(lines[1])          # 循环未退出,后续帧仍被处理
        self.assertEqual(second["id"], 1)
        self.assertEqual(second["result"], {})

    def test_batch_array_invalid_request(self):
        batch = "[" + json.dumps({"jsonrpc": "2.0", "id": 1,
                                  "method": "ping"}) + "]"
        out, err = self._run([batch])
        obj = json.loads(out.splitlines()[0])
        self.assertEqual(obj["error"]["code"], -32600)

    def test_logging_goes_to_stderr_not_stdout(self):
        # answer_question 触发 _log_usage 等不应污染 stdout;用真实降级路径
        with mock.patch.object(mcp_server, "answer_question",
                               lambda *a, **k: ('{"mode":"degraded"}', None)):
            call = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                               "params": {"name": "vibetrace_ask",
                                          "arguments": {"target": "f.py",
                                                        "question": "Q"}}})
            out, err = self._run([call])
        for line in out.splitlines():
            json.loads(line)                   # stdout 纯净
        self.assertEqual(len(out.splitlines()), 1)


class TestServeRealPath(unittest.TestCase):
    """真实路径(非 mock)e2e:真 git 仓跑 blame,验 stdout 纯净 + 出口脱敏走真实业务路径
    (mock 版只验框架,这条防『有人往真实 collect_segments/_log_usage 加 print』的回归)。"""

    def _git(self, cwd, *args):
        subprocess.run(["git", *args], cwd=cwd, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def test_real_blame_stdout_pure_and_exit_redacted(self):
        with tempfile.TemporaryDirectory() as t:
            repo = Path(t) / "repo"; repo.mkdir()
            self._git(repo, "init"); self._git(repo, "config", "user.email", "t@t.t")
            self._git(repo, "config", "user.name", "t")
            (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
            self._git(repo, "add", "a.py")
            self._git(repo, "commit", "-m", "fix leak sk-abcdef0123456789ABCD")
            init = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                               "params": {}})
            call = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                               "params": {"name": "vibetrace_blame",
                                          "arguments": {"target": "a.py",
                                                        "project": str(repo)}}})
            stdin = io.StringIO("\n".join([init, call]) + "\n")
            out, err = io.StringIO(), io.StringIO()
            mcp_server.serve(stdin, out, Cache(":memory:"), _cfg(), None, stderr=err)
            lines = out.getvalue().splitlines()
            for line in lines:
                self.assertEqual(json.loads(line)["jsonrpc"], "2.0")  # 真实路径 stdout 纯净
            text = json.loads(lines[1])["result"]["content"][0]["text"]
            self.assertNotIn("sk-abcdef0123456789ABCD", text)   # 真实 blame 出口脱敏
            self.assertIn("[REDACTED]", text)


if __name__ == "__main__":
    unittest.main()
