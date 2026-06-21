import unittest

from vibetrace.sessions import head_tail


class TestHeadTail(unittest.TestCase):
    def test_list_under_limit_unchanged(self):
        self.assertEqual(head_tail([1, 2, 3], 6), [1, 2, 3])

    def test_list_keeps_head_and_tail(self):
        out = head_tail(list(range(10)), 4)
        # 保留首尾:靠后的话更接近最终决策,不能纯 head 截断
        self.assertEqual(len(out), 4)
        self.assertEqual(out[0], 0)            # 首
        self.assertEqual(out[-1], 9)           # 尾(最终决策)
        self.assertIn(9, out)

    def test_list_odd_limit(self):
        out = head_tail(list(range(10)), 3)
        self.assertEqual(len(out), 3)
        self.assertEqual(out[-1], 9)

    def test_string_under_limit_unchanged(self):
        self.assertEqual(head_tail("hello", 10), "hello")

    def test_string_keeps_head_and_tail(self):
        out = head_tail("A" * 50 + "TAILMARK", 20)
        self.assertLessEqual(len(out.replace("…", "")), 20)
        self.assertTrue(out.startswith("A"))
        self.assertTrue(out.rstrip().endswith("TAILMARK"))

    def test_limit_one_list(self):
        self.assertEqual(head_tail([1, 2, 3], 1), [3])  # 只能留一个就留尾


if __name__ == "__main__":
    unittest.main()
