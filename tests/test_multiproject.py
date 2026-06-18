import unittest

from vibetrace import brief
from vibetrace.cache import Cache


class TestRekeyProject(unittest.TestCase):
    def test_moves_capsules_daily_reviewed_old_to_new(self):
        c = Cache(":memory:")
        c.seal_capsule("api", "sha1", 0, "risk", "2026-06-01", "2026-06-22")
        c.put_daily("api", "2026-06-18", "概览", "决定")
        c.mark_reviewed("api", "sha1")
        c.rekey_project("api", "/abs/work/api")
        # 旧 basename 键查无
        self.assertEqual(c.all_capsules("api"), [])
        self.assertIsNone(c.get_daily("api", "2026-06-18"))
        self.assertEqual(c.reviewed_shas("api"), {})
        # 新全路径键查有(数据保住了)
        self.assertEqual(len(c.all_capsules("/abs/work/api")), 1)
        self.assertIsNotNone(c.get_daily("/abs/work/api", "2026-06-18"))
        self.assertIn("sha1", c.reviewed_shas("/abs/work/api"))


class TestSameBasenameIsolation(unittest.TestCase):
    def test_distinct_paths_dont_bleed(self):
        c = Cache(":memory:")
        c.seal_capsule("/a/api", "shaA", 0, "rA", "2026-06-01", "2026-06-22")
        c.seal_capsule("/b/api", "shaB", 0, "rB", "2026-06-01", "2026-06-22")
        self.assertEqual([x["risk"] for x in c.all_capsules("/a/api")], ["rA"])
        self.assertEqual([x["risk"] for x in c.all_capsules("/b/api")], ["rB"])


class TestBriefKeysByPath(unittest.TestCase):
    def test_brief_reads_daily_by_full_path(self):
        c = Cache(":memory:")
        c.put_daily("/abs/proj", "2026-06-18", "我的概览XYZ", "某决定")
        out = brief.build_brief(c, "proj", "/abs/proj")
        self.assertIn("我的概览XYZ", out)            # 按全路径读到了

    def test_brief_ignores_basename_keyed_daily(self):
        c = Cache(":memory:")
        c.put_daily("proj", "2026-06-18", "旧basename概览", "x")  # 仅 basename 键
        out = brief.build_brief(c, "proj", "/abs/proj")
        self.assertNotIn("旧basename概览", out)       # 不再按 basename 读


if __name__ == "__main__":
    unittest.main()
