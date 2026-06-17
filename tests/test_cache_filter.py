import unittest

from vibetrace.cache import Cache


class TestRecentOpenLoopsFilter(unittest.TestCase):
    def test_excludes_ask_course_digest_rows(self):
        c = Cache(":memory:")
        c.put_narrative("realsha", "P", "m", {"open_loops": ["真未闭环"]})
        c.put_narrative("digest:x", "P", "m", {"open_loops": ["不该出现-digest"]})
        c.put_narrative("course:v2:y", "P", "m", {"open_loops": ["不该出现-course"]})
        c.put_narrative("ask:z", "P", "m",
                        {"answer": "a", "open_loops": ["不该出现-ask"]})
        self.assertEqual(c.recent_open_loops("P"), ["真未闭环"])


if __name__ == "__main__":
    unittest.main()
