"""Decision review cards exposed through the review command."""
import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from codetalk import cli
from codetalk import review as review_mod
from codetalk.cache import Cache


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


class TestDecisionReviewCards(unittest.TestCase):
    def setUp(self):
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)
        _git(["init", "-q"], self.project)
        _git(["config", "user.email", "review@example.test"], self.project)
        _git(["config", "user.name", "Review Test"], self.project)
        source = Path(self.project) / "client.py"
        source.write_text("def fetch():\n    return 'stdlib'\n", encoding="utf-8")
        _git(["add", "."], self.project)
        _git([
            "commit", "-q", "-m", "feat: add local client sk-1234567890abcdef\n\n"
            "Vibe-Decision: Keep the standard-library HTTP client\n"
            "Vibe-Rejected: Add a third-party HTTP dependency because the core must stay dependency-free",
        ], self.project)
        self.sha = _git(["rev-parse", "HEAD"], self.project)
        source.write_text("def fetch():\n    return 'new client'\n", encoding="utf-8")
        self.cache = str(Path(self.project) / "cache.db")

    def test_local_diff_builds_separated_unresolved_card(self):
        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.cache):
            cards, err, meta = review_mod.build_review_cards(self.project)

        self.assertIsNone(err)
        self.assertEqual(meta["total_hunks"], 1)
        self.assertEqual(len(cards), 1)
        card = cards[0]
        self.assertEqual(card["kind"], "potential_conflict")
        self.assertEqual({k: card["change"][k] for k in ("file", "start", "end")}, {
            "file": "client.py", "start": 1, "end": 2,
        })
        self.assertIn("return 'new client'", card["change"]["diff"])
        self.assertEqual(card["provenance"]["precision"], "line")
        self.assertEqual(card["association"]["semantic_match"], "not_evaluated")
        primary = card["evidence"]["primary"]
        notes = primary["decision_notes"]
        self.assertIn("third-party HTTP dependency", notes["rejected"][0])
        self.assertIn("standard-library HTTP client", notes["chosen"][0])
        self.assertEqual(primary["sha"], self.sha)
        self.assertEqual(card["evidence"]["supporting"], [])
        self.assertNotIn("sk-1234567890abcdef", json.dumps(card))
        self.assertIsNone(card["interpretation"])
        self.assertEqual(card["judgment"], {"status": "unresolved"})

    def test_cli_json_emits_same_card_contract(self):
        stdout = io.StringIO()
        run = subprocess.run

        def local_git_only(args, *pargs, **kwargs):
            self.assertEqual(args[0], "git")
            return run(args, *pargs, **kwargs)

        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.cache), \
             mock.patch("subprocess.run", side_effect=local_git_only), \
             mock.patch("urllib.request.urlopen",
                        side_effect=AssertionError("review attempted network egress")), \
             contextlib.redirect_stdout(stdout):
            rc = cli.main(["review", "--project", self.project, "--json"])

        self.assertEqual(rc, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["cards"][0]["kind"], "potential_conflict")
        self.assertEqual(
            payload["cards"][0]["evidence"]["primary"]["sha"], self.sha)
        self.assertEqual(payload["cards"][0]["judgment"]["status"], "unresolved")
        self.assertEqual(payload["meta"]["total_hunks"], 1)

    def test_generated_narrative_is_not_presented_as_decision_evidence(self):
        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.cache):
            before, err, _meta = review_mod.build_review_cards(self.project)
        self.assertIsNone(err)

        cache = Cache(self.cache)
        cache.put_narrative(self.sha, self.project, "fake-model", {
            "why": "Generated explanation for readability",
            "decisions": ["Generated choice"],
            "rejected": ["Generated rejection"],
        })
        cache.close()

        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.cache):
            cards, err, _meta = review_mod.build_review_cards(self.project)

        self.assertIsNone(err)
        card = cards[0]
        self.assertEqual(card["id"], before[0]["id"])
        notes = card["evidence"]["primary"]["decision_notes"]
        self.assertEqual(notes["chosen"], [
            "Keep the standard-library HTTP client",
        ])
        self.assertEqual(notes["rejected"], [
            "Add a third-party HTTP dependency because the core must stay dependency-free",
        ])
        self.assertEqual(card["interpretation"], {
            "label": "generated_interpretation",
            "authoritative": False,
            "summary": "Generated explanation for readability",
            "decisions": ["Generated choice"],
            "rejected": ["Generated rejection"],
        })

    def test_generated_only_context_is_visible_but_never_labeled_evidence(self):
        source = Path(self.project) / "generated.py"
        source.write_text("value = 1\n", encoding="utf-8")
        _git(["add", "generated.py"], self.project)
        _git(["commit", "-q", "-m", "feat: add generated context"], self.project)
        sha = _git(["rev-parse", "HEAD"], self.project)
        source.write_text("value = 2\n", encoding="utf-8")
        cache = Cache(self.cache)
        cache.put_narrative(sha, self.project, "fake-model", {
            "why": "Generated explanation only",
            "decisions": ["Generated choice only"],
            "rejected": ["Generated rejection only"],
        })
        cache.close()

        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.cache):
            cards, err, _meta = review_mod.build_review_cards(self.project)

        self.assertIsNone(err)
        card = next(card for card in cards
                    if card["change"]["file"] == "generated.py")
        self.assertEqual(card["kind"], "decision_context")
        self.assertEqual(card["evidence"]["primary"]["decision_notes"], {
            "chosen": [], "rejected": [],
        })
        self.assertEqual(card["interpretation"]["decisions"], [
            "Generated choice only",
        ])
        self.assertIn("非证据", card["provenance"]["label"])

    def test_supporting_history_is_retained_without_displacing_rejected_path(self):
        _git(["add", "client.py"], self.project)
        _git(["commit", "-q", "-m", "refactor: keep later context\n\n"
              "Vibe-Decision: Preserve the public fetch function"], self.project)
        later_sha = _git(["rev-parse", "HEAD"], self.project)
        source = Path(self.project) / "client.py"
        source.write_text("def fetch():\n    return 'latest client'\n", encoding="utf-8")

        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.cache):
            cards, err, _meta = review_mod.build_review_cards(self.project)

        self.assertIsNone(err)
        evidence = cards[0]["evidence"]
        self.assertEqual(evidence["primary"]["sha"], self.sha)
        self.assertIn(later_sha, [item["sha"] for item in evidence["supporting"]])

    def test_line_level_rejected_path_ranks_before_file_fallback(self):
        diff = ("--- a/client.py\n+++ b/client.py\n"
                "@@ -999 +999 @@\n-old\n+new\n"
                "@@ -1,2 +1,2 @@\n def fetch():\n-    return 'stdlib'\n"
                "+    return 'new client'\n")
        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.cache):
            cards, err, _meta = review_mod.build_review_cards(self.project, diff)

        self.assertIsNone(err)
        self.assertEqual([card["provenance"]["precision"] for card in cards],
                         ["line", "file"])
        self.assertTrue(all(card["kind"] == "potential_conflict" for card in cards))

    def test_malformed_history_degrades_to_no_evidence(self):
        malformed = [{"sha": self.sha, "rejected": 7}]
        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.cache), \
             mock.patch.object(review_mod, "collect_graded",
                               return_value=(malformed, "line")):
            cards, err, _meta = review_mod.build_review_cards(self.project)

        self.assertIsNone(err)
        self.assertEqual(cards[0]["kind"], "no_evidence")
        self.assertEqual(cards[0]["provenance"]["precision"], "none")
        self.assertIn("no recoverable Git history",
                      cards[0]["association"]["reason"])

    def test_terminal_renders_the_same_stable_card_and_human_boundary(self):
        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.cache):
            cards, err, meta = review_mod.build_review_cards(self.project)
            output = review_mod.render_review_cards(cards, meta)

        self.assertIsNone(err)
        self.assertIn(cards[0]["id"], output)
        self.assertIn("需要人工判断", output)


if __name__ == "__main__":
    unittest.main()
