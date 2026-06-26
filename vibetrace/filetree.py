"""工作区文件树 + git status(零 LLM,纯 stdlib)。

供 console 文件树「接地入口」视图:确定性读工作区状态 + 拼项目结构树。
与 gitlog(历史)分开:这里只关心工作树当下状态。容错降级绝不崩。
"""
import subprocess

from . import gitlog

# 状态码 → 人话标签;列表序即优先级(越靠前越优先):U>D>R>C>A>M>?
STATUS_LABELS = [("U", "冲突"), ("D", "已删除"), ("R", "重命名"),
                 ("C", "复制"), ("A", "新增"), ("M", "已修改"), ("?", "未跟踪")]
_NAME = dict(STATUS_LABELS)
_PRIORITY = {code: i for i, (code, _) in enumerate(STATUS_LABELS)}


def label(code):
    """porcelain 两字符 XY code → 人话标签(确定性)。
    取 XY 两位里优先级更高者定主标签;X(暂存位)非空格且其字母即主标签来源时加「已暂存·」。
    未知字母 → 原样 code(不崩)。"""
    code = (code or "  ")[:2].ljust(2)
    x, y = code[0], code[1]
    letters = [c for c in (x, y) if c not in (" ", "?")]
    if "?" in (x, y):  # 只加一次
        letters.append("?")
    if not letters:
        return code.strip() or "?"
    main = min(letters, key=lambda c: _PRIORITY.get(c, 99))
    name = _NAME.get(main)
    if name is None:
        return code.strip()
    # 已暂存·前缀:X 位非空/非?,且该字符是主标签来源,且不是冲突(U)
    staged = x not in (" ", "?", "U") and x == main
    return ("已暂存·" + name) if staged else name


def status(project_path):
    """工作区 git status(零 LLM)。→ [{"path","code","label"}];git 失败/非 git 仓 → []。
    `-uall` 展开未跟踪目录为逐文件(否则新建目录折叠成 `?? dir/`、内部新增文件全不可见)。
    `-z` NUL 分隔有状态迭代:R/C 项的下一段是 old/orig-path,一并消费;跳空段;丢尾斜杠条目。"""
    try:
        raw = gitlog._git(["status", "--porcelain=v1", "-z", "--untracked-files=all"],
                          project_path)
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        return []
    segs = raw.split("\x00")
    out, i = [], 0
    while i < len(segs):
        seg = segs[i]
        if not seg:
            i += 1
            continue
        code, path = seg[:2], seg[3:]
        i += 2 if code[:1] in ("R", "C") else 1   # R/C(X 位:暂存重命名/复制):消费紧跟的 old-path 段
        if not path or path.endswith("/"):
            continue
        out.append({"path": path, "code": code, "label": label(code)})
    return out


def build_tree(paths, status_map):
    """纯函数:repo 相对路径集 + {path:{code,label}} → 嵌套树。不碰 git/磁盘。
    dir 节点 changed=任一后代有 status;目录在前、各按名字典序。"""
    root = {"name": "", "type": "dir", "children": {}}
    for path in paths:
        parts = [p for p in path.split("/") if p]
        if not parts:
            continue
        node = root
        for part in parts[:-1]:
            child = node["children"].get(part)
            if child is None or child["type"] == "file":
                child = {"name": part, "type": "dir", "children": {}}
                node["children"][part] = child
            node = child
        leaf, st = parts[-1], status_map.get(path)
        node["children"][leaf] = {"name": leaf, "type": "file", "path": path,
                                  **({k: st[k] for k in ("code", "label") if k in st} if st else {})}

    def finalize(node):
        if node["type"] == "file":
            return node
        kids = [finalize(c) for c in node["children"].values()]
        kids.sort(key=lambda c: (c["type"] != "dir", c["name"]))
        node["children"] = kids
        node["changed"] = any(
            c["changed"] if c["type"] == "dir" else ("code" in c) for c in kids)
        return node
    return finalize(root)
