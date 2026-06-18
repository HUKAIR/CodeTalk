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

Two run modes (Issue #4 — single cache.db source of truth):
  render_tunnel(): write static HTML (file://); capsule answers read-only.
  serve_tunnel():  127.0.0.1 http.server; tunnel POSTs answers back to
                   cache.db live. cache.db is the only capsule store —
                   the tunnel no longer keeps answers in localStorage.
"""
import json
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from string import Template

from .cache import Cache
from .config import CACHE_DB_PATH, load_config
from .gitlog import collect_commits
from .report import _OUTCOMES

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
    Returns error_or_None (blocks until Ctrl+C)."""
    html_text, project, err = _build_html(project_path, serve=True)
    if err:
        return err
    pkey = str(Path(project_path).resolve())   # 胶囊/reviewed 回写键:绝对路径

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # 静默:不打 access log

        def do_GET(self):
            if self.path != "/":
                self.send_response(404); self.end_headers(); return
            body = html_text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length", 0))
                req = json.loads(self.rfile.read(n))
            except (ValueError, TypeError):
                self.send_response(400); self.end_headers(); return
            cache = Cache(CACHE_DB_PATH)
            try:
                if self.path == "/capsule":
                    cid, outcome = req["capsule_id"], req["outcome"]
                    # 安全:outcome 必须是已知枚举,防任意字符串写入缓存
                    if outcome not in _OUTCOMES:
                        self.send_response(400); self.end_headers(); return
                    cache.set_capsule_outcome(cid, outcome, pkey)
                elif self.path == "/reviewed":
                    # 还债信号:你回看了哪个 commit 叙事 → 喂理解债量化
                    sha = req["sha"]
                    if not isinstance(sha, str) or not sha:
                        self.send_response(400); self.end_headers(); return
                    cache.mark_reviewed(pkey, sha)
                else:
                    self.send_response(404); self.end_headers(); return
            except KeyError:
                self.send_response(400); self.end_headers(); return
            finally:
                cache.close()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

    # 绑 127.0.0.1(不 0.0.0.0):隧道服务只对本机开放,数据不出本机
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"隧道服务:{url}\n回答即时写回 cache.db。Ctrl+C 停止。")
    if open_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        srv.server_close()
    return None
