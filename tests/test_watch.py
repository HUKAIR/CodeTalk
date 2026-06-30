import contextlib
import io
import shutil
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from vibetrace import brief, cli, config, report
from vibetrace.cache import Cache


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


def _make_repo(n_commits):
    d = tempfile.mkdtemp()
    _git(["init", "-q"], d)
    _git(["config", "user.email", "t@t"], d)
    _git(["config", "user.name", "t"], d)
    f = Path(d) / "a.py"
    for i in range(n_commits):
        f.write_text(f"{i}\n")
        _git(["add", "."], d)
        _git(["commit", "-q", "-m", f"c{i}"], d)
    return str(Path(d).resolve())


class TestBuildWatch(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 6, 9)
        self.dirs = []

    def tearDown(self):
        for d in self.dirs:
            shutil.rmtree(d, ignore_errors=True)

    def _tmpdir(self):
        d = tempfile.mkdtemp()
        self.dirs.append(d)
        return str(Path(d).resolve())

    def _open_capsule(self, cache, proj, risk, sealed="2026-05-01", sha="sha",
                      idx=0):
        cache.seal_capsule(proj, sha, idx, risk, sealed, "2026-05-22")
        cache.open_due_capsules(proj, "2026-06-01")  # 盖 opened_date → 进 pending

    def test_empty_projects_list_is_friendly(self):
        out = brief.build_watch(Cache(":memory:"), [], self.today)
        self.assertIn("没有", out)
        # 不该崩,也不该出现报错痕迹
        self.assertNotIn("Traceback", out)

    def test_no_pending_anywhere_is_friendly(self):
        c = Cache(":memory:")
        p = self._tmpdir()
        # 已密封但未到期(open_date 在未来),不进 pending
        c.seal_capsule(p, "sha", 0, "未来风险", "2026-06-08", "2026-07-01")
        out = brief.build_watch(c, [p], self.today)
        self.assertIn("没有", out)

    def test_lists_pending_capsule_with_risk(self):
        c = Cache(":memory:")
        p = self._tmpdir()
        self._open_capsule(c, p, "serve 模式回写可能丢失")
        out = brief.build_watch(c, [p], self.today)
        self.assertIn(Path(p).name, out)
        self.assertIn("serve 模式回写可能丢失", out)

    def test_shows_days_sealed(self):
        c = Cache(":memory:")
        p = self._tmpdir()
        self._open_capsule(c, p, "r", sealed="2026-05-01")  # 至 6/9 = 39 天
        out = brief.build_watch(c, [p], self.today)
        self.assertIn("39", out)  # 已封天数

    def test_shows_fill_rate_per_project(self):
        c = Cache(":memory:")
        p = self._tmpdir()
        # 两枚开启:一枚已回填,一枚待回填 → 回填率 1/2
        self._open_capsule(c, p, "待验证的", sha="s1", idx=0)
        c.seal_capsule(p, "s2", 0, "已答的", "2026-05-01", "2026-05-22")
        c.open_due_capsules(p, "2026-06-01")
        c.set_capsule_outcome("s2:0", "成真了", p)
        out = brief.build_watch(c, [p], self.today)
        # 回填率体现为 1/2
        self.assertIn("1/2", out)
        # 已回填的不该出现在待办列表
        self.assertNotIn("已答的", out)

    def test_nonexistent_path_skipped_silently(self):
        c = Cache(":memory:")
        # 给一个失效路径密封并开启胶囊
        c.seal_capsule("/no/such/path/xyz", "sha", 0, "r", "2026-05-01",
                       "2026-05-22")
        c.open_due_capsules("/no/such/path/xyz", "2026-06-01")
        out = brief.build_watch(c, ["/no/such/path/xyz"], self.today)
        self.assertIn("没有", out)  # 失效路径不计入

    def test_redaction_masks_secret_in_risk(self):
        c = Cache(":memory:")
        p = self._tmpdir()
        self._open_capsule(c, p, "key 是 sk-abcdef0123456789ABCDEF 别泄漏")
        out = brief.build_watch(c, [p], self.today)
        self.assertIn("[REDACTED]", out)
        self.assertNotIn("sk-abcdef0123456789ABCDEF", out)

    def test_project_with_more_pending_sorts_first(self):
        c = Cache(":memory:")
        few, many = self._tmpdir(), self._tmpdir()
        self._open_capsule(c, few, "单枚", sha="f1")
        self._open_capsule(c, many, "多枚一", sha="m1", idx=0)
        c.seal_capsule(many, "m2", 0, "多枚二", "2026-05-01", "2026-05-22")
        c.open_due_capsules(many, "2026-06-01")
        out = brief.build_watch(c, [few, many], self.today)
        self.assertLess(out.index(Path(many).name), out.index(Path(few).name))

    def test_verbatim_watch_tagged_and_sorted_first(self):
        # 逐字 Vibe-Watch(commit body 真有该行)标 🎯 并排前;LLM 预测 risk 标 🤖 在后
        c = Cache(":memory:")
        p = self._tmpdir()
        self._open_capsule(c, p, "AI 猜的风险", sha="s1", idx=0)
        self._open_capsule(c, p, "我亲手标的", sha="s2", idx=0)

        def fake_body(proj, sha):
            return "Vibe-Watch: 我亲手标的" if sha == "s2" else ""
        with mock.patch.object(brief, "commit_body", fake_body):
            out = brief.build_watch(c, [p], self.today)
        self.assertIn("🎯 你标的", out)
        self.assertIn("🤖 AI 预测", out)
        self.assertLess(out.index("我亲手标的"), out.index("AI 猜的风险"))  # 逐字排前

    def test_secret_shaped_watch_still_tagged_verbatim(self):
        # 含 secret 形的手写 Watch:cache 里 risk 已脱敏([REDACTED]),body 是原文。
        # 两侧须同口径脱敏比,否则误判成 🤖 AI 预测(与 _seal 同口径,brief 此前漏修)。
        from vibetrace.config import redact_secrets
        raw = 'rotate api_key=ghp_abcd1234EFGH5678ijkl if leak'
        c = Cache(":memory:")
        p = self._tmpdir()
        self._open_capsule(c, p, redact_secrets(raw), sha="s1", idx=0)  # 存脱敏版

        with mock.patch.object(brief, "commit_body",
                               lambda proj, sha: f"Vibe-Watch: {raw}"):
            out = brief.build_watch(c, [p], self.today)
        self.assertIn("🎯 你标的", out)          # 仍认成用户手写,非 🤖
        self.assertNotIn("🤖 AI 预测", out)

    def test_bad_sealed_date_does_not_crash(self):
        c = Cache(":memory:")
        p = self._tmpdir()
        self._open_capsule(c, p, "风险", sealed="not-a-date")
        out = brief.build_watch(c, [p], self.today)  # 不抛异常即可
        self.assertIn(Path(p).name, out)


class TestWatchCLI(unittest.TestCase):
    def setUp(self):
        self.dirs = []

    def tearDown(self):
        for d in self.dirs:
            shutil.rmtree(d, ignore_errors=True)

    def test_watch_lists_due_capsules_and_skips_sync(self):
        repo = _make_repo(2)
        self.dirs.append(repo)
        dbdir = tempfile.mkdtemp()
        self.dirs.append(dbdir)
        dbfile = str(Path(dbdir) / "cache.db")
        c = Cache(dbfile)
        c.seal_capsule(repo, "sha", 0, "待验证项", "2026-05-01", "2026-05-22")
        c.open_due_capsules(repo, "2026-06-01")
        c.close()

        synced = {"v": False}
        with mock.patch.object(cli, "CACHE_DB_PATH", dbfile), \
             mock.patch.object(config, "CONFIG_PATH", Path(dbdir) / "none.json"), \
             mock.patch.object(report, "read_capsule_answers",
                               lambda *a, **k: synced.__setitem__("v", True)):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = cli.main(["watch"])
        self.assertEqual(rc, 0)
        self.assertIn("待验证项", buf.getvalue())
        self.assertIn(Path(repo).name, buf.getvalue())
        self.assertFalse(synced["v"])  # 零 LLM、不跑胶囊同步


if __name__ == "__main__":
    unittest.main()
