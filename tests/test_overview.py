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
    """临时 git 仓,对 a.py 提交 n 次;返回 resolve 后的绝对路径字符串。"""
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


class TestDistinctProjects(unittest.TestCase):
    def test_keeps_abspaths_drops_basename_phantoms(self):
        c = Cache(":memory:")
        # 真实路径键(三表各放一种)
        c.put_narrative("sha1", "/abs/proj-a", "m", {"what": "x"})
        c.put_daily("/abs/proj-b", "2026-06-01", "ov", "")
        c.seal_capsule("/abs/proj-c", "shaC", 0, "r", "2026-05-01", "2026-05-22")
        # basename 幻影(graph/ask/course 历史写法)——必须被滤掉
        c.put_narrative("graph:proj-a", "proj-a", "graph", {"nodes": []})
        c.put_narrative("ask:zzz", "proj-a", "ask", {"what": "y"})
        got = c.distinct_projects()
        self.assertEqual(got, ["/abs/proj-a", "/abs/proj-b", "/abs/proj-c"])

    def test_empty_cache_returns_empty_list(self):
        self.assertEqual(Cache(":memory:").distinct_projects(), [])


class TestBuildOverview(unittest.TestCase):
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

    def _open_capsule(self, cache, proj, risk, sealed="2026-05-01"):
        cache.seal_capsule(proj, "sha", 0, risk, sealed, "2026-05-22")
        cache.open_due_capsules(proj, "2026-06-01")  # 盖 opened_date → 进 pending

    def test_empty_projects_list(self):
        out = brief.build_overview(Cache(":memory:"), [], self.today)
        self.assertIn("没有需要注意的项目", out)

    def test_nonexistent_paths_skipped_silently(self):
        out = brief.build_overview(Cache(":memory:"),
                                   ["/no/such/path/xyz"], self.today)
        self.assertIn("没有需要注意的项目", out)
        self.assertNotIn("失效", out)  # 不计数、不报失效

    def test_capsule_only_project_shown(self):
        c = Cache(":memory:")
        p = self._tmpdir()  # 非 git 目录 → debt_board 返回 [],债峰 0
        self._open_capsule(c, p, "serve 模式胶囊回写可能丢失")
        out = brief.build_overview(c, [p], self.today)
        self.assertIn(Path(p).name, out)
        self.assertIn("待验证预测 1 枚", out)
        self.assertIn("serve 模式胶囊回写可能丢失", out)
        self.assertNotIn("理解债 top", out)  # 无 git → 无债行

    def test_days_ago_from_sealed_date(self):
        c = Cache(":memory:")
        p = self._tmpdir()
        self._open_capsule(c, p, "r", sealed="2026-05-01")  # 至 6/9 = 39 天
        out = brief.build_overview(c, [p], self.today)
        self.assertIn("最久 39 天前", out)

    def test_redaction_masks_secret_in_risk(self):
        c = Cache(":memory:")
        p = self._tmpdir()
        self._open_capsule(c, p, "key 是 sk-abcdef0123456789ABCDEF 别泄漏")
        out = brief.build_overview(c, [p], self.today)
        self.assertIn("[REDACTED]", out)
        self.assertNotIn("sk-abcdef0123456789ABCDEF", out)

    def test_topk_omits_lowest_debt(self):
        c = Cache(":memory:")
        a, b, cc = self._tmpdir(), self._tmpdir(), self._tmpdir()
        peaks = {a: 30.0, b: 20.0, cc: 10.0}

        def fake_board(path, cache, today, top=None):
            return [{"file": "x.py", "debt": peaks[path]}]

        with mock.patch.object(brief, "TOP_DEBT_PROJECTS", 2), \
             mock.patch("vibetrace.debt.debt_board", side_effect=fake_board):
            out = brief.build_overview(c, [a, b, cc], self.today)
        self.assertIn(Path(a).name, out)
        self.assertIn(Path(b).name, out)
        self.assertNotIn(Path(cc).name, out)        # 债最低被省
        self.assertIn("另有 1 个存活项目未入榜", out)

    def test_capsule_sorts_before_higher_debt(self):
        c = Cache(":memory:")
        hi, lo = self._tmpdir(), self._tmpdir()     # hi 债高无胶囊;lo 债低有胶囊
        self._open_capsule(c, lo, "待验证")
        peaks = {hi: 99.0, lo: 1.0}

        def fake_board(path, cache, today, top=None):
            return [{"file": "x.py", "debt": peaks[path]}]

        with mock.patch("vibetrace.debt.debt_board", side_effect=fake_board):
            out = brief.build_overview(c, [hi, lo], self.today)
        self.assertLess(out.index(Path(lo).name), out.index(Path(hi).name))


class TestBuildBriefRedacts(unittest.TestCase):
    def test_brief_output_is_redacted(self):
        c = Cache(":memory:")
        c.put_daily("/abs/proj", "2026-06-01",
                    "上次提交里写了 sk-abcdef0123456789ABCDEF", "")
        out = brief.build_brief(c, "proj", "/abs/proj")
        self.assertIn("[REDACTED]", out)
        self.assertNotIn("sk-abcdef0123456789ABCDEF", out)


class TestBriefAllCLI(unittest.TestCase):
    def setUp(self):
        self.dirs = []

    def tearDown(self):
        for d in self.dirs:
            shutil.rmtree(d, ignore_errors=True)

    def test_brief_all_routes_to_overview_and_skips_sync(self):
        repo = _make_repo(2)                       # 真实 git 仓
        self.dirs.append(repo)
        dbdir = tempfile.mkdtemp()
        self.dirs.append(dbdir)
        dbfile = str(Path(dbdir) / "cache.db")
        c = Cache(dbfile)
        c.put_daily(repo, "2026-06-01", "ov", "")  # 让 repo 可被发现
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
                rc = cli.main(["brief", "--all"])
        self.assertEqual(rc, 0)
        self.assertIn("跨项目总览", buf.getvalue())
        self.assertIn(Path(repo).name, buf.getvalue())
        self.assertFalse(synced["v"])  # --all 不跑跨项目胶囊同步


if __name__ == "__main__":
    unittest.main()
