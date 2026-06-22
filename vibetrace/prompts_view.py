"""指令回看(零-LLM):按天/会话时间线列出用户发给 AI 的原始指令 + 这会话改过的文件,
并把它就近「软对齐」到 commit(明确标注「软对齐,可能不准」,绝不冒充因果)。

复用 sessions/cursor_sessions 已抓的 prompts(采集时已脱敏);纯本地、不触网、不调 LLM。
对位场景:「今天我让 AI 实现了一堆功能,但忘了当初具体提了什么,想回看」。
"""
from pathlib import Path

from .config import redact_secrets


def _rel(path, root):
    """仓内文件 → 项目相对路径;仓外文件 → 只留文件名(不泄露绝对路径)。"""
    try:
        return str(Path(path).relative_to(root))
    except ValueError:
        return Path(path).name


def _session_commits(commits):
    """从 align 挂在 commit 上的 matches 反建 session_id → [(sha7, subject)](保序去重)。
    这是软对齐(时间窗 ±30min + 文件交集),只作弱提示,不代表因果。"""
    by_sid = {}
    for c in commits:
        for m in c.get("matches") or []:
            sid = (m.get("session") or {}).get("session_id")
            if not sid:
                continue
            entry = (c.get("sha", "")[:7], c.get("subject", ""))
            hits = by_sid.setdefault(sid, [])
            if entry not in hits:
                hits.append(entry)
    return by_sid


def _hhmm(dt):
    return dt.strftime("%H:%M") if hasattr(dt, "strftime") else "--:--"


def _day(dt):
    return dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else "未知时间"


def _sort_key(s):
    st = s.get("start")
    has = hasattr(st, "strftime")
    return (not has, st if has else None)   # 有时间的按 start 升序,坏/缺时间的排末尾


def build_prompts_view(sessions, commits, project_path):
    """→ markdown 文本(零 LLM)。sessions=scan 后 summary(datetime start/end、
    set/list files_written、list prompts);commits 已 align。无指令→友好提示,绝不崩。"""
    root = Path(project_path).resolve()
    sess = [s for s in sessions if s.get("prompts")]
    if not sess:
        return ("# 指令回看\n\n这段时间没有抓到指令记录"
                "(可能没用 Claude/Cursor,或会话已被清理)。")
    by_sid = _session_commits(commits)
    lines = [f"# 指令回看 · {root.name}(零 LLM,本地)\n"]
    cur_day = None
    for s in sorted(sess, key=_sort_key):
        d = _day(s.get("start"))
        if d != cur_day:
            cur_day = d
            lines.append(f"\n## {d}")
        span = f"{_hhmm(s.get('start'))}–{_hhmm(s.get('end'))}"
        title = redact_secrets(s.get("title") or "") or "(无标题)"
        lines.append(f"\n### {span}  [{s.get('source', '?')}] {title}")
        for p in s["prompts"]:
            lines.append(f"- {redact_secrets(p)}")
        files = sorted({_rel(f, root) for f in (s.get("files_written") or [])})
        if files:
            shown = "、".join(files[:8])
            more = f" 等 {len(files)} 个" if len(files) > 8 else ""
            lines.append(f"→ 改动文件:{shown}{more}")
        hits = by_sid.get(s.get("session_id")) or []
        if hits:
            refs = "  ·  ".join(f"[{sha}] {redact_secrets(sub)}"
                                for sha, sub in hits[:5])
            lines.append("→ 可能对应 commit(软对齐,按时间+文件推测,可能不准):"
                         + refs)
    return "\n".join(lines)
