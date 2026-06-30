"""codetalk web 子命令:无 [web] extra(fastapi 未装)时友好降级退出,绝不崩。
用 sys.modules patch 强制 from . import web 抛 ImportError,使测试与环境无关。"""
import io
import sys
import unittest
from contextlib import redirect_stderr
from unittest import mock

from codetalk import cli


class TestCliWeb(unittest.TestCase):
    def test_web_without_extra_friendly_error(self):
        import codetalk
        # 仅 patch sys.modules 不够:其它测试可能已 import codetalk.web,使 codetalk 包缓存了
        # web 属性,from . import web 会走属性短路、绕过 sys.modules sentinel(顺序依赖)。
        # 故同时临时删掉该属性,确保 from . import web 真正命中 None sentinel → ImportError。
        had = hasattr(codetalk, "web")
        saved = getattr(codetalk, "web", None)
        if had:
            delattr(codetalk, "web")
        try:
            with mock.patch.dict(sys.modules, {"codetalk.web": None}):  # 强制 ImportError
                buf = io.StringIO()
                with redirect_stderr(buf):
                    code = cli.main(["web", "--project", "."])
        finally:
            if had:
                setattr(codetalk, "web", saved)
        self.assertEqual(code, 2)                 # 友好退出码,不抛
        self.assertIn("[web]", buf.getvalue())    # 提示装 web extra


if __name__ == "__main__":
    unittest.main()
