import unittest

from vibetrace.gitlog import parse_breadcrumbs


class TestParseBreadcrumbs(unittest.TestCase):
    def test_extracts_decision_and_watch(self):
        body = ("修复缓存键\n\n"
                "Vibe-Decision: 用 urllib 不引第三方\n"
                "Vibe-Watch: 先这么扛,并发安全待验证\n"
                "Co-Authored-By: x")
        decisions, watches = parse_breadcrumbs(body)
        self.assertEqual(decisions, ["用 urllib 不引第三方"])
        self.assertEqual(watches, ["先这么扛,并发安全待验证"])

    def test_empty_and_none_safe(self):
        self.assertEqual(parse_breadcrumbs(""), ([], []))
        self.assertEqual(parse_breadcrumbs(None), ([], []))

    def test_ignores_lowercase_midline_and_blank_value(self):
        body = ("vibe-decision: 小写不算\n"
                "随便 Vibe-Decision: 行中不算\n"
                "Vibe-Decision:   ")
        self.assertEqual(parse_breadcrumbs(body), ([], []))


if __name__ == "__main__":
    unittest.main()
