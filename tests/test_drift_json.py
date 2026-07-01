"""drift_json(): MCP-safe JSON output for drift deviation report."""
import json
import subprocess
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

from codetalk import drift
from codetalk.drift import drift_json


class TestDriftJson(unittest.TestCase):
    def _git(self, cwd, *args):
        subprocess.run(["git", *args], cwd=cwd, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def test_returns_valid_json_with_expected_keys(self):
        with tempfile.TemporaryDirectory() as t:
            repo = Path(t) / "r"
            repo.mkdir()
            self._git(repo, "init")
            self._git(repo, "config", "user.email", "t@t")
            self._git(repo, "config", "user.name", "t")
            (repo / "a.py").write_text("x=1\n")
            self._git(repo, "add", ".")
            self._git(repo, "commit", "-m", "init")
            result = drift_json(str(repo))
            data = json.loads(result)
            self.assertIn("flagged", data)
            self.assertIsInstance(data["flagged"], list)
            self.assertIn("session_count", data)

    def test_error_on_non_git_dir(self):
        with tempfile.TemporaryDirectory() as t:
            result = drift_json(t)
            data = json.loads(result)
            self.assertIn("error", data)
            self.assertEqual(data["flagged"], [])

    def test_json_scan_is_readonly(self):
        with tempfile.TemporaryDirectory() as t:
            repo = Path(t) / "r"
            repo.mkdir()
            self._git(repo, "init")
            seen = []

            def fake_scan(_project, _since, cache=None):
                seen.append(cache)
                return [], None

            with mock.patch.object(drift.gitlog, "collect_commit_files",
                                   return_value=([], None)), \
                    mock.patch.object(drift.sessions, "scan_sessions", fake_scan):
                data = json.loads(drift_json(str(repo)))
            self.assertEqual(seen, [None])
            self.assertEqual(data["flagged"], [])

    def test_cli_scan_is_readonly(self):
        with tempfile.TemporaryDirectory() as t:
            repo = Path(t) / "r"
            repo.mkdir()
            self._git(repo, "init")
            seen = []

            def fake_scan(_project, _since, cache=None):
                seen.append(cache)
                return [], None

            args = Namespace(project=str(repo), since="7 days ago")
            with mock.patch.object(drift.gitlog, "collect_commit_files",
                                   return_value=([], None)), \
                    mock.patch.object(drift.sessions, "scan_sessions", fake_scan), \
                    redirect_stdout(StringIO()):
                self.assertEqual(drift.drift_cmd(args), 0)
            self.assertEqual(seen, [None])


if __name__ == "__main__":
    unittest.main()
