"""Shared local evidence operations for the stdlib and optional web workspaces."""
import re
from pathlib import Path

from . import gitlog, graph_thread, search
from .cache import Cache
from .config import redact_data
from .report import _OUTCOMES


def commit_record(project, sha):
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", sha):
        return {"error": "bad sha"}, 400
    date, subject = gitlog.commit_meta(project, sha)
    body = gitlog.commit_body(project, sha)
    diff = gitlog.commit_diff(project, sha, char_budget=8000)
    if not subject and not diff:
        return {"error": "commit not found"}, 404
    return redact_data({"sha": sha, "date": date, "subject": subject,
                        "body": body, "diff": diff}), 200


def search_records(project, query, cache_path):
    """Keep the existing text API and add typed results without parsing prose."""
    with Cache(cache_path) as cache:
        originals, noted = search.collect_breadcrumb_hits(project, query)
        cached = search.collect_topic_hits(cache, project, query)
    results = [{"sha": hit["sha"], "kind": "source", "title": hit["subject"],
                "date": hit["date"], "text": search.render_breadcrumb_hit(hit)}
               for hit in originals]
    results += [{"sha": hit["sha"], "kind": "conversation" if hit["kind"] == "conversation" else "interpretation",
                 "title": hit["sha"][:12], "date": "", "text": search.render_hit(hit)}
                for hit in cached]
    text = "\n\n".join(row["text"] for row in results) if results else search._no_hit(noted)
    return redact_data({"text": text, "results": results})


def write_reading_record(project, path, payload, cache_path):
    if not isinstance(payload, dict):
        return {"error": "invalid payload"}, 400
    project = str(Path(project).resolve())
    with Cache(cache_path) as cache:
        if path == "/capsule":
            cap_id, outcome = payload.get("capsule_id"), payload.get("outcome")
            if outcome not in _OUTCOMES or not isinstance(cap_id, str):
                return {"error": "bad capsule outcome"}, 400
            if not any(c["capsule_id"] == cap_id for c in cache.all_capsules(project)):
                return {"error": "capsule not found in this project"}, 404
            cache.set_capsule_outcome(cap_id, outcome, project)
        elif path == "/reviewed":
            sha = payload.get("sha")
            if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{7,40}", sha):
                return {"error": "bad sha"}, 400
            if not gitlog.commit_meta(project, sha)[1]:
                return {"error": "commit not found"}, 404
            cache.mark_reviewed(project, sha[:7])  # debt.py uses the same seven-character key
        elif path == "/graph/annotation":
            return graph_thread.write_annotation(cache, project, payload)
        else:
            return {"error": "not found"}, 404
    return {"ok": True}, 200
