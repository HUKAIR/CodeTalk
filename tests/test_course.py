import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vibetrace import course


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


class TestCourseRedaction(unittest.TestCase):
    """任务4:course 生成 HTML 后、落盘前整页脱敏(无 API key → 朴素降级路径)。"""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)
        _git(["init", "-q"], self.d)
        _git(["config", "user.email", "t@t"], self.d)
        _git(["config", "user.name", "t"], self.d)
        (Path(self.d) / "a.py").write_text("1\n")
        _git(["add", "."], self.d)
        _git(["commit", "-q", "-m", "fix sk-ABCDEF0123456789ABCD"], self.d)
        self.dbfile = str(Path(self.d) / "cache.db")
        self.vault = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.vault, ignore_errors=True)

    def test_written_html_redacts_secret(self):
        # 无 api_key → LLMClient 抛 LLMError → 朴素降级(零网络,确定路径)
        cfg = {"vault_path": self.vault, "provider": "anthropic",
               "model": "x", "providers": {"anthropic": {}}}
        with mock.patch.object(course, "CACHE_DB_PATH", self.dbfile), \
             mock.patch.object(course, "load_config", return_value=cfg), \
             mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
            out, err = course.build_course(self.d)
        self.assertIsNone(err)
        html = out.read_text(encoding="utf-8")
        self.assertNotIn("sk-ABCDEF0123456789ABCD", html)   # secret 不进落盘 HTML
        self.assertIn("[REDACTED]", html)                   # 脱敏生效


if __name__ == "__main__":
    unittest.main()
