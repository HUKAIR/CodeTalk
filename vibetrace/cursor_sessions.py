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

from .config import redact_secrets
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
    except (TypeError, ValueError, OSError):
        return None


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
            "tokens": {"input": 0, "output": 0, "cache_read": 0}}


def _parse_composer(gcon, cid, root):
    head = _table_get(gcon, "cursorDiskKV", f"composerData:{cid}") or {}
    bubbles = []
    try:
        rows = gcon.execute("SELECT value FROM cursorDiskKV WHERE key LIKE ?",
                            (f"bubbleId:{cid}:%",)).fetchall()
    except sqlite3.Error:
        rows = []
    for (raw,) in rows:
        try:
            bubbles.append(json.loads(raw))
        except (ValueError, TypeError):
            continue
    bubbles.sort(key=lambda b: b.get("createdAt") or 0)
    s = _blank_summary(cid)
    for b in bubbles:
        ts = _ms(b.get("createdAt"))
        if ts:
            s["start"] = min(s["start"] or ts, ts)
            s["end"] = max(s["end"] or ts, ts)
        s["files_written"] |= _abs_files(b, Path(root))
        text = (b.get("text") or "").strip()
        if not text:
            continue
        s["records"] += 1
        if b.get("type") == 1 and len(s["prompts"]) < MAX_PROMPTS:
            s["prompts"].append(redact_secrets(head_tail(text, PROMPT_CAP)))
        elif b.get("type") == 2 and len(s["excerpts"]) < MAX_EXCERPTS:
            s["excerpts"].append(redact_secrets(head_tail(text, EXCERPT_CAP)))
    s["title"] = (s["prompts"][0][:60] if s["prompts"]
                  else redact_secrets((head.get("text") or "")[:60]))
    return s
