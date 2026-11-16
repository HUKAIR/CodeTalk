"""Development thread for the graph page: commit trunk, note leaves, local annotations.

零 LLM。主干 = 扫描范围内全部 commit;叶 = 每个 commit 的决策 / 否决 / 待验证
(作者面包屑优先,没有才用缓存叙事并标明来源)。批注只存本机 cache.db,不改 git 历史。
"""
import math
import re
import subprocess

from . import gitlog
from .breadcrumbs import parse_breadcrumbs, parse_rejected
from .config import redact_data, redact_secrets

MAX_LEAVES = 6          # 每个 commit 每类叶子上限(叶 id 末位是单个数字)
MAX_FILES = 30
_NODE = r"[0-9a-f]{7}(?::[drw][0-9])?"
_SHA7 = r"[0-9a-f]{7}"
# 节点批注 / 手动连线 / 计划方向(挂在某个 commit 上,本机记录)
_KEY = re.compile(rf"^(?:{_NODE}|link:{_NODE}>{_NODE}|plan:{_SHA7}:[0-9a-z]{{1,12}})$")
_FIELDS = {"note", "tags", "pin", "hidden", "label", "text", "dir", "done"}
_TEXT_LIMITS = {"note": 2000, "label": 80, "text": 300, "dir": 24}


def thread(commits, cache):
    """commits: oldest-first [{sha,date,subject,files,body}] → {trunk, leaves}。"""
    trunk, leaves = [], []
    for order, commit in enumerate(commits):
        body = commit.get("body", "")
        decisions, watches = parse_breadcrumbs(body)
        groups = {"decision": decisions, "rejected": parse_rejected(body), "watch": watches}
        source = "breadcrumb"
        if not any(groups.values()):
            narrative = cache.get_narrative(commit["sha"]) or {}
            groups = {kind: value if isinstance(value, list) else []     # 坏缓存不拆成单字
                      for kind, value in (("decision", narrative.get("decisions")),
                                          ("rejected", narrative.get("rejected")),
                                          ("watch", narrative.get("risks")))}
            source = "narrative"
        short, date = commit["sha"][:7], commit["date"]
        files = sorted(commit.get("files") or [])
        trunk.append({
            "id": short, "sha": commit["sha"], "ts": order,
            "date": date.date().isoformat() if hasattr(date, "date") else str(date)[:10],
            "subject": redact_secrets(commit.get("subject") or ""),
            "files": [redact_secrets(name) for name in files[:MAX_FILES]],
            "nfiles": len(files)})
        for kind, items in groups.items():
            texts = [text for text in items if isinstance(text, str) and text]
            for index, text in enumerate(texts[:MAX_LEAVES]):
                leaves.append({"id": f"{short}:{kind[0]}{index}", "commit": short,
                               "kind": kind, "source": source,
                               "text": redact_secrets(text)})
    return {"trunk": trunk, "leaves": leaves}


def _number(value):
    # 先比大小再 isfinite:超大整数转 float 会抛 OverflowError
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and abs(value) < 1e6 and math.isfinite(value))


def clean_annotation(data):
    """校验并脱敏一条批注 → (clean, None) | (None, error)。只收已知字段。"""
    if not isinstance(data, dict) or set(data) - _FIELDS:
        return None, "bad annotation"
    clean = {}
    for field, limit in _TEXT_LIMITS.items():
        value = data.get(field)
        if value in (None, ""):
            continue
        if not isinstance(value, str) or len(value) > limit:
            return None, f"bad {field}"
        clean[field] = value
    tags = data.get("tags") or []
    if (not isinstance(tags, list) or len(tags) > 8 or any(
            not isinstance(tag, str) or not tag.strip() or len(tag) > 32 for tag in tags)):
        return None, "bad tags"
    if tags:
        clean["tags"] = [tag.strip() for tag in tags]
    pin = data.get("pin")
    if pin is not None:
        if not (isinstance(pin, dict) and set(pin) == {"x", "y"}
                and _number(pin["x"]) and _number(pin["y"])):
            return None, "bad pin"
        clean["pin"] = {"x": round(pin["x"], 1), "y": round(pin["y"], 1)}
    hidden = data.get("hidden")
    if hidden is not None and not isinstance(hidden, bool):
        return None, "bad hidden"
    if hidden:
        clean["hidden"] = True
    done = data.get("done")                       # 计划的实施提交(7 位短 SHA)
    if done not in (None, ""):
        if not isinstance(done, str) or not re.fullmatch(_SHA7, done):
            return None, "bad done"
        clean["done"] = done
    return redact_data(clean), None


def _is_commit(project, short):
    """短 SHA 必须解析到一个以它开头的 commit;同名分支/标签不算。"""
    try:
        full = gitlog._git(["rev-parse", "--verify", "--quiet", short + "^{commit}"], project)
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        return False
    return full.strip().startswith(short)


def write_annotation(cache, project, payload):
    """POST /graph/annotation:{key, data} → (body, status)。data 为 null 即删除。"""
    key = payload.get("key")
    if not isinstance(key, str) or not _KEY.fullmatch(key):
        return {"error": "bad node"}, 400
    if "data" not in payload:                  # 删除必须显式写 data: null
        return {"error": "bad annotation"}, 400
    data = payload["data"]
    clean = None
    if data is not None:
        clean, error = clean_annotation(data)
        if error:
            return {"error": error}, 400
    if key.startswith("plan:"):
        nodes = [key.split(":")[1]] + ([clean["done"]] if clean and clean.get("done") else [])
    else:
        nodes = re.findall(_NODE, key.removeprefix("link:"))
    for node in nodes:
        if not _is_commit(project, node[:7]):
            return {"error": "commit not found"}, 404
    # 节点批注 / 计划清空 = 删除;连线本身就是记录,空 data 也保留
    if clean is None or (not clean and not key.startswith("link:")):
        cache.delete_graph_annotation(project, key)
    else:
        cache.put_graph_annotation(project, key, clean)
    return {"ok": True, "annotations": cache.get_graph_annotations(project)}, 200
