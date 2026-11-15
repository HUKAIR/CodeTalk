import unittest

from codetalk.gitlog import has_decision_notes, parse_breadcrumbs, parse_rejected


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


class TestWrappedBreadcrumbs(unittest.TestCase):
    def test_real_wrapped_decision(self):
        body = (
            "Vibe-Decision: 两个独立复选框（支持 / 不支持），不是一个框的勾/不勾 —— 一个框分不出「判它\n"
            "  没支撑」和「还没看」，后者必须排除在分母外；都勾 = conflict，计数不进统计"
        )
        self.assertEqual(parse_breadcrumbs(body), ([
            "两个独立复选框（支持 / 不支持），不是一个框的勾/不勾 —— 一个框分不出「判它 "
            "没支撑」和「还没看」，后者必须排除在分母外；都勾 = conflict，计数不进统计"
        ], []))

    def test_wrapped_rejected(self):
        self.assertEqual(parse_rejected("Vibe-Rejected: 全局缓存\n  会串仓"),
                         ["全局缓存 会串仓"])

    def test_blank_first_line_with_continuation_is_valid(self):
        body = "Vibe-Decision:   \n  内容"
        self.assertEqual(parse_breadcrumbs(body), (["内容"], []))
        self.assertTrue(has_decision_notes(body))

    def test_wrapped_watch(self):
        self.assertEqual(parse_breadcrumbs("Vibe-Watch: 并发安全\n  待验证"),
                         ([], ["并发安全 待验证"]))

    def test_consecutive_wrapped_trailers_stay_separate(self):
        body = ("Vibe-Decision: 决策一\n  原因一\n"
                "Vibe-Watch: 风险一\n  验证一\n"
                "Vibe-Rejected: 备选一\n  否决一\n"
                "  Vibe-Decision: 决策二\n  原因二\n"
                "\tVibe-Rejected: 备选二\n  否决二\n"
                "Vibe-Watch: 风险二\n  验证二")
        self.assertEqual(parse_breadcrumbs(body),
                         (["决策一 原因一", "决策二 原因二"],
                          ["风险一 验证一", "风险二 验证二"]))
        self.assertEqual(parse_rejected(body), ["备选一 否决一", "备选二 否决二"])

    def test_indented_prose_without_trailer_is_ignored(self):
        body = "正文\n  缩进正文\n\t仍是正文"
        self.assertEqual(parse_breadcrumbs(body), ([], []))
        self.assertEqual(parse_rejected(body), [])
        self.assertFalse(has_decision_notes(body))

    def test_blank_or_unindented_line_ends_continuation(self):
        for kind in ("Decision", "Watch", "Rejected"):
            for separator in ("", " \t", "正文"):
                with self.subTest(kind=kind, separator=separator):
                    body = f"Vibe-{kind}: 首行\n  续行\n{separator}\n  不收"
                    expected = ["首行 续行"]
                    self.assertEqual(parse_breadcrumbs(body),
                                     (expected if kind == "Decision" else [],
                                      expected if kind == "Watch" else []))
                    self.assertEqual(parse_rejected(body),
                                     expected if kind == "Rejected" else [])

    def test_rejected_does_not_collect_decision_continuation(self):
        body = "Vibe-Rejected: 备选\nVibe-Decision: 决策\n  决策续行"
        self.assertEqual(parse_rejected(body), ["备选"])

    def test_indentation_and_edge_whitespace_normalized(self):
        for kind in ("Decision", "Watch", "Rejected"):
            with self.subTest(kind=kind):
                body = f"  Vibe-{kind}:  首行  \n    二行 \t\n\t\t 三行  "
                expected = ["首行 二行 三行"]
                self.assertEqual(parse_breadcrumbs(body),
                                 (expected if kind == "Decision" else [],
                                  expected if kind == "Watch" else []))
                self.assertEqual(parse_rejected(body),
                                 expected if kind == "Rejected" else [])
                self.assertTrue(has_decision_notes(body))


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
