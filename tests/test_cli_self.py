import contextlib
import io
import unittest
from unittest import mock

from codetalk import cli, self_report


class TestCliSelf(unittest.TestCase):
    def _run_and_capture_days(self, argv):
        got = {}

        def fake_build(log_path, days, fill):
            got["days"] = days
            return "ok"

        with mock.patch.object(self_report, "build_self_report", fake_build), \
                contextlib.redirect_stdout(io.StringIO()):
            rc = cli.main(argv)
        return rc, got

    def test_self_subcommand_default_days(self):
        rc, got = self._run_and_capture_days(["self"])
        self.assertEqual(rc, 0)
        self.assertEqual(got["days"], 7)        # 默认近 7 天

    def test_self_subcommand_passes_days(self):
        rc, got = self._run_and_capture_days(["self", "--days", "30"])
        self.assertEqual(rc, 0)
        self.assertEqual(got["days"], 30)


if __name__ == "__main__":
    unittest.main()
