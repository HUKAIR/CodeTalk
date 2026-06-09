"""Soft session-commit alignment: time window + file-path overlap."""
from datetime import timedelta
from pathlib import Path

TIME_SLACK = timedelta(minutes=30)


def _relative_files(session, project_root):
    """Session file paths are absolute; map them into the repo, drop the rest."""
    rel = set()
    for path in session["files_written"]:
        try:
            rel.add(str(Path(path).relative_to(project_root)))
        except ValueError:
            continue
    return rel


def align(commits, sessions, project_path):
    """Attach matches=[{session, overlap, confidence}] to every commit.

    high = commit falls in the session's time window AND touches shared
    files; low = only one signal. Target is soft 80% accuracy by design.
    """
    project_root = Path(project_path).resolve()
    session_files = [(s, _relative_files(s, project_root)) for s in sessions]
    for commit in commits:
        matches = []
        for session, files in session_files:
            in_window = bool(
                session["start"] and session["end"]
                and session["start"] - TIME_SLACK <= commit["date"]
                <= session["end"] + TIME_SLACK)
            overlap = sorted(files & set(commit["files"]))
            if not in_window and not overlap:
                continue
            confidence = "high" if (in_window and overlap) else "low"
            matches.append({"session": session, "overlap": overlap,
                            "confidence": confidence})
        matches.sort(key=lambda m: (m["confidence"] != "high", -len(m["overlap"])))
        commit["matches"] = matches
    return commits
