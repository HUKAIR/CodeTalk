"""codetalk demo:现造 fixture 仓跑真实 blame,零 key/配置。冷启动护城河展示。"""
import contextlib
import io
import unittest

from codetalk import demo


class TestDemo(unittest.TestCase):
    def test_demo_shows_verbatim_decisions_zero_config(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = demo.run_demo()
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        # 逐字引真实 commit 的决策 + 否决备选(护城河的 why-NOT)
        self.assertIn("//10 整除向下取整", out)              # Vibe-Decision 逐字
        self.assertIn("round(total/10)", out)                # Vibe-Rejected 逐字(diff 取不到)
        self.assertIn("否决备选", out)                        # blame 独立标否决
        self.assertIn("blame points.py", out)                # 跑的是真 blame 引擎

    def test_demo_cleans_up_temp_repo(self):
        import tempfile, os
        before = set(os.listdir(tempfile.gettempdir()))
        with contextlib.redirect_stdout(io.StringIO()):
            demo.run_demo()
        after = set(os.listdir(tempfile.gettempdir()))
        leaked = [n for n in (after - before) if n.startswith("codetalk-demo-")]
        self.assertEqual(leaked, [])                          # 跑完即弃,不留临时仓


if __name__ == "__main__":
    unittest.main()
