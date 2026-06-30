import unittest

from codetalk.gitlog import parse_breadcrumbs, parse_rejected


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


class TestParseRejected(unittest.TestCase):
    def test_extracts_rejected(self):
        body = ("feat\n\nVibe-Rejected: 用全局 history(无 cwd 泄露其他仓)\n"
                "Vibe-Decision: 走文本归因\n")
        self.assertEqual(parse_rejected(body), ["用全局 history(无 cwd 泄露其他仓)"])

    def test_empty_and_none_safe(self):
        self.assertEqual(parse_rejected(""), [])
        self.assertEqual(parse_rejected(None), [])

    def test_ignores_lowercase_midline_and_blank_value(self):
        body = ("vibe-rejected: 小写不算\n"
                "随便 Vibe-Rejected: 行中不算\n"
                "Vibe-Rejected:   ")
        self.assertEqual(parse_rejected(body), [])


if __name__ == "__main__":
    unittest.main()
