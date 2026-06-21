import unittest
from unittest import mock

from vibetrace import gitlog


class TestGitlogExtra(unittest.TestCase):
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
                         ["log", "--format=%H", "--", "f.py"])


if __name__ == "__main__":
    unittest.main()
