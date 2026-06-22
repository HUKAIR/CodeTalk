"""report 命令(briefing.py)测试:零 LLM、确定性从当前仓状态生成汇报 HTML。

覆盖三块内容(变更日志 / 面包屑覆盖 / Discovery 发现)、出口脱敏、容错降级,
以及 cli report 子命令解析与 report_cmd 分发(serve vs render)。不真起服务。"""
import contextlib
import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vibetrace import briefing, cli, commands


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   text=True)


def _repo_with_commits(d):
    _git(["init", "-q"], d)
    _git(["config", "user.email", "t@t"], d)
    _git(["config", "user.name", "t"], d)
    (Path(d) / "a.py").write_text("1\n")
    _git(["add", "."], d)
    _git(["commit", "-q", "-m", "首个功能 foo"], d)
    (Path(d) / "a.py").write_text("2\n")
    _git(["add", "."], d)
    _git(["commit", "-q", "-m", "修个 bug",
          "-m", "Vibe-Decision: 选 A 因为 B\nVibe-Watch: 注意并发"], d)


class TestBuildBriefing(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)
        _repo_with_commits(self.d)

    def test_contains_commit_subjects(self):
        html, err = briefing._build_briefing(self.d)
        self.assertIsNone(err)
        self.assertIn("首个功能 foo", html)
        self.assertIn("修个 bug", html)

    def test_contains_breadcrumb_coverage_stat(self):
        html, err = briefing._build_briefing(self.d)
        self.assertIsNone(err)
        # 2 个 commit,1 个带面包屑 → "1/2"
        self.assertIn("1/2", html)

    def test_renders_roadmap_discovery_points(self):
        roadmap = Path(self.d) / "ROADMAP.md"
        roadmap.write_text(
            "# Roadmap\n\n"
            "## 发现驱动的方向修正(问卷1)\n\n"
            "- **入口 wedge** 用理解旧代码\n"
            "- 接地语料权重很关键\n\n"
            "## 明确不做\n\n- 别的\n", encoding="utf-8")
        html, err = briefing._build_briefing(self.d)
        self.assertIsNone(err)
        self.assertIn("发现驱动的方向修正", html)
        self.assertIn("入口 wedge", html)
        self.assertIn("接地语料权重很关键", html)
        self.assertNotIn("别的", html)            # 只取「发现驱动」段,不串到下一 ##
        self.assertIn("<strong>", html)           # ** 粗体已转换

    def test_lists_discovery_questionnaires(self):
        disc = Path(self.d) / "docs" / "discovery"
        disc.mkdir(parents=True)
        (disc / "gap-analysis-问卷1.md").write_text("x", encoding="utf-8")
        (disc / "gap-analysis-问卷2.md").write_text("y", encoding="utf-8")
        html, err = briefing._build_briefing(self.d)
        self.assertIsNone(err)
        self.assertIn("gap-analysis-问卷1.md", html)
        self.assertIn("gap-analysis-问卷2.md", html)

    def test_self_contained_offline_html(self):
        html, err = briefing._build_briefing(self.d)
        self.assertIsNone(err)
        self.assertIn("<style", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)        # 离线无外部依赖


class TestBriefingRedaction(unittest.TestCase):
    def test_secret_in_commit_subject_redacted(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        _git(["init", "-q"], d)
        _git(["config", "user.email", "t@t"], d)
        _git(["config", "user.name", "t"], d)
        (Path(d) / "a.py").write_text("1\n")
        _git(["add", "."], d)
        _git(["commit", "-q", "-m", "fix sk-ABCDEF0123456789ABCD"], d)
        html, err = briefing._build_briefing(d)
        self.assertIsNone(err)
        self.assertNotIn("sk-ABCDEF0123456789ABCD", html)
        self.assertIn("[REDACTED]", html)


class TestBriefingDegrade(unittest.TestCase):
    def test_no_roadmap_no_docs_no_crash(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        _repo_with_commits(d)            # 有 git 但无 ROADMAP / 无 docs/discovery
        html, err = briefing._build_briefing(d)
        self.assertIsNone(err)
        self.assertIn("<html", html.lower())

    def test_non_git_dir_no_crash(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        html, err = briefing._build_briefing(d)   # 非 git 仓也要稳
        self.assertIsNone(err)
        self.assertIn("<html", html.lower())


class TestRenderReport(unittest.TestCase):
    def test_writes_html_to_vault(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        _repo_with_commits(d)
        vault = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, vault, ignore_errors=True)
        with mock.patch("vibetrace.briefing.load_config",
                        return_value={"vault_path": vault}):
            path, err = briefing.render_report(d)
        self.assertIsNone(err)
        self.assertTrue(path.exists())
        self.assertTrue(path.name.endswith("-report.html"))
        self.assertIn("修个 bug", path.read_text(encoding="utf-8"))


class TestReportCmdDispatch(unittest.TestCase):
    def _args(self, serve=False, no_open=False):
        return mock.Mock(project=".", serve=serve, no_open=no_open)

    def test_serve_goes_to_serve_report(self):
        with mock.patch("vibetrace.briefing.serve_report",
                        return_value=None) as srv, \
             mock.patch("vibetrace.briefing.render_report") as rnd:
            rc = commands.report_cmd(self._args(serve=True))
        self.assertEqual(rc, 0)
        srv.assert_called_once()
        rnd.assert_not_called()

    def test_default_goes_to_render_report(self):
        with mock.patch("vibetrace.briefing.render_report",
                        return_value=(Path("/x/p-report.html"), None)) as rnd, \
             mock.patch("vibetrace.briefing.serve_report") as srv, \
             contextlib.redirect_stdout(io.StringIO()):
            rc = commands.report_cmd(self._args(serve=False))
        self.assertEqual(rc, 0)
        rnd.assert_called_once()
        srv.assert_not_called()


class TestReportCLIParse(unittest.TestCase):
    def test_cli_report_dispatches(self):
        with mock.patch("vibetrace.briefing.render_report",
                        return_value=(Path("/x/p-report.html"), None)) as rnd, \
             contextlib.redirect_stdout(io.StringIO()):
            rc = cli.main(["report", "--project", "."])
        self.assertEqual(rc, 0)
        rnd.assert_called_once()

    def test_cli_report_serve_flag(self):
        with mock.patch("vibetrace.briefing.serve_report",
                        return_value=None) as srv:
            rc = cli.main(["report", "--serve", "--no-open"])
        self.assertEqual(rc, 0)
        srv.assert_called_once()
        # --no-open → open_browser=False
        _, kwargs = srv.call_args
        self.assertFalse(kwargs["open_browser"])


if __name__ == "__main__":
    unittest.main()
