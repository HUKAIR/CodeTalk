"""--no-llm 硬开关:显式关闭 LLM 调用(数据不出本机)。覆盖 config / 环境变量 / CLI flag。

机制单点:LLMClient.__init__ 见 no_llm 即抛 LLMError → 所有现有降级路径生效
(digest 需 LLM 故干净失败;ask/course/MCP ask 降级为确定性)。一处守住,含 MCP server。
"""
import copy
import io
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

import vibetrace.config as config
from vibetrace import cli
from vibetrace.config import DEFAULTS
from vibetrace.llm import LLMClient, LLMError


def _git(a, c):
    subprocess.run(["git", *a], cwd=c, check=True, capture_output=True, text=True)


class TestNoLlmChokepoint(unittest.TestCase):
    def test_no_llm_raises_even_with_key(self):
        cfg = copy.deepcopy(DEFAULTS)
        cfg["no_llm"] = True
        cfg["providers"]["deepseek"]["api_key"] = "sk-realkey1234567890ab"  # 有 key 也拒
        with self.assertRaises(LLMError) as ctx:
            LLMClient(cfg)
        self.assertIn("no_llm", str(ctx.exception).lower())

    def test_default_no_llm_false(self):
        with mock.patch.object(config, "CONFIG_PATH", Path("/nonexistent/vt.json")), \
             mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VIBETRACE_NO_LLM", None)
            self.assertFalse(config.load_config().get("no_llm"))

    def test_env_var_sets_no_llm(self):
        with mock.patch.object(config, "CONFIG_PATH", Path("/nonexistent/vt.json")), \
             mock.patch.dict(os.environ, {"VIBETRACE_NO_LLM": "1"}):
            self.assertTrue(config.load_config().get("no_llm"))


class TestNoLlmCliFlag(unittest.TestCase):
    def test_digest_no_llm_fails_clean_even_with_key(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        _git(["init", "-q"], d)
        _git(["config", "user.email", "t@t"], d)
        _git(["config", "user.name", "t"], d)
        (Path(d) / "a.py").write_text("x\n")
        _git(["add", "."], d)
        _git(["commit", "-q", "-m", "init"], d)
        buf = io.StringIO()
        with mock.patch.object(cli, "CACHE_DB_PATH", str(Path(d) / "cache.db")), \
             mock.patch.object(config, "CONFIG_PATH", Path("/nonexistent/vt.json")), \
             mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-fakekey1234567890"}), \
             redirect_stderr(buf):
            code = cli.main(["digest", "--no-llm", "--project", d])
        self.assertEqual(code, 2)                       # digest 需 LLM → no_llm 下干净失败
        self.assertIn("no_llm", buf.getvalue().lower())  # 不调网络,信息明确


if __name__ == "__main__":
    unittest.main()
