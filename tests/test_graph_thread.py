"""Development thread graph: commit trunk, note leaves, and local-only annotations."""
import json
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from codetalk import console, graph, graph_thread, review
from codetalk.cache import Cache


def _c(sha, day, files, subject="s", body=""):
    return {"sha": sha, "date": datetime(2026, 6, day, tzinfo=timezone.utc),
            "subject": subject, "files": files, "body": body}


SHA1, SHA2, SHA3 = "a" * 40, "b" * 40, "c" * 40


class ThreadCase(unittest.TestCase):
    def test_trunk_keeps_every_commit_and_leaves_cover_three_kinds(self):
        commits = [
            _c(SHA1, 1, ["a.py"], body="Vibe-Decision: keep entries\n"
               "Vibe-Rejected: full clear\nVibe-Watch: empty cache"),
            _c(SHA2, 2, ["b.py"]),                      # no notes: still on the trunk
        ]
        data = graph_thread.thread(commits, Cache(":memory:"))
        self.assertEqual([n["id"] for n in data["trunk"]], ["aaaaaaa", "bbbbbbb"])
        self.assertEqual(data["trunk"][0]["sha"], SHA1)          # full identity survives
        self.assertEqual(data["trunk"][0]["files"], ["a.py"])
        leaves = {leaf["id"]: leaf for leaf in data["leaves"]}
        self.assertEqual(leaves["aaaaaaa:d0"]["text"], "keep entries")
        self.assertEqual(leaves["aaaaaaa:r0"]["kind"], "rejected")
        self.assertEqual(leaves["aaaaaaa:w0"]["kind"], "watch")
        self.assertTrue(all(leaf["source"] == "breadcrumb" for leaf in leaves.values()))
        self.assertFalse([leaf for leaf in data["leaves"] if leaf["commit"] == "bbbbbbb"])

    def test_cached_narrative_is_the_fallback_and_is_labelled(self):
        cache = Cache(":memory:")
        cache.put_narrative(SHA3, "P", "m", {"decisions": ["chosen"], "rejected": ["dropped"],
                                             "risks": ["later"]})
        data = graph_thread.thread([_c(SHA3, 3, [])], cache)
        self.assertEqual({leaf["kind"] for leaf in data["leaves"]},
                         {"decision", "rejected", "watch"})
        self.assertEqual({leaf["source"] for leaf in data["leaves"]}, {"narrative"})

    def test_note_text_is_redacted(self):
        body = 'Vibe-Decision: use api_key="sk-abcdefghijklmnopqrstuvwxyz0123456789"'
        data = graph_thread.thread([_c(SHA1, 1, [], body=body)], Cache(":memory:"))
        self.assertIn("[REDACTED]", data["leaves"][0]["text"])


class AnnotationCase(unittest.TestCase):
    def test_clean_accepts_known_fields_and_rejects_the_rest(self):
        clean, err = graph_thread.clean_annotation(
            {"note": "why", "tags": [" risky "], "pin": {"x": 1.26, "y": -3}, "hidden": True})
        self.assertIsNone(err)
        self.assertEqual(clean, {"note": "why", "tags": ["risky"],
                                 "pin": {"x": 1.3, "y": -3}, "hidden": True})
        for bad in ({"other": 1}, {"note": "x" * 2001}, {"tags": ["a"] * 9},
                    {"pin": {"x": float("inf"), "y": 0}}, {"pin": {"x": 1}},
                    {"hidden": "yes"}, {"tags": "a"}, "text"):
            self.assertIsNotNone(graph_thread.clean_annotation(bad)[1], bad)

    def test_plan_fields_are_validated(self):
        clean, err = graph_thread.clean_annotation(
            {"text": "split the parser", "dir": "parser", "done": "abcdef1"})
        self.assertIsNone(err)
        self.assertEqual(clean, {"text": "split the parser", "dir": "parser", "done": "abcdef1"})
        for bad in ({"done": "xyz"}, {"text": "x" * 301}, {"dir": "d" * 25}, {"done": 7}):
            self.assertIsNotNone(graph_thread.clean_annotation(bad)[1], bad)

    def test_note_is_redacted_before_it_is_stored(self):
        clean, _ = graph_thread.clean_annotation(
            {"note": 'token="sk-abcdefghijklmnopqrstuvwxyz0123456789"'})
        self.assertIn("[REDACTED]", clean["note"])

    def test_cache_round_trip_is_scoped_to_one_project(self):
        cache = Cache(":memory:")
        cache.put_graph_annotation("/p/one", "aaaaaaa", {"note": "n"})
        self.assertEqual(cache.get_graph_annotations("/p/one"), {"aaaaaaa": {"note": "n"}})
        self.assertEqual(cache.get_graph_annotations("/p/two"), {})
        cache.delete_graph_annotation("/p/one", "aaaaaaa")
        self.assertEqual(cache.get_graph_annotations("/p/one"), {})


class GraphServeCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / "synthetic-project"
        self.project.mkdir()
        self.db = self.root / "cache.db"
        for args in [("init", "-q"), ("config", "user.email", "demo@example.invalid"),
                     ("config", "user.name", "Synthetic Demo")]:
            self.git(*args)
        (self.project / "cache.py").write_text("x = 1\n")
        self.git("add", "--", "cache.py")
        self.git("commit", "-qm", "Keep cache entries\n\nVibe-Decision: Keep unrelated entries.\n"
                 "Vibe-Rejected: Full clear repeats work.")
        self.sha7 = self.git("rev-parse", "HEAD").strip()[:7]
        self.addCleanup(patch.stopall)
        patch.object(console, "CACHE_DB_PATH", self.db).start()
        patch.object(review, "CACHE_DB_PATH", self.db).start()
        patch.object(graph, "CACHE_DB_PATH", self.db).start()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.project), *args], check=True,
                              capture_output=True, text=True).stdout

    def start(self):
        from codetalk.reading_server import create_reading_server
        self.server = create_reading_server(self.project, cache_path=self.db)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()

        def stop():
            self.server.shutdown()
            thread.join(3)
            self.server.server_close()
        self.addCleanup(stop)
        self.origin = "http://127.0.0.1:" + str(self.server.server_port)

    def request(self, path, payload=None, origin=None):
        headers, data = {}, None
        if payload is not None:
            data = json.dumps(payload).encode()
            headers = {"Content-Type": "application/json", "Origin": origin or self.origin}
        req = urllib.request.Request(self.origin + path, data=data, headers=headers)
        try:
            response = urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            body = response.read().decode()
            is_json = "json" in response.headers.get("Content-Type", "")
            return response.status, (json.loads(body) if is_json else body)

    def test_static_export_is_read_only_and_carries_the_thread(self):
        page, err = graph.render_graph_html(self.project, self.db)
        self.assertIsNone(err)
        self.assertIn("var SERVE = false;", page)
        self.assertIn('"trunk"', page)
        self.assertIn("Keep unrelated entries.", page)

    def test_agent_json_stays_nodes_and_edges_only(self):
        with Cache(self.db) as cache:
            payload, err = graph.build_graph_json(self.project, cache)
        self.assertIsNone(err)
        self.assertEqual(set(json.loads(payload)), {"nodes", "edges"})

    def test_served_graph_saves_annotation_and_bakes_it_into_the_next_page(self):
        self.start()
        status, page = self.request("/graph")
        self.assertEqual(status, 200)
        self.assertIn("var SERVE = true;", page)
        status, body = self.request("/graph/annotation",
                                    {"key": self.sha7, "data": {"note": "remember this"}})
        self.assertEqual((status, body["annotations"]), (200, {self.sha7: {"note": "remember this"}}))
        self.assertIn("remember this", self.request("/graph")[1])
        link = "link:%s:d0>%s" % (self.sha7, self.sha7)
        self.assertEqual(self.request("/graph/annotation", {"key": link, "data": {}})[0], 200)
        status, body = self.request("/graph/annotation", {"key": self.sha7, "data": None})
        self.assertEqual((status, list(body["annotations"])), (200, [link]))

    def test_plan_is_stored_per_commit_and_page_carries_read_state_and_head(self):
        self.start()
        key = "plan:%s:k1" % self.sha7
        status, body = self.request("/graph/annotation",
                                    {"key": key, "data": {"text": "next step", "dir": "ui"}})
        self.assertEqual((status, body["annotations"][key]["dir"]), (200, "ui"))
        self.assertEqual(self.request("/graph/annotation", {
            "key": key, "data": {"text": "next step", "done": "0000000"}})[0], 404)
        self.assertEqual(self.request("/graph/annotation", {
            "key": "plan:0000000:k1", "data": {"text": "x"}})[0], 404)
        self.assertEqual(self.request("/reviewed", {"sha": self.sha7})[0], 200)
        page = self.request("/graph")[1]
        self.assertIn('"reviewed": ["%s"]' % self.sha7, page)
        self.assertIn('"head": "%s"' % self.sha7, page)

    def test_annotation_write_refuses_bad_origin_unknown_commit_and_bad_shape(self):
        self.start()
        good = {"key": self.sha7, "data": {"note": "n"}}
        self.assertEqual(self.request("/graph/annotation", good,
                                      origin="https://external.invalid")[0], 403)
        self.assertEqual(self.request("/graph/annotation",
                                      {"key": "0000000", "data": {"note": "n"}})[0], 404)
        self.assertEqual(self.request("/graph/annotation",
                                      {"key": "not-a-node", "data": {}})[0], 400)
        self.assertEqual(self.request("/graph/annotation",
                                      {"key": self.sha7, "data": {"evil": 1}})[0], 400)
        with Cache(self.db) as cache:
            self.assertEqual(cache.get_graph_annotations(str(self.project)), {})


if __name__ == "__main__":
    unittest.main()
