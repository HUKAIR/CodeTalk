"""vibetrace web 子命令:无 [web] extra(fastapi 未装)时友好降级退出,绝不崩。
用 sys.modules patch 强制 from . import web 抛 ImportError,使测试与环境无关。"""
import io
import sys
import unittest
from contextlib import redirect_stderr
from unittest import mock

from vibetrace import cli


class TestCliWeb(unittest.TestCase):
    def test_web_without_extra_friendly_error(self):
        with mock.patch.dict(sys.modules, {"vibetrace.web": None}):  # 强制 ImportError
            buf = io.StringIO()
            with redirect_stderr(buf):
                code = cli.main(["web", "--project", "."])
        self.assertEqual(code, 2)                 # 友好退出码,不抛
        self.assertIn("[web]", buf.getvalue())    # 提示装 web extra


if __name__ == "__main__":
    unittest.main()
