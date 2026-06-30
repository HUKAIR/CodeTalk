"""保证 digest 拆分后公共面不破:dispatch 入口 + 日期辅助函数语义。"""
import unittest
from datetime import date, datetime, timezone


class TestDigestPublicSurface(unittest.TestCase):
    def test_commands_digest_still_callable(self):
        # cli._DISPATCH 与 main 兜底都引用 commands.digest,拆分后须仍可达。
        from codetalk import commands
        self.assertTrue(callable(commands.digest))

    def test_digest_module_exports(self):
        from codetalk import digest as digest_mod
        self.assertTrue(callable(digest_mod.digest))

    def test_shift_clamps_month_overflow(self):
        from codetalk.digest import _shift
        # 3/31 往前一月 → 2 月无 31 日,夹到月末。
        self.assertEqual(_shift(date(2026, 3, 31), months=1), date(2026, 2, 28))
        self.assertEqual(_shift(date(2026, 1, 15), years=1), date(2025, 1, 15))

    def test_since_to_dt_relative_and_iso(self):
        from codetalk.digest import _since_to_dt
        self.assertIsNone(_since_to_dt("garbage that git understands"))
        iso = _since_to_dt("2026-06-01")
        self.assertEqual(iso.tzinfo, timezone.utc)
        rel = _since_to_dt("3 days ago")
        self.assertLess(rel, datetime.now(timezone.utc))


if __name__ == "__main__":
    unittest.main()
