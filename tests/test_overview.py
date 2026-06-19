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


if __name__ == "__main__":
    unittest.main()
