"""Tolerant parser for Cursor's local AI sessions (composer) → vibetrace
session summaries. Non-official SQLite schema (cursorDiskKV/ItemTable),
empirically verified 2026-06-21 (see spec). Opened read-only/immutable;
every read .get()-guarded; degrades and never raises.
"""
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from .config import redact_secrets, VIBETRACE_DIR
from .sessions import (EXCERPT_CAP, MAX_EXCERPTS, MAX_PROMPTS, PROMPT_CAP,
                       _freeze, _thaw, head_tail)

log = logging.getLogger("vibetrace")

_USER_DIRS = [
    Path.home() / "Library/Application Support/Cursor/User",   # macOS(已实测)
    Path.home() / ".config/Cursor/User",                       # Linux(未实测)
    Path(os.environ.get("APPDATA", "")) / "Cursor/User",       # Windows(未实测)
]


def _user_dir():
    return next((d for d in _USER_DIRS if d.is_dir()), None)


def _open_ro(db_path):
    return sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)


def _table_get(con, table, key):
    """读 SQLite 键值表(cursorDiskKV / ItemTable)一项 → 解析 JSON;任何问题返回 None。"""
    try:
        row = con.execute(
            f"SELECT value FROM {table} WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None
    except (sqlite3.Error, ValueError, TypeError):
        return None


def project_composer_ids(user_dir, project_path):
    """workspace 优先归属:workspace.json.folder==项目 → 该 workspace 的 composerIds。
    返回 (ids set, matched bool);未命中任何 workspace 时 matched=False(走文件兜底)。"""
    target = Path(project_path).resolve()
    for ws in sorted((user_dir / "workspaceStorage").glob("*/")):
        try:
            folder = json.loads((ws / "workspace.json").read_text(encoding="utf-8"))["folder"]
            folder_path = Path(unquote(urlparse(folder).path)).resolve()
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if folder_path != target:
            continue
        db = ws / "state.vscdb"
        if not db.exists():
            return set(), True
        try:
            con = _open_ro(db)
            data = _table_get(con, "ItemTable", "composer.composerData") or {}
            con.close()
        except sqlite3.Error as exc:
            log.warning("Cursor workspace 库读失败:%r", exc)
            return set(), True
        ids = {c.get("composerId") for c in (data.get("allComposers") or [])
               if isinstance(c, dict) and c.get("composerId")}
        return ids, True
    return set(), False


def _ms(value):
    """Cursor epoch 毫秒 → tz-aware UTC datetime;非法返回 None。"""
    try:
        return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _epoch(value):
    """createdAt(int 或数字字符串)→ 可比较 int 毫秒;非数值返回 0。
    真实 Cursor 数据 createdAt 偶为字符串,直接与 int 比较/排序会 TypeError(dogfood 实测)。"""
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):   # 溢出/无穷串也按契约降级为 0(同 _ms)
        return 0


def _abs_files(bubble, root):
    """从一条消息抠出涉及文件,统一成绝对路径(供 align 与 commit 文件求交)。"""
    out = set()
    for fld in ("relevantFiles", "recentlyViewedFiles"):
        for x in bubble.get(fld) or []:
            if isinstance(x, str):
                out.add(x)
    for fld in ("attachedCodeChunks", "attachedFileCodeChunksMetadataOnly"):
        for x in bubble.get(fld) or []:
            if isinstance(x, dict):
                u = (x.get("uri") or x.get("relativeWorkspacePath") or x.get("fsPath"))
                if isinstance(u, dict):
                    u = u.get("path") or u.get("fsPath")
                if isinstance(u, str):
                    out.add(u)
    abs_out = set()
    for p in out:
        if p.startswith("file://"):
            p = unquote(urlparse(p).path)
        pp = Path(p)
        abs_out.add(str(pp if pp.is_absolute() else (root / pp)))
    return abs_out


def _blank_summary(cid):
    return {"session_id": cid, "title": "", "prompts": [], "excerpts": [],
            "files_written": set(), "files_read": set(),
            "start": None, "end": None, "records": 0, "parse_failures": 0,
            "is_subagent": False,   # 与 Claude summary 契约对齐(Cursor 会话非 subagent)
            "source": "cursor",     # evidence 透传:区分原话来自哪个工具
            "tokens": {"input": 0, "output": 0, "cache_read": 0}}


def _parse_composer(gcon, cid, root):
    head = _table_get(gcon, "cursorDiskKV", f"composerData:{cid}")
    if not isinstance(head, dict):   # 非官方 schema:损坏/版本变可能非 dict,守住免整条会话丢
        head = {}
    bubbles = []
    try:
        rows = gcon.execute("SELECT value FROM cursorDiskKV WHERE key LIKE ?",
                            (f"bubbleId:{cid}:%",)).fetchall()
    except sqlite3.Error:
        rows = []
    for (raw,) in rows:
        try:
            obj = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict):   # 合法但非对象的 JSON(数组/标量)不致整条会话丢失
            bubbles.append(obj)
    bubbles.sort(key=lambda b: _epoch(b.get("createdAt")))   # createdAt 可能是字符串
    s = _blank_summary(cid)
    for b in bubbles:
        ts = _ms(b.get("createdAt"))
        if ts:
            s["start"] = min(s["start"] or ts, ts)
            s["end"] = max(s["end"] or ts, ts)
        s["files_written"] |= _abs_files(b, Path(root))
        raw_text = b.get("text")   # 非 str(富内容 dict/list)降级为空,免 .strip() 崩掉整条会话
        text = raw_text.strip() if isinstance(raw_text, str) else ""
        if not text:
            continue
        s["records"] += 1
        if b.get("type") == 1 and len(s["prompts"]) < MAX_PROMPTS:
            s["prompts"].append(redact_secrets(head_tail(text, PROMPT_CAP)))
        elif b.get("type") == 2 and len(s["excerpts"]) < MAX_EXCERPTS:
            s["excerpts"].append(redact_secrets(head_tail(text, EXCERPT_CAP)))
    # 先脱敏整段再切,避免 secret 跨第 60 字符被截成残片逃过正则(title 经 put_session 落盘不二次脱敏)
    head_text = head.get("text")   # 非 str 草稿降级为空,免 [:60] 切片崩掉整条会话
    s["title"] = (s["prompts"][0][:60] if s["prompts"]
                  else redact_secrets(head_text if isinstance(head_text, str) else "")[:60])
    return s


def _ids_by_file_overlap(gcon, root):
    """文件兜底:扫全局所有 composer,凡有消息文件落在本仓下即归属。"""
    root = Path(root).resolve()
    ids = set()
    try:
        rows = gcon.execute(
            "SELECT key FROM cursorDiskKV WHERE key LIKE 'composerData:%'").fetchall()
    except sqlite3.Error:
        return ids
    for (key,) in rows:
        cid = key.split(":", 1)[1]
        try:
            brows = gcon.execute("SELECT value FROM cursorDiskKV WHERE key LIKE ?",
                                 (f"bubbleId:{cid}:%",)).fetchall()
        except sqlite3.Error:
            continue
        for (raw,) in brows:
            try:
                b = json.loads(raw)
            except (ValueError, TypeError):
                continue
            if not isinstance(b, dict):   # 非对象 JSON 跳过,_abs_files 才不会 AttributeError
                continue
            for f in _abs_files(b, root):
                try:
                    Path(f).resolve().relative_to(root)
                    ids.add(cid)
                    break
                except ValueError:
                    continue
            if cid in ids:
                break
    return ids


def scan_sessions(project_path, since_dt, cache=None):
    """Return (summaries, error_or_None). Degrades, never raises.
    与 sessions.scan_sessions 同契约,供 digest 无差别合并。"""
    user = _user_dir()
    if not user:
        return [], "未找到 Cursor 数据目录(未安装或路径不同)"
    gdb = user / "globalStorage" / "state.vscdb"
    if not gdb.exists():
        return [], f"Cursor 全局库不存在:{gdb}"
    try:
        gcon = _open_ro(gdb)
    except sqlite3.Error as exc:
        return [], f"Cursor 全局库打开失败:{exc}"
    root = Path(project_path).resolve()
    summaries = []
    try:
        ids, matched = project_composer_ids(user, project_path)
        if not matched:
            ids = _ids_by_file_overlap(gcon, root)
        for cid in sorted(ids):
            try:
                last = gcon.execute(
                    "SELECT value FROM cursorDiskKV WHERE key LIKE ?",
                    (f"bubbleId:{cid}:%",)).fetchall()
                n = len(last)                       # 由 fetchall 推出,省一次 COUNT 扫表
                last_ms = 0
                for (raw,) in last:
                    try:
                        obj = json.loads(raw)
                    except (ValueError, TypeError):
                        continue
                    if isinstance(obj, dict):       # 非对象 JSON 不抛 AttributeError
                        last_ms = max(last_ms, _epoch(obj.get("createdAt")))  # 可能是字符串
                m = _ms(last_ms)
                if since_dt and m and m < since_dt:  # 早剪枝:窗口外会话免解析全部 bubble
                    continue
                ckey = "cursor:" + cid              # 源前缀:与 Claude session 键隔离、列语义不混
                cached = cache.get_session(ckey) if cache else None
                if cached and last_ms and cached["mtime"] == last_ms \
                        and cached["size"] == n:
                    s = _thaw(cached["summary"])
                else:
                    s = _parse_composer(gcon, cid, root)
                    if cache and s["records"] and last_ms:  # 无时间戳不缓存,免陈旧命中
                        cache.put_session(
                            ckey, s["end"].isoformat() if s["end"] else "",
                            last_ms, n, _freeze(s))
                if not s["records"]:
                    continue
                if since_dt and s["end"] and s["end"] < since_dt:
                    continue
                summaries.append(s)
            except Exception as exc:   # 单会话容错,不拖垮整体
                log.warning("Cursor 会话 %s 解析失败:%r", cid[:8], exc)
        return summaries, None
    finally:
        gcon.close()


NOTICE_SENTINEL = VIBETRACE_DIR / ".cursor_notice_shown"


def maybe_notice():
    """首次启用 Cursor 源时一次性告知(本地只读、可关),之后静默。"""
    try:
        if NOTICE_SENTINEL.exists():
            return
        log.warning("已启用 Cursor 会话源:将读取本地 Cursor 会话(只读、不出本机);"
                    "可在 ~/.vibetrace/config.json 的 sources 移除 \"cursor\" 关闭。")
        NOTICE_SENTINEL.parent.mkdir(parents=True, exist_ok=True)
        NOTICE_SENTINEL.write_text("", encoding="utf-8")
    except OSError:
        pass   # sentinel 写不了也不能拖垮主流程
