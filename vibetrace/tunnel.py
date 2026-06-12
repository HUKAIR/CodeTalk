"""Time tunnel, the project's memory as a flyable 3D corridor (M1 v3).

After FranzLy/TimeChannel: commits ring an endless tunnel — the entrance
is now, deeper is older; you scroll through your own history with
inertia, starfield and date waypoints. TimeChannel uses Three.js; this
stays inside vibetrace red lines (single file, zero deps, offline) by
doing the tunnel with native CSS 3D transforms + a Canvas 2D starfield.
Visual language follows careers.kimi.com: pure black/white pixel terminal,
Fusion Pixel font (CDN with font-display swap — degrades to system mono
offline), chunky low-res canvases, hard borders, quantized fades.

Markup/JS live in tunnel.html next to this module; this file only
assembles data and substitutes it in.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from string import Template

from .cache import Cache
from .config import CACHE_DB_PATH, load_config
from .gitlog import collect_commits

EXCERPT = 220


def _payload(commits, narratives, today):
    """Tunnel rings, newest first (entrance = now, deep = origin)."""
    items = []
    for commit in reversed(commits):
        narrative = narratives.get(commit["sha"]) or {}
        local_date = commit["date"].astimezone()
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
        })
    return items


def render_tunnel(project_path):
    """Build the tunnel HTML; returns (output_path, error_or_None)."""
    cfg = load_config()
    project_path = Path(project_path).resolve()
    # whole history: the tunnel is the project's full memory, diffs unneeded
    # (note: git mis-parses --since=1970-01-01 as empty; relative date works)
    commits, err = collect_commits(project_path, "30 years ago", 50)
    if err:
        return None, err
    if not commits:
        return None, "没有任何 commit,隧道无从谈起。"
    cache = Cache(CACHE_DB_PATH)
    narratives = {c["sha"]: cache.get_narrative(c["sha"]) for c in commits}
    cache.close()

    today = datetime.now(timezone.utc).astimezone().date()
    data = _payload(commits, narratives, today)
    template = Template((Path(__file__).parent / "tunnel.html")
                        .read_text(encoding="utf-8"))
    html_text = template.substitute(
        project=project_path.name,
        # "</" must not appear inside a <script> block
        data=json.dumps(data, ensure_ascii=False).replace("</", "<\\/"),
        generated=f"{today:%Y.%m.%d}",
    )
    vault = Path(cfg["vault_path"]).expanduser()
    vault.mkdir(parents=True, exist_ok=True)
    out = vault / f"{project_path.name}-tunnel.html"
    out.write_text(html_text, encoding="utf-8")
    return out, None
