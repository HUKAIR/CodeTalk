import unittest
from unittest import mock

from codetalk import gitlog


class TestGitlogExtra(unittest.TestCase):
    def test_merge_old_cache_uses_full_breadcrumb_at_authored_position(self):
        narrative = {"decisions": ["选择甲", "生成决策"],
                     "risks": ["并发安全"], "rejected": ["方案丙"]}
        body = ("Vibe-Decision: 选择甲\n  原因乙\n"
                "Vibe-Watch: 并发安全\n  待验证\n"
                "Vibe-Rejected: 方案丙\n  原因丁")
        with mock.patch.object(gitlog, "commit_body", return_value=body):
            self.assertEqual(gitlog.merge_breadcrumbs(narrative, ".", "sha"),
                             (["生成决策", "选择甲 原因乙"],
                              ["并发安全 待验证"], ["方案丙 原因丁"]))
        self.assertEqual(narrative["decisions"], ["选择甲", "生成决策"])

    def test_same_breadcrumb_requires_nonempty_cache_and_space_boundary(self):
        for cached, fresh, expected in [
                ("甲", "甲", True), ("甲", "甲 乙", True),
                ("甲", "甲乙", False), ("甲 乙", "甲", False),
                ("", "", False), ("", " 内容", False), ("", "内容", False)]:
            with self.subTest(cached=cached, fresh=fresh):
                self.assertEqual(gitlog.same_breadcrumb(cached, fresh), expected)

    def test_line_log_splices_extra_before_L(self):
        seen = {}

        def fake_git(args, cwd):
            seen["args"] = args
            return ""

        with mock.patch.object(gitlog, "_git", fake_git):
            gitlog.line_log(".", "f.py", 1, 5, extra=["--since=2 days ago"])
        args = seen["args"]
        self.assertIn("--since=2 days ago", args)
        # 范围 token 必须排在 -L 之前(git -L 对顺序敏感)
        self.assertLess(args.index("--since=2 days ago"),
                        args.index("-L1,5:f.py"))

    def test_file_log_splices_extra_before_pathsep(self):
        seen = {}

        def fake_git(args, cwd):
            seen["args"] = args
            return ""

        with mock.patch.object(gitlog, "_git", fake_git):
            gitlog.file_log(".", "f.py", extra=["a..b"])
        args = seen["args"]
        self.assertIn("a..b", args)
        self.assertLess(args.index("a..b"), args.index("--"))

    def test_extra_none_is_backward_compatible(self):
        seen = {}

        def fake_git(args, cwd):
            seen["args"] = args
            return ""

        with mock.patch.object(gitlog, "_git", fake_git):
            gitlog.file_log(".", "f.py")
        self.assertEqual(seen["args"],
                         ["log", "--follow", "--format=%H", "--", "f.py"])  # 跨 rename 追史


if __name__ == "__main__":
    unittest.main()
