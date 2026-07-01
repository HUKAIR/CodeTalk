import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

from codetalk import cli, doctor


class TestDoctor(unittest.TestCase):
    def _git(self, cwd, *args):
        subprocess.run(["git", *args], cwd=cwd, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _repo(self, breadcrumb=True):
        tmp = tempfile.TemporaryDirectory()
        repo = Path(tmp.name)
        self._git(repo, "init")
        self._git(repo, "config", "user.email", "t@t")
        self._git(repo, "config", "user.name", "t")
        (repo / "a.py").write_text("print('a')\n", encoding="utf-8")
        self._git(repo, "add", ".")
        if breadcrumb:
            self._git(repo, "commit", "-m", "init", "-m",
                      "Vibe-Decision: keep first run deterministic")
        else:
            self._git(repo, "commit", "-m", "init")
        return tmp, repo

    def test_report_surfaces_breadcrumb_coverage_and_next_step(self):
        tmp, repo = self._repo(breadcrumb=True)
        self.addCleanup(tmp.cleanup)
        report, err = doctor.build_doctor_report(repo)
        self.assertIsNone(err)
        self.assertIn("Evidence: rich (1/1 commits with breadcrumbs", report)
        self.assertIn("codetalk blame a.py --project", report)
        self.assertIn("codetalk drift --project", report)

    def test_report_labels_cold_start_repo(self):
        tmp, repo = self._repo(breadcrumb=False)
        self.addCleanup(tmp.cleanup)
        report, err = doctor.build_doctor_report(repo)
        self.assertIsNone(err)
        self.assertIn("Evidence: cold-start (0/1 commits with breadcrumbs", report)
        self.assertIn("codetalk enrich --project", report)

    def test_demo_file_prefers_groundable_signal_over_churn(self):
        # 改动最多的文件全是光秃提交,另一个改动少却带 Vibe-* 面包屑;
        # 冷启动首个 blame 应落在有零-LLM 可接地信号的文件上,而非改得最多的空文件。
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Path(tmp.name)
        self._git(repo, "init")
        self._git(repo, "config", "user.email", "t@t")
        self._git(repo, "config", "user.name", "t")
        for i in range(3):
            (repo / "busy.py").write_text(f"print({i})\n", encoding="utf-8")
            self._git(repo, "add", "busy.py")
            self._git(repo, "commit", "-m", f"tweak busy {i}")
        (repo / "rich.py").write_text("print('rich')\n", encoding="utf-8")
        self._git(repo, "add", "rich.py")
        self._git(repo, "commit", "-m", "add rich", "-m",
                  "Vibe-Decision: 逐字记录当初为何这么写")
        report, err = doctor.build_doctor_report(repo)
        self.assertIsNone(err)
        self.assertIn("codetalk blame rich.py --project", report)
        self.assertNotIn("codetalk blame busy.py", report)

    def test_cli_dispatches_doctor(self):
        seen = {}

        def fake(args):
            seen["project"] = args.project
            return 0

        with mock.patch.dict(cli._DISPATCH, {"doctor": fake}), \
                redirect_stdout(StringIO()):
            rc = cli.main(["doctor", "--project", "/tmp/example"])
        self.assertEqual(rc, 0)
        self.assertEqual(seen["project"], "/tmp/example")


if __name__ == "__main__":
    unittest.main()
