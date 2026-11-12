"""codetalk --version 打印包版本并退出 0(生产 CLI 基本约定)。"""
import contextlib
import io
import unittest

from codetalk import __version__, cli


class TestCliVersion(unittest.TestCase):
    def test_version_flag(self):
        buf = io.StringIO()
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stdout(buf):
            cli.main(["--version"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn(__version__, buf.getvalue())


if __name__ == "__main__":
    unittest.main()
