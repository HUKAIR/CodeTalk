import unittest
from unittest import mock

from vibetrace import ask


class TestSinceArgs(unittest.TestCase):
    def test_none_yields_empty(self):
        self.assertEqual(ask._since_args(None), [])
        self.assertEqual(ask._since_args(""), [])

    def test_relative_date_becomes_since_flag(self):
        self.assertEqual(ask._since_args("3 days ago"), ["--since=3 days ago"])

    def test_absolute_date_becomes_since_flag(self):
        self.assertEqual(ask._since_args("2026-06-18"), ["--since=2026-06-18"])

    def test_commit_range_passed_as_revrange(self):
        self.assertEqual(ask._since_args("abc123..def456"), ["abc123..def456"])

    def test_triple_dot_range_passed_as_revrange(self):
        self.assertEqual(ask._since_args("abc...def"), ["abc...def"])


class TestRetrieveSince(unittest.TestCase):
    def test_since_forwarded_to_line_log(self):
        seen = {}

        def fake_line_log(pp, file, start, end, extra=None):
            seen["extra"] = extra
            return [], None

        with mock.patch.object(ask, "line_log", fake_line_log), \
             mock.patch.object(ask, "file_log", lambda *a, **k: ([], None)), \
             mock.patch.object(ask, "commit_body", lambda p, s: ""):
            ask._retrieve(".", "f.py", 1, 5, mock.MagicMock(),
                          since="2 days ago")
        self.assertEqual(seen["extra"], ["--since=2 days ago"])

    def test_since_forwarded_to_file_log_when_no_lines(self):
        seen = {}

        def fake_file_log(pp, file, extra=None):
            seen["extra"] = extra
            return [], None

        with mock.patch.object(ask, "file_log", fake_file_log), \
             mock.patch.object(ask, "commit_body", lambda p, s: ""):
            ask._retrieve(".", "f.py", None, None, mock.MagicMock(),
                          since="a..b")
        self.assertEqual(seen["extra"], ["a..b"])


if __name__ == "__main__":
    unittest.main()
