"""Decision-impact graph: which decision rippled into which later changes.

纯本地、零 LLM。节点=决策性 commit(Vibe-Decision 面包屑优先,否则叙事 decisions;
top-N=40 按全量出度),边=文件级(决策 commit → 其后碰了同一文件的 commit,每决策
画最近 8 条)。胶囊作节点徽标。装配成单文件 graph.html(时间轴 DAG + 点击展开下游列表)。
像 debt.py 一样可独立测;像 course/tunnel 一样注入 HTML 模板。
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from string import Template

from .cache import Cache
from .config import CACHE_DB_PATH, load_config, redact_secrets
from .gitlog import collect_commit_files, commit_body, parse_breadcrumbs

SCAN_LIMIT = 200
TOP_N = 40
MAX_OUT = 8


def _assemble(commits, project_path, project, cache):
    """commits: oldest-first [{sha,date,subject,files}] → {nodes, edges}。零 LLM。"""
    order = {c["sha"]: i for i, c in enumerate(commits)}
    caps_by_sha = {}
    for cap in cache.all_capsules(project):
        caps_by_sha.setdefault(cap["sha"], []).append(cap)
    info = {}
    for c in commits:
        decisions, _ = parse_breadcrumbs(commit_body(project_path, c["sha"]))
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
        for t in full_out[d][:MAX_OUT]:                    # 时间最近的 8 个
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


def build_graph(project_path, vault=None):
    """→ (output_path, error_or_None)。无 git 历史→空图 exit 0(不报错)。"""
    cfg = load_config()
    if vault:
        cfg["vault_path"] = vault
    pp = Path(project_path).resolve()
    project = pp.name
    commits, err = collect_commit_files(pp)
    if err:
        # 空仓(尚无 commit)→ 空图,不报错;其他 git 错误才上报
        if "does not have any commits" in err or "bad default revision" in err:
            commits = []
        else:
            return None, err
    commits = commits[-SCAN_LIMIT:]                 # graph.py 自己截断最近 200
    cache = Cache(CACHE_DB_PATH)
    head = commits[-1]["sha"] if commits else "empty"
    key = "graph:" + head[:40]
    cached = cache.get_narrative(key)
    if cached and "nodes" in cached:
        data = cached
    else:
        data = _assemble(commits, pp, project, cache)
        cache.put_narrative(key, project, "graph", data)
    cache.close()
    today = datetime.now(timezone.utc).astimezone().date()
    template = Template((Path(__file__).parent / "graph.html")
                        .read_text(encoding="utf-8"))
    html = template.substitute(
        project=project,
        data=json.dumps(data, ensure_ascii=False).replace("</", "<\\/"),
        generated="%04d.%02d.%02d" % (today.year, today.month, today.day))
    vault_dir = Path(cfg["vault_path"]).expanduser()
    vault_dir.mkdir(parents=True, exist_ok=True)
    out = vault_dir / (project + "-graph.html")
    out.write_text(html, encoding="utf-8")
    return out, None
