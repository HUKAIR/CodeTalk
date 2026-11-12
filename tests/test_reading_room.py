"""Reading-room UI uses real Git records and project-scoped local writes."""
import json
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from codetalk import console, review
from codetalk.cache import Cache


class ReadingRoomCase(unittest.TestCase):
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
        (self.project / "cache.py").write_text("def clear(cache, key):\n    cache.pop(key, None)\n")
        self.git("add", "--", "cache.py")
        self.git("commit", "-qm", "Keep cache entries\n\nVibe-Decision: Keep unrelated entries.\n"
                 "Vibe-Rejected: Full clear repeats work.\nVibe-Watch: Check empty cache.",
                 "--", "cache.py")
        self.sha = self.git("rev-parse", "HEAD").strip()
        (self.project / "cache.py").write_text("def clear(cache, key):\n    cache.clear()\n")
        with Cache(self.db) as cache:
            cache.seal_capsule(str(self.project), self.sha, 0, "Check empty cache",
                               "2020-01-01", "2020-01-02")
            cache.open_due_capsules(str(self.project), "2026-11-10")
        self.addCleanup(patch.stopall)
        patch.object(console, "CACHE_DB_PATH", self.db).start()
        patch.object(review, "CACHE_DB_PATH", self.db).start()
        patch.object(console.sessions, "scan_sessions", return_value=([], None)).start()
        patch.object(console.recap, "console_payload", return_value=None).start()

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
        headers = {}
        data = None
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
            return response.status, (json.loads(body) if "json" in response.headers.get("Content-Type", "") else body)

    def test_unborn_head_keeps_console_available(self):
        self.project = self.root / "new-project"
        self.project.mkdir()
        self.git("init", "-q")
        self.start()
        code, page = self.request("/")
        self.assertEqual(code, 200)
        self.assertIn('"timeline": []', page)
        code, result = self.request("/review")
        self.assertEqual(code, 400)
        self.assertEqual(result, {"error": "review unavailable"})

    def test_uncached_timeline_keeps_original_decisions_separate(self):
        with Cache(self.db) as cache:
            data, error = console._assemble(self.project, cache)
        self.assertIsNone(error)
        row = data["timeline"][0]
        self.assertEqual(row["full_sha"], self.sha)
        self.assertEqual(row["source"]["chosen"], ["Keep unrelated entries."])
        self.assertEqual(row["source"]["rejected"], ["Full clear repeats work."])
        self.assertIn("Vibe-Watch", row["source"]["body"])
        self.assertEqual(row["decisions"], [])  # no invented cached interpretation

    def test_core_server_search_commit_and_review_are_reachable(self):
        self.start()
        code, page = self.request("/")
        self.assertEqual(code, 200)
        self.assertIn("reading-room", page)
        code, result = self.request("/api/search?q=cache")
        self.assertEqual(code, 200)
        self.assertTrue(result["results"])
        code, commit = self.request("/api/commit/" + self.sha)
        self.assertEqual(code, 200)
        self.assertIn("Vibe-Rejected", commit["body"])
        self.assertIn("cache.pop", commit["diff"])
        self.assertEqual(self.request("/api/commit/--help")[0], 400)
        self.assertEqual(self.request("/api/commit/" + "0" * 40)[0], 404)
        code, page = self.request("/review")
        self.assertEqual(code, 200)
        self.assertIn("Full clear repeats work", page)

    def test_real_writes_survive_reload_and_reject_cross_origin(self):
        self.start()
        cap = {"capsule_id": self.sha + ":0", "outcome": "已解决"}
        self.assertEqual(self.request("/capsule", cap, "https://external.invalid")[0], 403)
        self.assertEqual(self.request("/capsule", cap)[0], 200)
        self.assertEqual(self.request("/reviewed", {"sha": self.sha})[0], 200)
        cards, err, _ = review.build_review_cards(self.project)
        self.assertIsNone(err)
        payload = {"card_id": cards[0]["id"], "status": "intentional_exception",
                   "action_changed": None, "elapsed_seconds": 2}
        self.assertEqual(self.request("/judgment", payload)[0], 200)
        code, feedback = self.request("/feedback/preview", {"card_id": cards[0]["id"]})
        self.assertEqual(code, 200)
        self.assertIn("feedback", feedback)
        self.assertEqual(self.request("/feedback/export", {"card_id": cards[0]["id"]})[0], 200)
        with Cache(self.db) as cache:
            self.assertEqual(cache.all_capsules(str(self.project))[0]["outcome"], "已解决")
            self.assertIn(self.sha[:7], cache.reviewed_shas(str(self.project)))
            self.assertEqual(cache.get_review_judgments(str(self.project))[cards[0]["id"]]["status"], "intentional_exception")
        self.assertIn('"intentional_exception"', self.request("/review")[1])
        self.assertEqual(self.request("/capsule", {**cap, "capsule_id": "missing"})[0], 404)

    def test_other_project_cannot_be_selected_on_core_server(self):
        self.start()
        self.assertEqual(self.request("/reviewed", {"sha": self.sha, "project": {"bad": "type"}})[0], 400)
        self.assertEqual(self.request("/api/search?q=cache&project=/other")[0], 403)
        self.assertEqual(self.request("/reviewed", {"sha": self.sha, "project": "/other"})[0], 403)

    def test_optional_web_scopes_search_writes_and_review_to_selected_project(self):
        try:
            from fastapi.testclient import TestClient
            from codetalk import web
        except ImportError:
            self.skipTest("requires web/test extras")
        other = self.root / "other"
        other.mkdir()
        with patch.object(web, "_DEFAULT_PROJECT", str(other)), patch.object(web, "CACHE_DB_PATH", self.db):
            client = TestClient(web.app, base_url="http://127.0.0.1")
            selected = {"project": str(self.project)}
            self.assertEqual(client.get("/api/search", params={**selected, "q": "cache"}).status_code, 200)
            self.assertEqual(client.post("/capsule", json={**selected, "capsule_id": self.sha + ":0", "outcome": "已解决"}).status_code, 200)
            self.assertEqual(client.post("/reviewed", json={**selected, "sha": self.sha}).status_code, 200)
            self.assertEqual(client.post("/reviewed", json={"sha": self.sha}).status_code, 404)
            cards, error, _ = review.build_review_cards(self.project)
            self.assertIsNone(error)
            for status in ("confirmed_conflict", "intentional_exception", "unrelated", "insufficient_evidence"):
                result = client.post("/judgment", params=selected, json={"card_id": cards[0]["id"], "status": status,
                                     "action_changed": True if status == "confirmed_conflict" else None, "elapsed_seconds": 2})
                self.assertEqual(result.status_code, 200, result.text)
                self.assertIn(status, client.get("/review", params=selected).text)
            self.assertEqual(client.post("/judgment", params=selected, json={"card_id": cards[0]["id"], "status": "unrelated"},
                                        headers={"Origin": "https://external.invalid"}).status_code, 403)
            self.assertEqual(client.post("/feedback/preview", params=selected, json={"card_id": cards[0]["id"]}).status_code, 200)
            self.assertEqual(client.post("/feedback/export", params=selected, json={"card_id": cards[0]["id"]}).status_code, 200)
            with patch.object(web, "_llm", return_value=None), patch.object(web.chat, "answer", return_value={"answer": "local"}) as answer:
                self.assertEqual(client.post("/api/chat", json={**selected, "question": "Why?"}).status_code, 200)
                self.assertEqual(answer.call_args.args[2], self.project)
        with Cache(self.db) as cache:
            self.assertIn(self.sha[:7], cache.reviewed_shas(str(self.project)))
            self.assertFalse(cache.reviewed_shas(str(other)))


if __name__ == "__main__":
    unittest.main()
