"""统一控制台:把开工概览 / 时光轴 / 决策图 / 理解债 汇成一个单文件 web 页。

进页先看概览,顶部导航切视图,每视图概览优先、按需钻取——取代"一整页 dump"。
全程零 LLM(吃已缓存数据);复用 tunnel._payload / graph._assemble / debt_board / brief。
单文件、零构建、离线;--serve 经 webserve 把胶囊回答 + 回看写回 cache.db。
"""
from datetime import datetime, timezone
from pathlib import Path
from string import Template

from . import brief, filetree, graph, tunnel
from .cache import Cache
from .config import CACHE_DB_PATH, load_config, redact_data, redact_secrets
from .debt import debt_board
from .gitlog import collect_commit_files
from .webserve import inline_json


def _file_grounding(changed_paths, commits, narratives):
    """零 LLM:为每个变更文件列其历史 commit + 决策 + SHA 引用(供右面板核验)。
    只为 changed_paths 构建(有界);吃已建 commits/narratives 不二次查 DB。
    sources 据 SHA 确定性合成(非 narrative 字段)。→ [{"path","commits":[...]}]。"""
    out = []
    for path in changed_paths:
        rows = []
        for c in commits:
            if path not in (c.get("files") or []):
                continue
            nv = narratives.get(c["sha"])
            n = nv if isinstance(nv, dict) else {}
            rows.append({
                "sha": c["sha"][:7],
                "subject": c.get("subject", ""),
                "date": c["date"].date().isoformat() if c.get("date") else "",
                "decisions": (n or {}).get("decisions") or [],
                "sources": [{"type": "commit", "sha": c["sha"][:7]}],
            })
        rows.reverse()                               # 最新在前
        out.append({"path": path, "commits": rows})
    return out


def _assemble(project_path, cache):
    """汇五视图数据为一份 JSON(零 LLM,复用现成件)。→ (data, error_or_None)。
    空仓不报错(返回空时光轴);真 git 错误才上报。"""
    pp = Path(project_path).resolve()
    project = pp.name
    pkey = str(pp)
    cache.rekey_project(project, pkey)              # 迁旧 basename 键(幂等)
    today = datetime.now(timezone.utc).astimezone().date()
    commits, err = collect_commit_files(pp)
    if err:
        if "does not have any commits" in err or "bad default revision" in err:
            commits = []
        else:
            return None, err
    narratives = {c["sha"]: cache.get_narrative(c["sha"]) for c in commits}
    capsules_by_sha = {}
    for cap in cache.all_capsules(pkey):
        capsules_by_sha.setdefault(cap["sha"], []).append(cap)
    debt = debt_board(pp, cache, today)
    cov = brief._breadcrumb_coverage(pp)
    data = {
        "overview": {
            "last": cache.latest_daily(pkey),
            "debt_top": debt[:3],
            "pending": cache.pending_capsules(pkey),
            "coverage": list(cov) if cov else None,
        },
        "timeline": tunnel._payload(commits, narratives, capsules_by_sha, today),
        "graph": (graph._assemble(commits[-graph.SCAN_LIMIT:], pp, project, cache)
                  if commits else {"nodes": [], "edges": []}),
        "debt": debt,
    }
    tp = filetree.tree_payload(pp)                   # 复用装配(零 LLM,消除同构双份 + 省 1 次 git 子进程)
    data["tree"] = {
        "nodes": tp["nodes"],
        "grounding": _file_grounding([s["path"] for s in tp["status"]], commits, narratives),
    }
    return data, None


def _build_html(project_path, serve, chat=False):
    """装配控制台 HTML。→ (html, project_name, error)。落盘前脱敏。
    chat=True(仅 vibetrace web 服务时)启用内嵌接地对话 dock(POST /api/chat/stream);
    静态/webserve 无该端点 → 默认 False,前端不挂 chat UI、不发请求。"""
    pp = Path(project_path).resolve()
    cache = Cache(CACHE_DB_PATH)
    data, err = _assemble(pp, cache)
    cache.close()
    if err:
        return None, pp.name, err
    from . import report  # 零 LLM 命令:记一行用量(commit 数 / serve 模式),写失败不影响主流程
    report.append_usage({"command": "console", "project": str(pp),
                         "commits": len(data["timeline"]), "serve": serve})
    today = datetime.now(timezone.utc).astimezone().date()
    template = Template((Path(__file__).parent / "console.html")
                        .read_text(encoding="utf-8"))
    html = template.substitute(
        project=pp.name,
        data=inline_json(redact_data(data)),
        generated=f"{today:%Y.%m.%d}",
        serve="true" if serve else "false",
        chat="true" if chat else "false",
    )
    return redact_secrets(html), pp.name, None


def render_console(project_path):
    """写静态控制台 HTML(file://,只读)。→ (path, error)。"""
    cfg = load_config()
    html, project, err = _build_html(project_path, serve=False)
    if err:
        return None, err
    vault = Path(cfg["vault_path"]).expanduser()
    vault.mkdir(parents=True, exist_ok=True)
    out = vault / (project + "-console.html")
    out.write_text(html, encoding="utf-8")
    return out, None


def serve_console(project_path, open_browser=True):
    """起本地服务,胶囊回答 + 回看即时写回 cache。→ error_or_None(阻塞到 Ctrl+C)。"""
    html, _, err = _build_html(project_path, serve=True)
    if err:
        return err
    from .webserve import serve_html
    return serve_html(html, project_path, open_browser)
