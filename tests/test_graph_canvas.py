import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from codetalk import graph


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


class TestToCanvas(unittest.TestCase):
    def _data(self):
        return {"nodes": [
            {"id": "aaaaaaa", "date": "2026-06-18", "subject": "s",
             "text": "决策一", "kind": "breadcrumb", "badge": "胶囊:待验证", "ts": 0},
            {"id": "bbbbbbb", "date": "2026-06-18", "subject": "改动x",
             "text": "", "kind": "change", "badge": "", "ts": 1}],
            "edges": [{"from": "aaaaaaa", "to": "bbbbbbb"}]}

    def test_canvas_node_and_edge_schema(self):
        canvas = graph._to_canvas(self._data())
        self.assertEqual(len(canvas["nodes"]), 2)
        self.assertEqual(len(canvas["edges"]), 1)
        n0 = canvas["nodes"][0]
        for key in ("id", "type", "text", "x", "y", "width", "height"):
            self.assertIn(key, n0)
        self.assertEqual(n0["type"], "text")
        self.assertIn("决策一", n0["text"])
        self.assertIn("胶囊:待验证", n0["text"])       # 徽标进节点文本
        self.assertEqual(n0["x"], 0)                    # ts*450
        self.assertEqual(n0["color"], "5")             # breadcrumb 配色
        self.assertNotIn("color", canvas["nodes"][1])  # change 节点无色

    def test_edge_endpoints_reference_real_nodes(self):
        canvas = graph._to_canvas(self._data())
        ids = {n["id"] for n in canvas["nodes"]}
        e = canvas["edges"][0]
        self.assertIn(e["fromNode"], ids)
        self.assertIn(e["toNode"], ids)

    def test_serializable(self):
        json.dumps(graph._to_canvas(self._data()))  # 不抛即合规


class TestBuildGraphCanvas(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.vault = tempfile.mkdtemp()
        _git(["init", "-q"], self.dir)
        _git(["config", "user.email", "t@t"], self.dir)
        _git(["config", "user.name", "t"], self.dir)
        (Path(self.dir) / "a.py").write_text("x\n")
        _git(["add", "."], self.dir)
        _git(["commit", "-q", "-m", "c1\n\nVibe-Decision: 决策一"], self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        shutil.rmtree(self.vault, ignore_errors=True)

    def _canvas_path(self):
        return Path(self.vault) / (Path(self.dir).name + "-graph.canvas")

    def test_canvas_written_when_flag(self):
        _, err = graph.build_graph(self.dir, vault=self.vault, canvas=True)
        self.assertIsNone(err)
        self.assertTrue(self._canvas_path().exists())
        obj = json.loads(self._canvas_path().read_text(encoding="utf-8"))
        self.assertIn("nodes", obj)
        self.assertIn("edges", obj)

    def test_no_canvas_by_default(self):
        graph.build_graph(self.dir, vault=self.vault)
        self.assertFalse(self._canvas_path().exists())


if __name__ == "__main__":
    unittest.main()
