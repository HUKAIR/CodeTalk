"""只读 spike:从 Cursor 本地 SQLite 抽取一段 AI 会话,验证 vibetrace 能否吃 Cursor 源。

不是生产功能,是可行性验证(POC)。纯本地、只读、不外传;输出前 redact_secrets 脱敏 +
消息正文截断(对话比代码更敏感)。回答三件事:
  1) composerData/bubble 里真有 用户提问 + AI 回答 + 文件上下文 + 时间戳 吗?
  2) 能映射成 vibetrace 的 session 结构(prompts/excerpts/files/ts)吗?
  3) 自带的 文件/commit 引用,够不够给现有 align.py 做 session↔commit 软关联?

用法:  python3 spikes/cursor_session_spike.py            # 自动挑最近最丰富的一段
       python3 spikes/cursor_session_spike.py <composerId>

M0 红线自检:仅标准库(sqlite3/json/pathlib);数据不出本机;容错降级不崩;落盘/打印前脱敏。
"""
import json
import sqlite3
import sys
from pathlib import Path

# 复用 vibetrace 脱敏;独立运行时退化为占位(spike 不强依赖)
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from vibetrace.config import redact_secrets
except Exception:  # pragma: no cover - spike fallback
    def redact_secrets(t):
        return t

PREVIEW = 140  # 正文预览上限:验证结构,不导出整段对话

# Cursor 全局库(composerData + bubbleId 都在这里),跨平台兜底
_CANDIDATES = [
    Path.home() / "Library/Application Support/Cursor/User/globalStorage/state.vscdb",
    Path.home() / ".config/Cursor/User/globalStorage/state.vscdb",
    Path.home() / "AppData/Roaming/Cursor/User/globalStorage/state.vscdb",
]


def _open():
    db = next((p for p in _CANDIDATES if p.exists()), None)
    if not db:
        raise SystemExit("没找到 Cursor 全局库 state.vscdb——Cursor 没装或路径不同。")
    return sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)


def _load(con, key):
    row = con.execute("SELECT value FROM cursorDiskKV WHERE key=?", (key,)).fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except (ValueError, TypeError):
        return None  # 容错:坏行跳过不崩


def list_sessions(con):
    """[(composerId, createdAt, bubble_count)],按消息数降序——挑真实工作会话。"""
    out = []
    for (key,) in con.execute(
            "SELECT key FROM cursorDiskKV WHERE key LIKE 'composerData:%'"):
        cid = key.split(":", 1)[1]
        n = con.execute(
            "SELECT COUNT(*) FROM cursorDiskKV WHERE key LIKE ?",
            (f"bubbleId:{cid}:%",)).fetchone()[0]
        if n:
            d = _load(con, key) or {}
            out.append((cid, d.get("createdAt", 0), n))
    return sorted(out, key=lambda r: (r[2], r[1]), reverse=True)


def _files_from_bubble(b):
    """从一条消息里抠出涉及的文件路径(多个来源,容错)。"""
    files = set()
    for fld in ("relevantFiles", "recentlyViewedFiles"):
        for x in b.get(fld) or []:
            if isinstance(x, str):
                files.add(x)
    for fld in ("attachedCodeChunks", "attachedFileCodeChunksMetadataOnly"):
        for x in b.get(fld) or []:
            if isinstance(x, dict):
                u = x.get("uri") or x.get("relativeWorkspacePath") or x.get("fsPath")
                if isinstance(u, dict):
                    u = u.get("path") or u.get("fsPath")
                if u:
                    files.add(u if isinstance(u, str) else str(u))
    return files


def extract_session(con, cid):
    """映射成 vibetrace session 形状:prompts / excerpts / files / commits / ts。"""
    head = _load(con, f"composerData:{cid}") or {}
    rows = con.execute(
        "SELECT key, value FROM cursorDiskKV WHERE key LIKE ?",
        (f"bubbleId:{cid}:%",)).fetchall()
    bubbles = []
    for _, raw in rows:
        try:
            bubbles.append(json.loads(raw))
        except (ValueError, TypeError):
            continue
    bubbles.sort(key=lambda b: b.get("createdAt") or 0)
    prompts, excerpts, files, commits = [], [], set(), set()
    for b in bubbles:
        text = (b.get("text") or "").strip()
        files |= _files_from_bubble(b)
        for c in b.get("commits") or []:
            sha = c.get("sha") if isinstance(c, dict) else c
            if sha:
                commits.add(str(sha)[:12])
        if not text:
            continue
        # type 1=用户, 2=AI(启发式;原始 type 一并保留供核验)
        role = "user" if b.get("type") == 1 else "ai"
        prev = redact_secrets(text)[:PREVIEW]
        (prompts if role == "user" else excerpts).append((b.get("createdAt"), prev))
    return {
        "session_id": cid,
        "created_at": head.get("createdAt"),
        "draft_text": redact_secrets((head.get("text") or ""))[:PREVIEW],
        "bubble_count": len(bubbles),
        "prompts": prompts,
        "excerpts": excerpts,
        "files_touched": sorted(files),
        "commits_referenced": sorted(commits),
        "lines_added": head.get("totalLinesAdded"),
        "lines_removed": head.get("totalLinesRemoved"),
    }


def main():
    con = _open()
    sessions = list_sessions(con)
    print(f"== Cursor 会话总数(有消息的):{len(sessions)} ==")
    for cid, ts, n in sessions[:8]:
        print(f"  {cid[:8]}  消息 {n:>3}  createdAt={ts}")
    if not sessions:
        return
    cid = sys.argv[1] if len(sys.argv) > 1 else sessions[0][0]
    s = extract_session(con, cid)
    con.close()
    print(f"\n== 抽取样例会话 {cid[:8]} (映射成 vibetrace session 形状) ==")
    print(f"createdAt={s['created_at']}  bubbles={s['bubble_count']}  "
          f"用户提问 {len(s['prompts'])} 条 / AI 回答 {len(s['excerpts'])} 条")
    print(f"涉及文件 {len(s['files_touched'])} 个 / 引用 commit {len(s['commits_referenced'])} 个 "
          f"/ +{s['lines_added']} -{s['lines_removed']} 行")
    print("\n-- 用户提问预览(脱敏+截断)--")
    for ts, p in s["prompts"][:3]:
        print(f"  [{ts}] {p}")
    print("\n-- AI 回答预览(脱敏+截断)--")
    for ts, e in s["excerpts"][:2]:
        print(f"  [{ts}] {e}")
    print("\n-- 文件上下文样例(供 session↔commit 软关联)--")
    for f in s["files_touched"][:8]:
        print(f"  {f}")
    print("\n== 可行性判定 ==")
    has_text = bool(s["prompts"] or s["excerpts"])
    has_files = bool(s["files_touched"])
    print(f"  ① 有 用户提问+AI回答+时间戳 : {'是' if has_text else '否'}")
    print(f"  ② 能映射 vibetrace session : 是(本函数已映射)")
    print(f"  ③ 自带文件/commit 上下文够软关联 : "
          f"{'是' if has_files or s['commits_referenced'] else '弱(需靠时间窗兜底)'}")


if __name__ == "__main__":
    main()
