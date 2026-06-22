import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vibetrace import tunnel


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


class TestTunnelRedaction(unittest.TestCase):
    """任务3:render/serve 共用 _build_html,返回前整页脱敏。"""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)
        _git(["init", "-q"], self.d)
        _git(["config", "user.email", "t@t"], self.d)
        _git(["config", "user.name", "t"], self.d)
        (Path(self.d) / "a.py").write_text("1\n")
        _git(["add", "."], self.d)
        # commit subject 里塞一个假 secret(sk- + 20 位)
        _git(["commit", "-q", "-m", "fix sk-ABCDEF0123456789ABCD"], self.d)
        self.dbfile = str(Path(self.d) / "cache.db")

    def test_build_html_redacts_secret_in_subject(self):
        with mock.patch.object(tunnel, "CACHE_DB_PATH", self.dbfile):
            html, project, err = tunnel._build_html(self.d, serve=False)
        self.assertIsNone(err)
        self.assertNotIn("sk-ABCDEF0123456789ABCD", html)   # secret 不进 HTML
        self.assertIn("[REDACTED]", html)                   # 脱敏生效

    def test_build_html_redacts_quoted_keyvalue_in_subject(self):
        # key="value" 形式:inline_json 转义引号后,只靠整页 redact 会漏 → redact_data 须先脱敏
        _git(["commit", "-q", "--allow-empty", "-m",
              'set token="ZxCvB12345Mn" ZZMARKER'], self.d)
        with mock.patch.object(tunnel, "CACHE_DB_PATH", self.dbfile):
            html, project, err = tunnel._build_html(self.d, serve=False)
        self.assertIsNone(err)
        self.assertIn("ZZMARKER", html)                     # subject 确已渲染
        self.assertNotIn("ZxCvB12345Mn", html)              # 引号定界 secret 不漏


if __name__ == "__main__":
    unittest.main()
