"""Collect commits (message + stat + truncated diff) via git subprocess."""
import logging
import subprocess
from datetime import datetime

log = logging.getLogger("vibetrace")

FIELD_SEP = "\x1f"
RECORD_SEP = "\x1e"
CHARS_PER_TOKEN = 4  # rough budget heuristic; exact counting needs no extra dep


def _git(args, cwd):
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                         text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:200])
    return out.stdout


def collect_commits(project_path, since, diff_token_budget):
    """Return (commits oldest-first, error_message_or_None)."""
    fmt = FIELD_SEP.join(["%H", "%aI", "%an", "%s", "%b"]) + RECORD_SEP
    try:
        raw = _git(["log", f"--since={since}", f"--pretty=format:{fmt}"],
                   project_path)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        return [], f"git log 失败:{exc}"

    commits = []
    for rec in raw.split(RECORD_SEP):
        rec = rec.strip("\n")
        if not rec:
            continue
        parts = rec.split(FIELD_SEP)
        if len(parts) < 4:
            log.warning("跳过无法解析的 git log 记录")
            continue
        sha, date_iso, author, subject = parts[0], parts[1], parts[2], parts[3]
        body = parts[4].strip() if len(parts) > 4 else ""
        try:
            date = datetime.fromisoformat(date_iso)
        except ValueError:
            log.warning("commit %s 日期无法解析,已跳过", sha[:8])
            continue
        commits.append({
            "sha": sha, "author": author, "subject": subject, "body": body,
            "date": date, "stat": "", "diff_excerpt": "", "files": [],
        })

    char_budget = diff_token_budget * CHARS_PER_TOKEN
    for commit in commits:
        sha = commit["sha"]
        try:
            commit["files"] = [f for f in _git(
                ["show", "--name-only", "--pretty=format:", sha],
                project_path).splitlines() if f]
            commit["stat"] = _git(
                ["show", "--stat", "--pretty=format:", sha],
                project_path).strip()
            diff = _git(["show", "--patch", "--no-color",
                         "--pretty=format:", sha], project_path)
            if len(diff) > char_budget:
                diff = diff[:char_budget] + "\n... [diff 已截断]"
            commit["diff_excerpt"] = diff.strip()
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            log.warning("commit %s 详情获取失败:%s", sha[:8], exc)

    commits.reverse()  # git log is newest-first; report reads oldest-first
    return commits, None
