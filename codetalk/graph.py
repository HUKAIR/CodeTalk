"""Decision-impact graph: which decision rippled into which later changes.

纯本地、零 LLM。节点=决策性 commit(Vibe-Decision 面包屑优先,否则叙事 decisions;
top-N=40 按全量出度),边=文件级(决策 commit → 其后碰了同一文件的 commit,每决策
画最近 8 条)。胶囊作节点徽标。装配成单文件 graph.html(时间轴 DAG + 点击展开下游列表)。
像 debt.py 一样可独立测;像 course/tunnel 一样注入 HTML 模板。
"""
import hashlib
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from string import Template

from .cache import Cache
from .config import CACHE_DB_PATH, load_config, redact_secrets
from .gitlog import collect_commit_files, parse_breadcrumbs
from .webserve import inline_json

SCAN_LIMIT = 200
TOP_N = 40
MAX_OUT = 8


def _assemble(commits, project_path, project, cache):
    """commits: oldest-first [{sha,date,subject,files}] → {nodes, edges}。零 LLM。"""
    order = {c["sha"]: i for i, c in enumerate(commits)}
    caps_by_sha = {}
    # 胶囊以绝对路径为键封存(digest pkey=str(project_path));此处须用绝对路径查,
    # 否则用 basename 永远查不到、决策节点徽标恒空(与 console/tunnel/debt 口径对齐)。
    for cap in cache.all_capsules(str(project_path)):
        caps_by_sha.setdefault(cap["sha"], []).append(cap)
    info = {}
    for c in commits:
        # body 已随批量 collect_commit_files 取回,不再逐 commit 跑 git show
        decisions, _ = parse_breadcrumbs(c.get("body", ""))
        narr = cache.get_narrative(c["sha"]) or {}
        narr_dec = narr.get("decisions") or []
        if decisions:
            text, kind = decisions[0], "breadcrumb"
        elif narr_dec:
            text, kind = narr_dec[0], "narrative"
        else:
            text, kind = "", ""
        info[c["sha"]] = {"files": set(c["files"] or []), "subject": c["subject"],
                          "date": c["date"], "text": text, "kind": kind}
    decisions = [s for s, v in info.items() if v["text"]]
    full_out = {}
    for d in decisions:
        df, do = info[d]["files"], order[d]
        full_out[d] = [c["sha"] for c in commits          # commits 升序 → 下游升序
                       if order[c["sha"]] > do and (info[c["sha"]]["files"] & df)]
    ranked = sorted(decisions, key=lambda s: (len(full_out[s]), order[s]),
                    reverse=True)[:TOP_N]                  # 按全量出度取 top-N
    ranked_set = set(ranked)
    node_ids, edges = set(ranked), []
    for d in ranked:
        for t in full_out[d][-MAX_OUT:]:                   # full_out 升序,尾部=时间最近
            edges.append((d, t))
            node_ids.add(t)

    def _badge(sha):
        caps = caps_by_sha.get(sha) or []
        if not caps:
            return ""
        done = [redact_secrets(str(c["outcome"])) for c in caps if c.get("outcome")]
        return "胶囊:" + ("、".join(done) if done else "待验证")

    nodes = []
    for sha in node_ids:
        v = info[sha]
        is_dec = sha in ranked_set
        date = v["date"]
        nodes.append({
            "id": sha[:7],
            "date": date.date().isoformat() if hasattr(date, "date") else str(date)[:10],
            "subject": redact_secrets(v["subject"] or ""),
            "text": redact_secrets(v["text"]) if is_dec else "",
            "kind": v["kind"] if is_dec else "change",
            "badge": _badge(sha) if is_dec else "",
            "ts": order[sha],
        })
    nodes.sort(key=lambda n: n["ts"])
    return {"nodes": nodes,
            "edges": [{"from": d[:7], "to": t[:7]} for d, t in edges]}


_CANVAS_COLOR = {"breadcrumb": "5", "narrative": "6"}  # Obsidian 预设:青 / 紫


def _to_canvas(data):
    """决策影响图 → Obsidian JSON Canvas(决策节点配色,x 按时间)。纯 stdlib。"""
    def nid(sha7):
        return hashlib.sha256(sha7.encode()).hexdigest()[:16]
    nodes = []
    for i, n in enumerate(data["nodes"]):
        label = n["text"] or n["subject"] or n["id"]
        if n.get("badge"):
            label += "\n" + n["badge"]
        node = {"id": nid(n["id"]), "type": "text",
                "text": "[%s] %s" % (n["id"], label),
                "x": n["ts"] * 450, "y": (i % 8) * 140,
                "width": 380, "height": 110}
        color = _CANVAS_COLOR.get(n["kind"])
        if color:
            node["color"] = color
        nodes.append(node)
    edges = [{"id": nid(e["from"] + e["to"]), "fromNode": nid(e["from"]),
              "toNode": nid(e["to"]), "fromSide": "right", "toSide": "left"}
             for e in data["edges"]]
    return {"nodes": nodes, "edges": edges}


def _graph_data(pp, project, cache):
    """纯内存装配决策影响图数据 → (data_dict | None, cache_hit, error_or_None)。
    collect→截断最近 SCAN_LIMIT→空仓兜底→缓存命中/(_assemble 并缓存)。不写盘。
    data 以 head SHA 为键缓存(immutable,与 build_graph/MCP 工具共用)。"""
    commits, err = collect_commit_files(pp)
    if err:
        # 空仓(尚无 commit)→ 空图,不报错;其他 git 错误才上报
        if "does not have any commits" in err or "bad default revision" in err:
            commits = []
        else:
            return None, False, err
    commits = commits[-SCAN_LIMIT:]                 # graph.py 自己截断最近 200
    head = commits[-1]["sha"] if commits else "empty"
    key = "graph:" + head[:40]
    cached = cache.get_narrative(key)
    if cached and "nodes" in cached:
        return cached, True, None
    data = _assemble(commits, pp, project, cache)
    cache.put_narrative(key, project, "graph", data)
    return data, False, None


def build_graph_json(project_path, cache):
    """MCP/agent 复用的纯内存入口 → (json_str | None, error_or_None)。绝不写盘。
    内部走 _graph_data;json.dumps(ensure_ascii=False) 保中文叙事不转义。"""
    pp = Path(project_path).resolve()
    data, _hit, err = _graph_data(pp, pp.name, cache)
    if err:
        return None, err
    return json.dumps(data, ensure_ascii=False), None


def build_graph(project_path, vault=None, canvas=False):
    """→ (output_path, error_or_None)。无 git 历史→空图 exit 0(不报错)。
    canvas=True 时额外写 <project>-graph.canvas(Obsidian JSON Canvas)。"""
    cfg = load_config()
    if vault:
        cfg["vault_path"] = vault
    pp = Path(project_path).resolve()
    project = pp.name
    cache = Cache(CACHE_DB_PATH)
    data, cache_hit, err = _graph_data(pp, project, cache)
    cache.close()
    if err:
        return None, err
    today = datetime.now(timezone.utc).astimezone().date()
    template = Template((Path(__file__).parent / "graph.html")
                        .read_text(encoding="utf-8"))
    html_text = template.substitute(
        project=html.escape(project, quote=True),  # 目录名转义防 HTML/JS 注入
        data=inline_json(data),
        generated=f"{today:%Y.%m.%d}")
    vault_dir = Path(cfg["vault_path"]).expanduser()
    vault_dir.mkdir(parents=True, exist_ok=True)
    out = vault_dir / (project + "-graph.html")
    out.write_text(html_text, encoding="utf-8")
    if canvas:
        (vault_dir / (project + "-graph.canvas")).write_text(
            json.dumps(_to_canvas(data), ensure_ascii=False), encoding="utf-8")
    from . import report  # 零 LLM 命令:记一行用量(节点/边),写失败不影响主流程
    report.append_usage({"command": "graph", "project": str(pp),
                         "nodes": len(data["nodes"]), "edges": len(data["edges"]),
                         "cache_hit": cache_hit})
    return out, None
