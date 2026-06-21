"""Time axis (时光轴): the project's history as a readable linear timeline.

Commits run top-down, newest-first, on a vertical spine grouped by day;
each row expands to its narrative (what/why/decisions/risks) + capsule
status. Plain system fonts, no 3D/canvas/pixel — readability over spectacle
(decision-impact *relationships* live in `graph`; this is pure linear time).
Stays inside vibetrace red lines: single file, zero deps, offline.

Markup/JS live in tunnel.html next to this module; this file only
assembles data and substitutes it in.

Two run modes (Issue #4 — single cache.db source of truth):
  render_tunnel(): write static HTML (file://); capsule answers read-only.
  serve_tunnel():  127.0.0.1 http.server; the page POSTs answers back to
                   cache.db live (/capsule, /reviewed). cache.db is the only
                   capsule store — the page keeps no answers in localStorage.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from string import Template

from .cache import Cache
from .config import CACHE_DB_PATH, load_config
from .gitlog import collect_commits

EXCERPT = 220


def _payload(commits, narratives, capsules_by_sha, today):
    """Tunnel rings, newest first (entrance = now, deep = origin)."""
    items = []
    for commit in reversed(commits):
        narrative = narratives.get(commit["sha"]) or {}
        local_date = commit["date"].astimezone()
        caps = capsules_by_sha.get(commit["sha"], [])
        items.append({
            "sha": commit["sha"][:7],
            "date": f"{local_date:%Y-%m-%d %H:%M}",
            "day": f"{local_date:%Y-%m-%d}",
            "days_ago": (today - local_date.date()).days,
            "subject": commit["subject"],
            "what": (narrative.get("what") or "")[:EXCERPT],
            "why": (narrative.get("why") or "")[:EXCERPT],
            "decisions": (narrative.get("decisions") or [])[:6],
            "risks": ((narrative.get("risks") or [])
                      + (narrative.get("open_loops") or []))[:5],
            # 真实胶囊(cache 单一真相源):带 capsule_id + 已答 outcome
            "capsules": [{"id": c["capsule_id"], "risk": c["risk"],
                          "outcome": c["outcome"], "opened": c["opened"]}
                         for c in caps],
        })
    return items


def _build_html(project_path, serve):
    """Assemble the tunnel HTML string. Returns (html, project_name, error)."""
    project_path = Path(project_path).resolve()
    # whole history: the tunnel is the project's full memory, diffs unneeded
    # (note: git mis-parses --since=1970-01-01 as empty; relative date works)
    commits, err = collect_commits(project_path, "30 years ago", 50)
    if err:
        return None, project_path.name, err
    if not commits:
        return None, project_path.name, "没有任何 commit,隧道无从谈起。"
    cache = Cache(CACHE_DB_PATH)
    cache.rekey_project(project_path.name, str(project_path))  # 迁移旧 basename 键(幂等)
    narratives = {c["sha"]: cache.get_narrative(c["sha"]) for c in commits}
    capsules_by_sha = {}
    for cap in cache.all_capsules(str(project_path)):
        capsules_by_sha.setdefault(cap["sha"], []).append(cap)
    cache.close()

    today = datetime.now(timezone.utc).astimezone().date()
    data = _payload(commits, narratives, capsules_by_sha, today)
    from . import report  # 零 LLM 命令:记一行用量(commit 数 / serve 模式),写失败不影响主流程
    report.append_usage({"command": "tunnel", "project": str(project_path),
                         "commits": len(commits), "serve": serve})
    template = Template((Path(__file__).parent / "tunnel.html")
                        .read_text(encoding="utf-8"))
    html_text = template.substitute(
        project=project_path.name,
        # "</" must not appear inside a <script> block
        data=json.dumps(data, ensure_ascii=False).replace("</", "<\\/"),
        generated=f"{today:%Y.%m.%d}",
        serve="true" if serve else "false",
    )
    return html_text, project_path.name, None


def render_tunnel(project_path):
    """Write the static tunnel HTML (file:// mode). Returns (path, error)."""
    cfg = load_config()
    html_text, project, err = _build_html(project_path, serve=False)
    if err:
        return None, err
    vault = Path(cfg["vault_path"]).expanduser()
    vault.mkdir(parents=True, exist_ok=True)
    out = vault / f"{project}-tunnel.html"
    out.write_text(html_text, encoding="utf-8")
    return out, None


def serve_tunnel(project_path, open_browser=True):
    """Serve the tunnel on 127.0.0.1 so answers write back to cache live.
    Returns error_or_None (blocks until Ctrl+C)。服务器逻辑复用 webserve.serve_html。"""
    html_text, project, err = _build_html(project_path, serve=True)
    if err:
        return err
    from .webserve import serve_html
    return serve_html(html_text, project_path, open_browser)
