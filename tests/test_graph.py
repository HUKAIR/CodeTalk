import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from vibetrace import graph
from vibetrace.cache import Cache


def _c(sha, day, files, subject="s"):
    return {"sha": sha, "date": datetime(2026, 6, day, tzinfo=timezone.utc),
            "subject": subject, "files": files}


class TestAssemble(unittest.TestCase):
    def test_breadcrumb_decision_file_edge_not_unrelated(self):
        commits = [_c("d1aaaaaa", 1, ["a.py"]),     # 决策(面包屑)
                   _c("c2bbbbbb", 2, ["a.py"]),     # 后续,碰 a.py → 下游
                   _c("x3cccccc", 3, ["z.py"])]     # 碰无关文件 → 不连
        cache = Cache(":memory:")
        bodies = {"d1aaaaaa": "Vibe-Decision: 用 urllib",
                  "c2bbbbbb": "", "x3cccccc": ""}
        with mock.patch.object(graph, "commit_body", lambda p, s: bodies[s]):
            data = graph._assemble(commits, ".", "P", cache)
        ids = {n["id"]: n for n in data["nodes"]}
        self.assertEqual(ids["d1aaaaa"]["kind"], "breadcrumb")
        self.assertEqual(ids["d1aaaaa"]["text"], "用 urllib")
        froms = {(e["from"], e["to"]) for e in data["edges"]}
        self.assertIn(("d1aaaaa", "c2bbbbb"), froms)        # 同文件、更晚 → 连
        self.assertNotIn(("d1aaaaa", "x3ccccc"), froms)     # 无关文件 → 不连

    def test_narrative_fallback_kind(self):
        commits = [_c("n1aaaaaa", 1, ["a.py"]), _c("c2bbbbbb", 2, ["a.py"])]
        cache = Cache(":memory:")
        cache.put_narrative("n1aaaaaa", "P", "m",
                            {"decisions": ["叙事决策"], "risks": [], "open_loops": []})
        with mock.patch.object(graph, "commit_body", lambda p, s: ""):  # 无面包屑
            data = graph._assemble(commits, ".", "P", cache)
        n = {x["id"]: x for x in data["nodes"]}["n1aaaaa"]
        self.assertEqual(n["kind"], "narrative")
        self.assertEqual(n["text"], "叙事决策")

    def test_capsule_badge_and_redaction(self):
        commits = [_c("d1aaaaaa", 1, ["a.py"])]
        cache = Cache(":memory:")
        cache.seal_capsule("P", "d1aaaaaa", 0, "并发风险", "2026-06-01", "2026-06-22")
        with mock.patch.object(graph, "commit_body",
                               lambda p, s: "Vibe-Decision: token=sk-abcdefghijklmnop1234"):
            data = graph._assemble(commits, ".", "P", cache)
        n = data["nodes"][0]
        self.assertTrue(n["badge"].startswith("胶囊:"))     # 有胶囊 → 徽标
        self.assertNotIn("sk-abcdefghijklmnop1234", n["text"])  # 决策文案脱敏
        self.assertIn("[REDACTED]", n["text"])

    def test_out_edges_capped_at_max_out(self):
        commits = [_c("d1aaaaaa", 1, ["a.py"])] + [
            _c("c%da" % i, i + 2, ["a.py"]) for i in range(12)]  # 12 个后续都碰 a.py
        cache = Cache(":memory:")
        with mock.patch.object(graph, "commit_body",
                               lambda p, s: "Vibe-Decision: x" if s == "d1aaaaaa" else ""):
            data = graph._assemble(commits, ".", "P", cache)
        out = [e for e in data["edges"] if e["from"] == "d1aaaaa"]
        self.assertEqual(len(out), graph.MAX_OUT)            # ≤8,取最近
        targets = {e["to"] for e in out}
        # MED-3:取「其后时间最近的 8 个」= 最早的 8 个下游 c0a..c7a,排除更晚的 c8a..c11a
        for i in range(8):
            self.assertIn(("c%da" % i)[:7], targets)
        for i in range(8, 12):
            self.assertNotIn(("c%da" % i)[:7], targets)

    def test_empty_commits_no_nodes(self):
        self.assertEqual(graph._assemble([], ".", "P", Cache(":memory:")),
                         {"nodes": [], "edges": []})


import shutil, subprocess, tempfile


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


class TestBuildGraph(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        _git(["init", "-q"], self.dir)
        _git(["config", "user.email", "t@t"], self.dir)
        _git(["config", "user.name", "t"], self.dir)
        p = Path(self.dir)
        (p / "a.py").write_text("x\n")
        _git(["add", "."], self.dir)
        _git(["commit", "-q", "-m", "c1\n\nVibe-Decision: 决策一"], self.dir)
        (p / "a.py").write_text("y\n")
        _git(["add", "."], self.dir)
        _git(["commit", "-q", "-m", "c2 改 a.py"], self.dir)
        self.vault = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        shutil.rmtree(self.vault, ignore_errors=True)

    def test_build_writes_html_with_decision(self):
        out, err = graph.build_graph(self.dir, vault=self.vault)
        self.assertIsNone(err)
        self.assertTrue(out.exists())
        html = out.read_text(encoding="utf-8")
        self.assertIn("决策影响图", html)
        self.assertIn("决策一", html)          # 决策文案注入了
        self.assertIn('"nodes"', html)          # 数据 JSON 注入了

    def test_empty_repo_writes_empty_graph_not_error(self):
        empty = tempfile.mkdtemp()
        _git(["init", "-q"], empty)
        try:
            out, err = graph.build_graph(empty, vault=self.vault)
            self.assertIsNone(err)               # LOW-3:空仓不报错
            self.assertTrue(out.exists())
        finally:
            shutil.rmtree(empty, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
