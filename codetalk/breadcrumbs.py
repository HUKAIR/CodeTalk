"""Vibe-* 决策面包屑解析(纯文本,不碰 git);gitlog re-export 供既有调用方。"""


def _fold_breadcrumbs(body):
    """折叠三类尾注的缩进续行;空行、普通正文和新尾注结束上一条。"""
    prefixes = ("Vibe-Decision:", "Vibe-Watch:", "Vibe-Rejected:")
    kind, text = None, ""
    for raw in (body or "").splitlines():
        line = raw.strip()
        if line and not line.startswith(prefixes) and raw[0].isspace() and kind:
            text = f"{text} {line}".strip()
            continue
        if kind and text:
            yield kind, text
        kind, text = None, ""
        for prefix in prefixes:
            if line.startswith(prefix):
                kind, text = prefix, line[len(prefix):].strip()
                break
    if kind and text:
        yield kind, text


def parse_breadcrumbs(body):
    """从 commit body 提取决策面包屑。区分大小写,行首匹配 Vibe-Decision:/Vibe-Watch:。
    返回 (decisions, watches);body 为空/None 安全返回 ([], [])。"""
    decisions, watches = [], []
    for kind, text in _fold_breadcrumbs(body):
        if kind == "Vibe-Decision:":
            decisions.append(text)
        elif kind == "Vibe-Watch:":
            watches.append(text)
    return decisions, watches


def parse_rejected(body):
    """从 commit body 提取 Vibe-Rejected 面包屑(被否决的备选)。区分大小写,行首匹配。
    被否决方案是 diff 结构性取不到的 why-NOT(README 护城河),提成一等公民供 blame 独立标注。
    body 为空/None 安全返回 []。"""
    return [text for kind, text in _fold_breadcrumbs(body) if kind == "Vibe-Rejected:"]


def has_decision_notes(body):
    """Whether a commit body carries any supported Vibe-* decision record."""
    decisions, watches = parse_breadcrumbs(body)
    return bool(decisions or watches or parse_rejected(body))


def same_breadcrumb(cached, fresh):
    """同一 commit 内,非空缓存值等于现算全文或其单空格边界前缀。"""
    return bool(cached) and (fresh == cached or fresh.startswith(cached + " "))


def merge_breadcrumb_values(cached, fresh):
    """叙事在前、面包屑在后;等价缓存项移除,全文保留在现算位置。"""
    remaining = [text for text in cached
                 if not any(same_breadcrumb(text, note) for note in fresh)]
    return list(dict.fromkeys(remaining + fresh))
