"""埋点接通验证:brief/ask/graph/course/tunnel/console 各记一行 usage。
零 API key → LLM 降级,命令仍要落埋点(容错:写失败不影响主流程)。"""
import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from codetalk import (ask, cli, commands, commands_view, console, course,
                       graph, report, tunnel)
from codetalk.config import DEFAULTS

# 各命令模块通过 `from .config import load_config, CACHE_DB_PATH` 各自绑定了名字,
# 在 config 上打补丁够不到它们,故按模块逐个改绑(指向临时 vault / cache)。
_MODULES = (ask, course, graph, tunnel, console, commands)


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


class TestUsageInstrumentation(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        _git(["init", "-q"], self.dir)
        _git(["config", "user.email", "t@t"], self.dir)
        _git(["config", "user.name", "t"], self.dir)
        p = Path(self.dir) / "a.py"
        p.write_text("x = 1\n")
        _git(["add", "."], self.dir)
        _git(["commit", "-q", "-m", "c1\n\nVibe-Decision: 决策一"], self.dir)
        self.vault = tempfile.mkdtemp()
        self.cache = tempfile.mktemp(suffix=".db")
        # 无 key 配置 → ask/course 走降级路径;输出目录指向临时 vault
        cfg = {**DEFAULTS, "vault_path": self.vault}
        for mod in _MODULES:
            if hasattr(mod, "load_config"):
                mock.patch.object(mod, "load_config", return_value=cfg).start()
            if hasattr(mod, "CACHE_DB_PATH"):
                mock.patch.object(mod, "CACHE_DB_PATH", self.cache).start()
        # commands 经 cli.CACHE_DB_PATH 取 db(见 _cache_db_path)
        mock.patch.object(cli, "CACHE_DB_PATH", self.cache).start()
        self.records = []
        self.usage_patch = mock.patch.object(
            report, "append_usage", side_effect=self.records.append)
        self.usage_patch.start()

    def tearDown(self):
        mock.patch.stopall()
        shutil.rmtree(self.dir, ignore_errors=True)
        shutil.rmtree(self.vault, ignore_errors=True)

    def _run(self, fn, args):
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            fn(SimpleNamespace(**args))

    def _commands_logged(self):
        return {r["command"] for r in self.records}

    def test_brief_logs(self):
        self._run(commands.brief_cmd,
                  {"project": self.dir, "vault": None, "all": False})
        self.assertIn("brief", self._commands_logged())

    def test_graph_logs(self):
        self._run(commands_view.graph_cmd,
                  {"project": self.dir, "vault": None, "canvas": False})
        self.assertIn("graph", self._commands_logged())

    def test_ask_logs(self):
        self._run(commands_view.ask_cmd,
                  {"project": self.dir, "target": "a.py",
                   "question": "为什么", "vault": None,
                   "since": None, "as_json": False})
        self.assertIn("ask", self._commands_logged())

    def test_course_logs(self):
        self._run(commands_view.course_cmd, {"project": self.dir})
        self.assertIn("course", self._commands_logged())

    def test_tunnel_render_logs(self):
        self._run(commands_view.tunnel_cmd,
                  {"project": self.dir, "serve": False, "no_open": True})
        self.assertIn("tunnel", self._commands_logged())

    def test_console_render_logs(self):
        self._run(commands_view.console_cmd,
                  {"project": self.dir, "serve": False, "no_open": True})
        self.assertIn("console", self._commands_logged())

    def test_append_usage_failure_does_not_break_command(self):
        """容错红线:埋点写盘失败(usage.log 路径不可写)不得拖垮主流程。"""
        self.usage_patch.stop()
        # 把 usage.log 指到一个目录上 → open(..,'a') 抛 IsADirectoryError(OSError)
        with mock.patch("codetalk.report.USAGE_LOG_PATH", Path(self.dir)):
            self._run(commands_view.graph_cmd,
                      {"project": self.dir, "vault": None, "canvas": False})
        # 没有抛出即通过;再确认 graph.html 真的写出来了
        self.assertTrue(list(Path(self.vault).glob("*-graph.html")))

    def test_append_usage_redacts_quote_delimited_secret(self):
        """usage.log 无下游兜底:须在 dumps 前脱敏。项目路径/--since 含 key="value"
        形 secret 时,若先 dumps 后 redact 会因引号转义漏过(config.py:102 的坑)。"""
        self.usage_patch.stop()
        log_path = Path(self.dir) / "usage.log"
        with mock.patch("codetalk.report.USAGE_LOG_PATH", log_path):
            report.append_usage({"command": "ask",
                                 "project": '/repo token="leakTok7788XY" x'})
        written = log_path.read_text(encoding="utf-8")
        self.assertNotIn("leakTok7788XY", written)
        self.assertIn("[REDACTED]", written)
        json.loads(written.strip())                     # 仍合法 JSON


if __name__ == "__main__":
    unittest.main()
