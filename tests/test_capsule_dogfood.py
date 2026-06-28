"""#1 dogfood 开关:VIBETRACE_CAPSULE_DAYS 覆盖 21 天到期窗口,显式设值即 dogfood
(绕过 seal-guard,当天就能密封并开胶囊取首个回面数据点)。"""
import os
import unittest
from unittest import mock

from vibetrace import digest


class TestCapsuleDays(unittest.TestCase):
    def test_default_21_not_dogfood(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(digest._capsule_days(), (21, False))

    def test_env_override_marks_dogfood(self):
        with mock.patch.dict(os.environ, {"VIBETRACE_CAPSULE_DAYS": "0"}):
            self.assertEqual(digest._capsule_days(), (0, True))     # 0 天 + dogfood

    def test_small_window_dogfood(self):
        with mock.patch.dict(os.environ, {"VIBETRACE_CAPSULE_DAYS": "1"}):
            self.assertEqual(digest._capsule_days(), (1, True))

    def test_bad_value_falls_back_to_default(self):
        with mock.patch.dict(os.environ, {"VIBETRACE_CAPSULE_DAYS": "xyz"}):
            self.assertEqual(digest._capsule_days(), (21, False))   # 坏值不崩,回默认

    def test_negative_clamped_to_zero(self):
        with mock.patch.dict(os.environ, {"VIBETRACE_CAPSULE_DAYS": "-5"}):
            self.assertEqual(digest._capsule_days(), (0, True))


if __name__ == "__main__":
    unittest.main()
