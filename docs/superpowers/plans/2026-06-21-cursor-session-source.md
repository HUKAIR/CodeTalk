# Cursor 会话源 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** opt-in 开启后,vibetrace `digest` 把本仓相关的 Cursor AI 会话(composer)与 Claude 会话一并纳入软关联,使 ask/graph 等下游受益。

**Architecture:** 新建 `vibetrace/cursor_sessions.py`,其 `scan_sessions(project_path, since_dt, cache)` 返回与 `sessions.scan_sessions` **同一形状**的 summary;在 `digest.py` 的会话汇集点(scan→align 之间)opt-in 合并。`align.py`/`enrich.py`/`sessions.py` 消费逻辑零改。

**Tech Stack:** Python 3.11+,仅标准库(`sqlite3`/`json`/`urllib.parse`/`pathlib`)+ 复用 `vibetrace.sessions` 与 `vibetrace.config`。stdlib `unittest`。

基线分支:`feat/cursor-source`(stacked on `feat/maturity-pass`/#28)。spec:`docs/superpowers/specs/2026-06-21-cursor-session-source-design.md`。

## Global Constraints
- 仅标准库 + 复用 vibetrace 现有模块;**禁新增第三方依赖**。
- 单 Python 模块 **< 300 行**(`cursor_sessions.py` 控制在此内)。
- Cursor 库一律 **只读 immutable** 打开:`sqlite3.connect(f"file:{p}?mode=ro&immutable=1", uri=True)`。
- **数据不出本机**;落盘/入 summary 前 `redact_secrets`。
- **容错降级绝不崩**:任何库/会话/字段问题 → 警告 + 跳过/返回空,digest 退回 Claude-only。
- 启用为 **显式 opt-in**:`cfg["sources"]` 默认 `["claude"]`;`--source` 可覆盖。
- summary 截断复用 `sessions.PROMPT_CAP`(400)/`EXCERPT_CAP`(300)与 `sessions.head_tail`。
- 角色:bubble `type==1`→用户(prompts)、`type==2`→AI(excerpts);其它跳过。
- 测试用**合成 SQLite fixture**,不依赖真实 Cursor;每模块 `python3 -m unittest discover -s tests` 全绿。

---

### Task 1: config 增加 `sources` 默认(opt-in 底座)

**Files:**
- Modify: `vibetrace/config.py:16-28`(DEFAULTS 字典)
- Test: `tests/test_cursor_config.py`

**Interfaces:**
- Produces: `load_config()["sources"]` → `list[str]`,默认 `["claude"]`。

- [ ] **Step 1: 写失败测试**
```python
# tests/test_cursor_config.py
import unittest
from vibetrace.config import load_config, DEFAULTS

class TestSourcesDefault(unittest.TestCase):
    def test_default_sources_is_claude_only(self):
        self.assertEqual(DEFAULTS["sources"], ["claude"])
        self.assertEqual(load_config()["sources"], ["claude"])

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试看失败**
Run: `python3 -m unittest tests.test_cursor_config -v`
Expected: FAIL — `KeyError: 'sources'`。

- [ ] **Step 3: 最小实现**
在 `vibetrace/config.py` 的 `DEFAULTS` 里、`"output_lang"` 行后加一行:
```python
    "sources": ["claude"],   # 会话源;加 "cursor" 启用 Cursor(opt-in,数据仍不出本机)
```

- [ ] **Step 4: 跑测试看通过**
Run: `python3 -m unittest tests.test_cursor_config -v` — Expected: PASS。

- [ ] **Step 5: 提交**
```bash
git add vibetrace/config.py tests/test_cursor_config.py
git commit -m "feat(config): sources 默认 [claude](Cursor 源 opt-in 底座)"
```

---

### Task 2: cursor_sessions 骨架 + 项目归属(workspace→composerIds)

**Files:**
- Create: `vibetrace/cursor_sessions.py`
- Test: `tests/test_cursor_sessions.py`

**Interfaces:**
- Produces:
  - `_user_dir() -> Path | None`
  - `_open_ro(db_path: Path) -> sqlite3.Connection`
  - `_table_get(con, table: str, key: str) -> object | None`
  - `project_composer_ids(user_dir: Path, project_path) -> (set[str], bool)` — workspace.json folder==项目 → 该 workspace `ItemTable['composer.composerData'].allComposers` 的 composerId 集;`bool` 表示是否命中某 workspace(未命中→调用方走文件兜底)。

- [ ] **Step 1: 写失败测试(含合成 fixture 工具,后续 Task 复用)**
```python
# tests/test_cursor_sessions.py
import json, sqlite3, tempfile, unittest
from pathlib import Path
from urllib.parse import quote
from vibetrace import cursor_sessions as cs

def make_workspace(user_dir, folder_path, composer_ids):
    """造一个 workspaceStorage/<h>/ : workspace.json(folder URI) + state.vscdb(ItemTable)。"""
    ws = Path(user_dir) / "workspaceStorage" / "h1"
    ws.mkdir(parents=True)
    uri = "file://" + quote(str(folder_path))
    (ws / "workspace.json").write_text(json.dumps({"folder": uri}))
    con = sqlite3.connect(ws / "state.vscdb")
    con.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO ItemTable VALUES (?,?)",
                ("composer.composerData",
                 json.dumps({"allComposers": [{"composerId": c} for c in composer_ids]})))
    con.commit(); con.close()
    return ws

class TestAttribution(unittest.TestCase):
    def test_workspace_folder_maps_to_composer_ids(self):
        with tempfile.TemporaryDirectory() as t:
            user = Path(t) / "User"; user.mkdir()
            proj = Path(t) / "myrepo"; proj.mkdir()
            make_workspace(user, proj, ["aaa", "bbb"])
            ids, matched = cs.project_composer_ids(user, proj)
            self.assertTrue(matched)
            self.assertEqual(ids, {"aaa", "bbb"})

    def test_no_matching_workspace_returns_false(self):
        with tempfile.TemporaryDirectory() as t:
            user = Path(t) / "User"; (user / "workspaceStorage").mkdir(parents=True)
            other = Path(t) / "other"; other.mkdir()
            ids, matched = cs.project_composer_ids(user, other)
            self.assertEqual((ids, matched), (set(), False))

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试看失败**
Run: `python3 -m unittest tests.test_cursor_sessions -v`
Expected: FAIL — `ModuleNotFoundError`/`AttributeError: project_composer_ids`。

- [ ] **Step 3: 实现骨架 + 归属**
```python
# vibetrace/cursor_sessions.py
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
```

- [ ] **Step 4: 跑测试看通过**
Run: `python3 -m unittest tests.test_cursor_sessions -v` — Expected: PASS(2 项)。

- [ ] **Step 5: 提交**
```bash
git add vibetrace/cursor_sessions.py tests/test_cursor_sessions.py
git commit -m "feat(cursor): 骨架 + workspace→composerIds 项目归属"
```

---

### Task 3: 解析一个 composer → session summary

**Files:**
- Modify: `vibetrace/cursor_sessions.py`
- Test: `tests/test_cursor_sessions.py`

**Interfaces:**
- Consumes: `_table_get`(Task 2);`sessions.{head_tail,PROMPT_CAP,EXCERPT_CAP,MAX_PROMPTS,MAX_EXCERPTS}`。
- Produces:
  - `_ms(v) -> datetime | None`(epoch ms → UTC datetime)
  - `_abs_files(bubble: dict, root: Path) -> set[str]`(消息涉及文件 → 绝对路径)
  - `_blank_summary(cid) -> dict`(与 sessions summary 同形状)
  - `_parse_composer(gcon, cid, root) -> dict`(summary:含 session_id/title/prompts/excerpts/files_written/files_read/start/end/records/parse_failures/tokens)

- [ ] **Step 1: 写失败测试(扩展 fixture:全局库 composer+bubbles)**
```python
# 追加到 tests/test_cursor_sessions.py
def make_global(user_dir, composer_id, bubbles, created=1000):
    """造 globalStorage/state.vscdb : composerData + 若干 bubbleId 行。
    bubbles: [(type, text, createdAt, [files])]。"""
    g = Path(user_dir) / "globalStorage"; g.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(g / "state.vscdb")
    con.execute("CREATE TABLE IF NOT EXISTS cursorDiskKV (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT OR REPLACE INTO cursorDiskKV VALUES (?,?)",
                (f"composerData:{composer_id}", json.dumps({"createdAt": created, "text": ""})))
    for i, (typ, text, ts, files) in enumerate(bubbles):
        con.execute("INSERT OR REPLACE INTO cursorDiskKV VALUES (?,?)",
                    (f"bubbleId:{composer_id}:b{i}",
                     json.dumps({"type": typ, "text": text, "createdAt": ts,
                                 "relevantFiles": files})))
    con.commit(); con.close()
    return g / "state.vscdb"

class TestParseComposer(unittest.TestCase):
    def test_maps_bubbles_to_prompts_excerpts_files_ts(self):
        with tempfile.TemporaryDirectory() as t:
            user = Path(t) / "User"; user.mkdir()
            root = Path(t) / "repo"; root.mkdir()
            db = make_global(user, "cid", [
                (1, "为什么用乐观锁", 1000, ["a.py"]),
                (2, "因为实现简单可靠,且 " + "x" * 400, 2000, ["a.py", "b.py"]),
            ])
            con = cs._open_ro(db)
            s = cs._parse_composer(con, "cid", root); con.close()
            self.assertEqual(s["session_id"], "cid")
            self.assertEqual(s["prompts"], ["为什么用乐观锁"])
            self.assertEqual(len(s["excerpts"]), 1)
            self.assertLessEqual(len(s["excerpts"][0]), cs.EXCERPT_CAP)
            self.assertEqual(s["files_written"], {str(root / "a.py"), str(root / "b.py")})
            self.assertEqual(s["start"].year, cs._ms(1000).year)
            self.assertTrue(s["start"] < s["end"])

    def test_secret_in_bubble_is_redacted(self):
        with tempfile.TemporaryDirectory() as t:
            user = Path(t) / "User"; user.mkdir(); root = Path(t) / "r"; root.mkdir()
            db = make_global(user, "c", [(1, "key sk-abcdef0123456789ABCD here", 5, [])])
            con = cs._open_ro(db); s = cs._parse_composer(con, "c", root); con.close()
            self.assertIn("[REDACTED]", s["prompts"][0])
            self.assertNotIn("sk-abcdef0123456789ABCD", s["prompts"][0])
```

- [ ] **Step 2: 跑测试看失败**
Run: `python3 -m unittest tests.test_cursor_sessions.TestParseComposer -v`
Expected: FAIL — `AttributeError: _parse_composer`。

- [ ] **Step 3: 实现解析(追加到 cursor_sessions.py)**
```python
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
```
> 注:`head_tail(text, cap)` 复用 sessions.py(str → 首+…+尾,≤cap)。`files_read` 留空集(Cursor 不清晰区分读/写;涉及文件统一进 files_written 以最大化 align 文件重叠)。

- [ ] **Step 4: 跑测试看通过**
Run: `python3 -m unittest tests.test_cursor_sessions.TestParseComposer -v` — Expected: PASS。

- [ ] **Step 5: 提交**
```bash
git add vibetrace/cursor_sessions.py tests/test_cursor_sessions.py
git commit -m "feat(cursor): composer+bubbles → session summary(角色/文件/时间/脱敏)"
```

---

### Task 4: scan_sessions(归属+解析+兜底+since+增量缓存+容错)

**Files:**
- Modify: `vibetrace/cursor_sessions.py`
- Test: `tests/test_cursor_sessions.py`

**Interfaces:**
- Consumes: `project_composer_ids`/`_parse_composer`/`_open_ro`(前序);`cache.get_session/put_session`、`sessions._freeze/_thaw`。
- Produces:
  - `_ids_by_file_overlap(gcon, root) -> set[str]`(文件兜底)
  - `scan_sessions(project_path, since_dt, cache=None) -> (list[summary], error_or_None)` — **与 sessions.scan_sessions 同契约**,永不抛异常。

- [ ] **Step 1: 写失败测试**
```python
# 追加到 tests/test_cursor_sessions.py
from vibetrace.cache import Cache

class TestScanSessions(unittest.TestCase):
    def _setup(self, t):
        user = Path(t) / "User"; user.mkdir()
        proj = Path(t) / "repo"; proj.mkdir()
        make_workspace(user, proj, ["cid"])
        make_global(user, "cid", [(1, "问题", 1000, ["a.py"]),
                                  (2, "回答" + "y" * 90, 2000, ["a.py"])])
        return user, proj

    def test_scan_returns_session_for_project(self):
        with tempfile.TemporaryDirectory() as t:
            user, proj = self._setup(t)
            with unittest.mock.patch.object(cs, "_USER_DIRS", [user]):
                out, err = cs.scan_sessions(proj, None, None)
            self.assertIsNone(err)
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0]["session_id"], "cid")
            self.assertIn("files_written", out[0])

    def test_no_cursor_dir_degrades(self):
        with unittest.mock.patch.object(cs, "_USER_DIRS",
                                        [Path("/nonexistent/x")]):
            out, err = cs.scan_sessions("/tmp/whatever", None, None)
        self.assertEqual(out, [])
        self.assertIsNotNone(err)

    def test_cache_incremental_hit(self):
        with tempfile.TemporaryDirectory() as t:
            user, proj = self._setup(t)
            cache = Cache(":memory:")
            with unittest.mock.patch.object(cs, "_USER_DIRS", [user]):
                cs.scan_sessions(proj, None, cache)          # 首次写缓存
                hit = cache.get_session("cid")
                self.assertIsNotNone(hit)
                out2, _ = cs.scan_sessions(proj, None, cache)  # 二次命中
            self.assertEqual(len(out2), 1)
```
> 文件顶部加 `import unittest.mock`(或 `from unittest import mock` 并相应改写)。

- [ ] **Step 2: 跑测试看失败**
Run: `python3 -m unittest tests.test_cursor_sessions.TestScanSessions -v`
Expected: FAIL — `AttributeError: scan_sessions`。

- [ ] **Step 3: 实现 scan_sessions(追加)**
```python
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
                n = gcon.execute("SELECT COUNT(*) FROM cursorDiskKV WHERE key LIKE ?",
                                 (f"bubbleId:{cid}:%",)).fetchone()[0]
                last = gcon.execute(
                    "SELECT value FROM cursorDiskKV WHERE key LIKE ? ",
                    (f"bubbleId:{cid}:%",)).fetchall()
                last_ms = 0
                for (raw,) in last:
                    try:
                        last_ms = max(last_ms, json.loads(raw).get("createdAt") or 0)
                    except (ValueError, TypeError):
                        continue
                cached = cache.get_session(cid) if cache else None
                if cached and cached["mtime"] == last_ms and cached["size"] == n:
                    s = _thaw(cached["summary"])
                else:
                    s = _parse_composer(gcon, cid, root)
                    if cache and s["records"]:
                        cache.put_session(
                            cid, s["end"].isoformat() if s["end"] else "",
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
```

- [ ] **Step 4: 跑测试看通过**
Run: `python3 -m unittest tests.test_cursor_sessions -v` — Expected: 全 PASS。

- [ ] **Step 5: 提交**
```bash
git add vibetrace/cursor_sessions.py tests/test_cursor_sessions.py
git commit -m "feat(cursor): scan_sessions(归属+文件兜底+since+增量缓存+容错)"
```

---

### Task 5: 首次启用一次性提示(sentinel)

**Files:**
- Modify: `vibetrace/cursor_sessions.py`
- Test: `tests/test_cursor_sessions.py`

**Interfaces:**
- Produces: `maybe_notice() -> None` — 首次启用 Cursor 源时向 stderr 打印一次本地优先告知,之后用 sentinel 文件抑制。
- Consumes: `config.VIBETRACE_DIR`。

- [ ] **Step 1: 写失败测试**
```python
# 追加到 tests/test_cursor_sessions.py
class TestNotice(unittest.TestCase):
    def test_notice_shown_once(self):
        with tempfile.TemporaryDirectory() as t:
            sentinel = Path(t) / ".cursor_notice_shown"
            with unittest.mock.patch.object(cs, "NOTICE_SENTINEL", sentinel):
                self.assertFalse(sentinel.exists())
                cs.maybe_notice()
                self.assertTrue(sentinel.exists())   # 首次创建
                cs.maybe_notice()                    # 第二次不报错、不重复
```

- [ ] **Step 2: 跑测试看失败**
Run: `python3 -m unittest tests.test_cursor_sessions.TestNotice -v`
Expected: FAIL — `AttributeError: NOTICE_SENTINEL`/`maybe_notice`。

- [ ] **Step 3: 实现(追加;文件顶部 import 处加 `from .config import VIBETRACE_DIR`)**
```python
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
```
> import 行调整为:`from .config import redact_secrets, VIBETRACE_DIR`。

- [ ] **Step 4: 跑测试看通过**
Run: `python3 -m unittest tests.test_cursor_sessions.TestNotice -v` — Expected: PASS。

- [ ] **Step 5: 提交**
```bash
git add vibetrace/cursor_sessions.py tests/test_cursor_sessions.py
git commit -m "feat(cursor): 首次启用一次性本地优先告知(sentinel)"
```

---

### Task 6: digest 集成 + cli `--source` 旗标

**Files:**
- Modify: `vibetrace/digest.py:12`(import)、`:66-70`(汇集点)、新增 `_sources` 辅助
- Modify: `vibetrace/cli.py:17-21`(digest 解析器加 `--source`)
- Test: `tests/test_cursor_digest.py`

**Interfaces:**
- Consumes: `cursor_sessions.scan_sessions/maybe_notice`(Task 4/5);`load_config()["sources"]`(Task 1);`args.source`(本任务新加)。
- Produces: `digest._sources(cfg, args) -> list[str]`;digest 在 `sources` 含 `"cursor"` 时把 Cursor 会话并入 `session_list`。

- [ ] **Step 1: 写失败测试**
```python
# tests/test_cursor_digest.py
import argparse, unittest
from unittest import mock
from vibetrace import digest

class TestSourcesResolve(unittest.TestCase):
    def test_default_claude_only(self):
        args = argparse.Namespace(source=None)
        self.assertEqual(digest._sources({"sources": ["claude"]}, args), ["claude"])

    def test_config_enables_cursor(self):
        args = argparse.Namespace(source=None)
        self.assertEqual(
            digest._sources({"sources": ["claude", "cursor"]}, args),
            ["claude", "cursor"])

    def test_cli_override_both(self):
        args = argparse.Namespace(source="both")
        self.assertEqual(set(digest._sources({"sources": ["claude"]}, args)),
                         {"claude", "cursor"})

    def test_cli_override_cursor_only(self):
        args = argparse.Namespace(source="cursor")
        self.assertEqual(digest._sources({"sources": ["claude"]}, args), ["cursor"])


class TestDigestMergesCursor(unittest.TestCase):
    def test_cursor_scan_called_when_enabled(self):
        # 仅验证启用时 digest 会调用 cursor_sessions.scan_sessions 合并(打桩,不跑真 LLM/git)
        called = {}
        def fake_scan(project_path, since_dt, cache=None):
            called["yes"] = True
            return [{"session_id": "cur1"}], None
        with mock.patch("vibetrace.cursor_sessions.scan_sessions", fake_scan), \
             mock.patch("vibetrace.cursor_sessions.maybe_notice", lambda: None):
            args = argparse.Namespace(source="cursor")
            self.assertEqual(digest._sources({"sources": ["claude"]}, args), ["cursor"])
            # _sources 决定启用;合并逻辑的端到端在 Task 0 smoke / 手动 dogfood 验证

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试看失败**
Run: `python3 -m unittest tests.test_cursor_digest -v`
Expected: FAIL — `AttributeError: _sources`。

- [ ] **Step 3: 实现 digest 集成**
`vibetrace/digest.py` 顶部 import 改:
```python
from . import align, cursor_sessions, enrich, gitlog, report, sessions
```
新增辅助(放在 `_shift` 之后):
```python
def _sources(cfg, args):
    """会话源:默认 config.sources;--source 覆盖(both=claude+cursor)。"""
    srcs = list(cfg.get("sources") or ["claude"])
    sel = getattr(args, "source", None)
    if sel == "both":
        return ["claude", "cursor"]
    if sel:
        return [sel]
    return srcs
```
把 `digest()` 内 line 66-70 替换为:
```python
    session_list, session_err = ([], None)
    srcs = _sources(cfg, args)
    if "claude" in srcs:
        session_list, session_err = sessions.scan_sessions(
            project_path, _since_to_dt(args.since), cache)
        if session_err:
            log.warning("会话层降级:%s", session_err)
    if "cursor" in srcs:
        cursor_sessions.maybe_notice()
        cur_list, cur_err = cursor_sessions.scan_sessions(
            project_path, _since_to_dt(args.since), cache)
        if cur_err:
            log.warning("Cursor 会话层降级:%s", cur_err)
        session_list = session_list + cur_list
    align.align(commits, session_list, project_path)
```

- [ ] **Step 4: cli 加 `--source` 旗标**
`vibetrace/cli.py` 在 digest 解析器(`dig.add_argument("--model", ...)` 之后)加:
```python
    dig.add_argument("--source", choices=["claude", "cursor", "both"],
                     help="会话源(默认按 config.sources;cursor 需 opt-in)")
```

- [ ] **Step 5: 跑测试看通过 + 全量**
Run: `python3 -m unittest tests.test_cursor_digest -v` — Expected: PASS。
Run: `python3 -m unittest discover -s tests` — Expected: OK(全绿)。

- [ ] **Step 6: 行数红线自检**
Run: `wc -l vibetrace/cursor_sessions.py vibetrace/digest.py vibetrace/cli.py`
Expected: 三者均 < 300。

- [ ] **Step 7: 提交**
```bash
git add vibetrace/digest.py vibetrace/cli.py tests/test_cursor_digest.py
git commit -m "feat(cursor): digest opt-in 合并 Cursor 会话 + cli --source"
```

---

## Self-Review
**1. Spec 覆盖:** opt-in(Task 1+6 ✓)· workspace 优先归属(Task 2 ✓)· 文件兜底(Task 4 ✓)· composer→session 映射含 type/文件/时间/脱敏/截断(Task 3 ✓)· since 过滤 + 增量缓存(Task 4 ✓)· 首次提示(Task 5 ✓)· digest 集成点(Task 6 ✓)· 容错降级(Task 2/3/4 各 try 兜底 ✓)· 只读 immutable(`_open_ro` ✓)· 同 sessions 契约(Task 3/4 summary 形状 ✓)· 测试用合成 fixture 不依赖真实 Cursor(✓)。
**2. 占位符扫描:** 无 TBD/“类似 Task N”;每步含完整代码与确切命令。
**3. 类型一致:** `scan_sessions(project_path, since_dt, cache=None)→(list,err)` 全程一致;summary 键集(session_id/title/prompts/excerpts/files_written/files_read/start/end/records/parse_failures/tokens)与 `sessions._freeze/_thaw` 期望一致;`_abs_files`/`_ms`/`_parse_composer`/`project_composer_ids` 签名在 Task 间一致。
**4. 开放项(spec 已记):** Linux/Win 路径未实测(代码兜底);非官方 schema 跨版本风险(全 `.get()` 防御);type 1/2 启发式(实现后用真实 Cursor 抽样二次核验 + 手动 dogfood:`vibetrace digest --source cursor --project <仓>`)。

## Execution Handoff
计划已存 `docs/superpowers/plans/2026-06-21-cursor-session-source.md`。两种执行方式:
1. **Subagent-Driven(推荐)**:逐任务派新 subagent + 两段审查,快。
2. **Inline**:本会话 executing-plans 批量执行 + 检查点。
