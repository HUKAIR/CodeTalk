"""Privacy-safe feedback contract for locally resolved review cards."""
import math

from . import __version__
from .config import redact_secrets

JUDGMENT_OUTCOMES = {
    "confirmed_conflict", "intentional_exception", "unrelated",
    "insufficient_evidence",
}


def _evidence_type(card):
    evidence = card.get("evidence") if isinstance(card, dict) else None
    primary = evidence.get("primary") if isinstance(evidence, dict) else None
    if not isinstance(primary, dict):
        return "none"
    notes = primary.get("decision_notes")
    notes = notes if isinstance(notes, dict) else {}
    if isinstance(notes.get("rejected"), list) and notes["rejected"]:
        return "authored_rejected_path"
    if isinstance(notes.get("chosen"), list) and notes["chosen"]:
        return "authored_decision"
    if any(isinstance(primary.get(key), list) and primary[key]
           for key in ("sessions", "tests", "pull_requests")):
        return "source_reference"
    if any(isinstance(primary.get(key), str) and primary[key].strip()
           for key in ("sha", "date", "subject")):
        return "commit_history"
    return "none"


def build_feedback(card, judgment, approved_comment=None):
    """Build a small allowlisted export; never copy source-bearing card fields."""
    if not isinstance(judgment, dict):
        raise ValueError("invalid judgment")
    status = judgment.get("status")
    if status not in JUDGMENT_OUTCOMES:
        raise ValueError("unresolved judgment")
    changed = judgment.get("action_changed")
    if status == "confirmed_conflict":
        if not isinstance(changed, bool):
            raise ValueError("action change is required")
    elif changed is not None:
        raise ValueError("invalid action change")
    elapsed = judgment.get("elapsed_seconds")
    if (isinstance(elapsed, bool) or not isinstance(elapsed, (int, float))
            or not math.isfinite(elapsed) or elapsed < 0 or elapsed > 86400):
        raise ValueError("invalid elapsed time")
    provenance = card.get("provenance") if isinstance(card, dict) else None
    precision = (provenance.get("precision")
                 if isinstance(provenance, dict) else None)
    if precision not in {"line", "file", "none"}:
        precision = "none"
    feedback = {
        "schema_version": 1,
        "product_version": __version__,
        "judgment": status,
        "action_changed": changed,
        "evidence_type": _evidence_type(card),
        "provenance_precision": precision,
        "elapsed_review_seconds": round(float(elapsed), 1),
        "verified_interception": status == "confirmed_conflict" and changed,
    }
    if approved_comment is not None:
        if not isinstance(approved_comment, str):
            raise ValueError("invalid comment")
        comment = redact_secrets(approved_comment.strip())[:500]
        if comment:
            feedback["approved_comment"] = comment
    return feedback
