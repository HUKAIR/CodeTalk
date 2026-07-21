"""Loopback decision-card review and local judgment persistence."""
import contextlib
import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from codetalk import cli
from codetalk import review_web
from codetalk.cache import Cache
from codetalk.review_web import create_review_server, render_review_html


def _card(card_id="review-card-1"):
    return {
        "id": card_id,
        "kind": "potential_conflict",
        "change": {"file": "client.py", "start": 3, "end": 8,
                   "diff": "@@ -3,2 +3,2 @@\n-old\n+new"},
        "association": {"reason": "Line history matched; semantics were not evaluated.",
                        "semantic_match": "not_evaluated"},
        "provenance": {"precision": "line", "label": "Line-level provenance"},
        "evidence": {
            "primary": {
                "sha": "a" * 40, "date": "2026-07-21", "subject": "Prior choice",
                "decision_notes": {"chosen": ["Keep stdlib"],
                                   "rejected": ["Third-party client"]},
                "sessions": [{"source": "codex", "prompts": ["Keep it local"]}],
                "tests": [{"path": "tests/test_client.py", "names": ["test_local"]}],
                "pull_requests": [{"number": 12, "title": "Local client"}],
            },
            "supporting": [],
        },
        "interpretation": {
            "label": "generated_interpretation", "authoritative": False,
            "summary": "Generated summary " + ("long evidence " * 80),
            "decisions": [], "rejected": [],
        },
        "judgment": {"status": "unresolved"},
    }


class ReviewServerCase(unittest.TestCase):
    def setUp(self):
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)
        self.cache_path = str(Path(self.project) / "cache.db")
        self.cards = [_card(), _card("review-card-2")]
        self.server = create_review_server(
            self.project, self.cards, cache_path=self.cache_path)
        self.addCleanup(self.server.server_close)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop_server)
        host, port = self.server.server_address
        self.assertEqual(host, "127.0.0.1")
        self.origin = f"http://127.0.0.1:{port}"

    def _stop_server(self):
        self.server.shutdown()
        self.thread.join(timeout=2)

    def _post(self, payload, origin="same", host=None):
        headers = {"Content-Type": "application/json"}
        if origin is not None:
            headers["Origin"] = self.origin if origin == "same" else origin
        req = urllib.request.Request(
            self.origin + "/judgment",
            data=json.dumps(payload).encode(), method="POST",
            headers=headers)
        if host:
            req.add_header("Host", host)
        try:
            with urllib.request.urlopen(req, timeout=2) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_judgment_survives_reload_and_verified_rule_is_exact(self):
        status, body = self._post({
            "card_id": "review-card-1", "status": "confirmed_conflict",
            "action_changed": True, "elapsed_seconds": 14,
        })
        self.assertEqual(status, 200)
        self.assertTrue(body["judgment"]["verified_interception"])

        with urllib.request.urlopen(self.origin + "/", timeout=2) as response:
            html = response.read().decode()
        self.assertIn('"status": "confirmed_conflict"', html)
        self.assertIn('"action_changed": true', html)

        cache = Cache(self.cache_path)
        saved = cache.get_review_judgments(str(Path(self.project).resolve()))
        cache.close()
        self.assertTrue(saved["review-card-1"]["verified_interception"])

        status, body = self._post({
            "card_id": "review-card-2", "status": "intentional_exception",
            "action_changed": None, "elapsed_seconds": 3,
        })
        self.assertEqual(status, 200)
        self.assertFalse(body["judgment"]["verified_interception"])

    def test_invalid_id_cross_origin_and_invalid_action_change_are_rejected(self):
        base = {"status": "unrelated", "action_changed": None,
                "elapsed_seconds": 1}
        status, _ = self._post({"card_id": "missing", **base})
        self.assertEqual(status, 404)
        status, _ = self._post(
            {"card_id": "review-card-1", **base}, origin="https://evil.example")
        self.assertEqual(status, 403)
        status, _ = self._post(
            {"card_id": "review-card-1", **base},
            origin=self.origin.replace("127.0.0.1", "localhost"))
        self.assertEqual(status, 403)
        status, _ = self._post({"card_id": "review-card-1", **base}, origin=None)
        self.assertEqual(status, 403)
        status, _ = self._post({
            "card_id": "review-card-1", "status": "unrelated",
            "action_changed": True, "elapsed_seconds": 1,
        })
        self.assertEqual(status, 400)

    def test_all_four_outcomes_are_accepted_without_false_interceptions(self):
        for outcome in ("confirmed_conflict", "intentional_exception", "unrelated",
                        "insufficient_evidence"):
            status, body = self._post({
                "card_id": "review-card-1", "status": outcome,
                "action_changed": False if outcome == "confirmed_conflict" else None,
                "elapsed_seconds": 2,
            })
            self.assertEqual(status, 200, outcome)
            self.assertFalse(body["judgment"]["verified_interception"], outcome)

    def test_bad_host_is_rejected(self):
        status, _ = self._post({
            "card_id": "review-card-1", "status": "insufficient_evidence",
            "action_changed": None, "elapsed_seconds": 1,
        }, host="evil.example")
        self.assertEqual(status, 403)


class TestReviewPage(unittest.TestCase):
    def test_page_separates_sections_and_collapses_original_sources(self):
        html = render_review_html("Repo <private>", [_card()], {})
        self.assertIn('data-section="evidence"', html)
        self.assertIn('data-section="interpretation"', html)
        self.assertIn('data-section="provenance"', html)
        self.assertIn("<details", html)
        for label in ("Commit", "Diff", "Decision note", "Test", "Pull request",
                      "Session"):
            self.assertIn(label, html)
        self.assertNotIn("Repo <private>", html)
        self.assertIn("Repo &lt;private&gt;", html)

    def test_project_name_is_redacted_before_html_escaping(self):
        html = render_review_html('password="hunter2secretvalue"', [_card()], {})
        self.assertNotIn("hunter2secretvalue", html)
        self.assertIn("[REDACTED]", html)

    def test_page_has_mobile_long_text_and_reduced_motion_guards(self):
        html = render_review_html("Repo", [_card()], {})
        self.assertIn("overflow-wrap: anywhere", html)
        self.assertIn("@media (max-width: 720px)", html)
        self.assertIn("prefers-reduced-motion: reduce", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("http://", html)

    def test_all_four_judgment_outcomes_are_present(self):
        html = render_review_html("Repo", [_card()], {})
        for outcome in ("confirmed_conflict", "intentional_exception", "unrelated",
                        "insufficient_evidence"):
            self.assertIn('"' + outcome + '"', html)


class TestReviewServeCommand(unittest.TestCase):
    def test_cli_dispatches_review_serve_without_opening_browser(self):
        with mock.patch("codetalk.review_web.serve_review", return_value=None) as serve:
            rc = cli.main(["review", "--project", ".", "--serve", "--no-open"])
        self.assertEqual(rc, 0)
        serve.assert_called_once_with(".", None, open_browser=False)

    def test_serve_review_opens_the_loopback_url(self):
        class Server:
            server_address = ("127.0.0.1", 43123)

            def serve_forever(self):
                raise KeyboardInterrupt

            def server_close(self):
                pass

        with mock.patch("codetalk.review.build_review_cards",
                        return_value=([_card()], None, {})), \
             mock.patch.object(review_web, "create_review_server",
                               return_value=Server()), \
             mock.patch.object(review_web.webbrowser, "open") as open_browser, \
             contextlib.redirect_stdout(mock.Mock()):
            err = review_web.serve_review(".", open_browser=True)

        self.assertIsNone(err)
        open_browser.assert_called_once_with("http://127.0.0.1:43123/")


if __name__ == "__main__":
    unittest.main()
