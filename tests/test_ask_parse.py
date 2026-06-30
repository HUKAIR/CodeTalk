import unittest

from codetalk.ask import _parse_target


class TestParseTarget(unittest.TestCase):
    def test_plain_file(self):
        self.assertEqual(_parse_target("a/b.py"), ("a/b.py", None, None))

    def test_range(self):
        self.assertEqual(_parse_target("a/b.py:42-60"), ("a/b.py", 42, 60))

    def test_single_line(self):
        self.assertEqual(_parse_target("b.py:7"), ("b.py", 7, 7))

    def test_colon_but_not_range_is_file(self):
        self.assertEqual(_parse_target("weird:name"), ("weird:name", None, None))


if __name__ == "__main__":
    unittest.main()
