"""Sanitized, explicit feedback exports from resolved review cards."""
import json
import unittest

from codetalk import __version__
from codetalk.review_feedback import build_feedback


def _sensitive_card():
    return {
        "id": "review-" + "a" * 12,
        "kind": "potential_conflict",
        "repository": "private-customer-repo",
        "change": {
            "file": "/Users/alice/Private/client.py", "start": 3, "end": 8,
            "diff": "@@ -3 +3 @@\n-password = 'do-not-export'\n+password = 'new'",
        },
        "provenance": {"precision": "line", "label": "Line-level provenance"},
        "evidence": {"primary": {
            "sha": "0123456789abcdef0123456789abcdef01234567",
            "author": "Alice <alice@private.example>",
            "subject": "Private customer decision",
            "decision_notes": {
                "chosen": ["Keep source private"],
                "rejected": ["Upload customer code"],
            },
            "sessions": [{"prompts": ["Conversation must stay private"]}],
            "tests": [{"path": "tests/test_private_client.py"}],
            "pull_requests": [{"number": 9182, "title": "Secret launch"}],
        }, "supporting": []},
        "interpretation": {"summary": "Generated private summary"},
    }


class TestFeedbackContract(unittest.TestCase):
    def test_export_is_an_allowlist_without_repository_or_source_identity(self):
        feedback = build_feedback(_sensitive_card(), {
            "status": "confirmed_conflict", "action_changed": True,
            "elapsed_seconds": 12.34, "verified_interception": False,
        })

        self.assertEqual(feedback, {
            "schema_version": 1,
            "product_version": __version__,
            "judgment": "confirmed_conflict",
            "action_changed": True,
            "evidence_type": "authored_rejected_path",
            "provenance_precision": "line",
            "elapsed_review_seconds": 12.3,
            "verified_interception": True,
        })
        exported = json.dumps(feedback)
        for sensitive in (
                "private-customer-repo", "/Users/alice", "client.py",
                "0123456789abcdef", "alice@private.example", "customer code",
                "Conversation must stay private", "Secret launch", "password"):
            self.assertNotIn(sensitive, exported)

    def test_approved_comment_is_redacted_and_length_bounded(self):
        secret = "sk-abcdefghijklmnop123456"
        feedback = build_feedback(
            _sensitive_card(), {
                "status": "unrelated", "action_changed": None,
                "elapsed_seconds": 2,
            }, approved_comment="Useful result " + secret + (" x" * 400))

        self.assertIn("[REDACTED]", feedback["approved_comment"])
        self.assertNotIn(secret, feedback["approved_comment"])
        self.assertLessEqual(len(feedback["approved_comment"]), 500)
        self.assertFalse(feedback["verified_interception"])

    def test_verified_interception_cannot_be_claimed_by_saved_metadata(self):
        feedback = build_feedback(_sensitive_card(), {
            "status": "intentional_exception", "action_changed": None,
            "elapsed_seconds": 4, "verified_interception": True,
        })
        self.assertFalse(feedback["verified_interception"])

    def test_unresolved_or_invalid_feedback_is_rejected(self):
        for judgment in ({}, {"status": "unresolved"}, {
                "status": "confirmed_conflict", "action_changed": None,
                "elapsed_seconds": 1,
        }):
            with self.subTest(judgment=judgment), self.assertRaises(ValueError):
                build_feedback(_sensitive_card(), judgment)

    def test_evidence_types_do_not_treat_generated_text_as_evidence(self):
        judgment = {"status": "unrelated", "action_changed": None,
                    "elapsed_seconds": 1}
        card = _sensitive_card()
        card["evidence"]["primary"]["decision_notes"]["rejected"] = []
        self.assertEqual(build_feedback(card, judgment)["evidence_type"],
                         "authored_decision")
        card["evidence"]["primary"]["decision_notes"]["chosen"] = []
        self.assertEqual(build_feedback(card, judgment)["evidence_type"],
                         "source_reference")
        card["evidence"]["primary"].update(
            sessions=[], tests=[], pull_requests=[])
        self.assertEqual(build_feedback(card, judgment)["evidence_type"],
                         "commit_history")
        card["evidence"] = None
        self.assertEqual(build_feedback(card, judgment)["evidence_type"], "none")

    def test_malformed_card_provenance_degrades_without_exposing_data(self):
        feedback = build_feedback(
            {"provenance": ["private path"], "evidence": {"primary": []}},
            {"status": "unrelated", "action_changed": None,
             "elapsed_seconds": 1})
        self.assertEqual(feedback["provenance_precision"], "none")
        self.assertEqual(feedback["evidence_type"], "none")
        empty = build_feedback(
            {"provenance": {}, "evidence": {"primary": {}}},
            {"status": "unrelated", "action_changed": None,
             "elapsed_seconds": 1})
        self.assertEqual(empty["evidence_type"], "none")


if __name__ == "__main__":
    unittest.main()
