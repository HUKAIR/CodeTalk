"""零参数 `codetalk`:不再 argparse exit 2 报错,打印新手欢迎页并 exit 0。"""
import io
import unittest
from contextlib import redirect_stdout

from codetalk import cli


class TestCliWelcome(unittest.TestCase):
    def test_no_args_prints_welcome_and_exits_zero(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.main([])
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("codetalk", out)               # 一行定位
        self.assertIn("demo", out)                   # 三条新手命令
        self.assertIn("doctor", out)
        self.assertIn("--help", out)

    def test_subcommands_still_dispatch(self):
        # 拦截只对零参数生效,不改 argparse 结构
        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as ctx:
                cli.main(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("codetalk", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
