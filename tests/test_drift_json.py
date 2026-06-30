"""drift_json(): MCP-safe JSON output for drift deviation report."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
