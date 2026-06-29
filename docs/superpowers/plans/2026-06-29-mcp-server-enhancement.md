# MCP Server Enhancement: Module Split + 3 New Tools + English + Annotations

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `mcp_server.py` to stay under 300-line cap, add 3 new MCP tools (drift/prompts/adr), switch all descriptions + errors to English, add `readOnlyHint` annotations, ship `.mcp.json.example`.

**Architecture:** Extract tool definitions + dispatch into new `mcp_tools.py`; thin `mcp_server.py` keeps only JSON-RPC serve loop + `run()`. New `drift.drift_json()` pure function for MCP-safe drift output. All 7 tools are read-only, zero-LLM-capable, exit-redacted.

**Tech Stack:** Python 3.11+ stdlib only. No new dependencies.

## Global Constraints

- M0: stdlib + anthropic SDK only (no new deps)
- M0: single module < 300 lines
- M0: data doesn't leave machine (exit redaction via `redact_secrets`)
- MCP spec: 2025-11-25 (stdio, newline-delimited JSON-RPC)
- All tool output goes through `_ok_content` / `_err_content` (exit redaction)
- All tools are read-only (`annotations.readOnlyHint: true`)

---

### Task 1: Extract `mcp_tools.py` from `mcp_server.py`

**Files:**
- Create: `vibetrace/mcp_tools.py`
- Modify: `vibetrace/mcp_server.py`
- Test: `tests/test_mcp_server.py` (existing tests must still pass)

**Interfaces:**
- Produces: `mcp_tools.TOOLS` (list of tool dicts), `mcp_tools.call_tool(name, arguments, cache, cfg, llm, default_project, stderr)` → content dict
- Produces: `mcp_tools.resolve_target(arguments)` → str|None, `mcp_tools.project_path(arguments, default_project, stderr)` → Path

- [ ] **Step 1: Create `vibetrace/mcp_tools.py`** with the 4 existing tool definitions (`_TOOLS`), `_ok_content`, `_err_content`, `_project_path`, `_resolve_target`, `_call_tool` — moved verbatim from `mcp_server.py`. Rename private `_TOOLS` → `TOOLS`, `_call_tool` → `call_tool`, `_project_path` → `project_path`, `_resolve_target` → `resolve_target` (they're now module public). Keep `_ok_content` / `_err_content` private (internal helpers).

- [ ] **Step 2: Update `vibetrace/mcp_server.py`** to import from `mcp_tools` instead of defining inline. Remove the moved code. `_handle` calls `mcp_tools.call_tool(...)` and references `mcp_tools.TOOLS`. Keep `_err`, `_result`, `_handle`, `serve`, `_write`, `run` in `mcp_server.py`.

- [ ] **Step 3: Run existing tests**

Run: `python3 -m pytest tests/test_mcp_server.py -v`
Expected: All 20+ tests PASS (no behavior change)

- [ ] **Step 4: Verify line counts**

Run: `wc -l vibetrace/mcp_server.py vibetrace/mcp_tools.py`
Expected: both < 300 lines

- [ ] **Step 5: Commit**

```
git add vibetrace/mcp_server.py vibetrace/mcp_tools.py
git commit -m "refactor(mcp): extract tool definitions to mcp_tools.py (300-line cap)"
```

---

### Task 2: English descriptions + error messages + annotations on existing 4 tools

**Files:**
- Modify: `vibetrace/mcp_tools.py`
- Test: `tests/test_mcp_server.py` (update assertions that check Chinese strings)

**Interfaces:**
- Consumes: `mcp_tools.TOOLS` (from Task 1)
- Produces: same shape, English strings, + `annotations` key on each tool

- [ ] **Step 1: Rewrite 4 tool descriptions to English** in `TOOLS` list. Each description should emphasize: zero-LLM / deterministic / real commit history / verbatim citations. Keep under 200 chars each.

- [ ] **Step 2: Add `annotations` to each tool**

```python
"annotations": {"title": "vibetrace ask", "readOnlyHint": True,
                "destructiveHint": False, "openWorldHint": False}
```

- [ ] **Step 3: Change all Chinese error strings in `call_tool` to English**

Replace:
- `"未知工具：{name}"` → `"Unknown tool: {name}"`
- `"arguments 必须是对象(JSON object)"` → `"arguments must be a JSON object"`
- `"缺少必填参数：{'、'.join(missing)}"` → `"Missing required parameter(s): {', '.join(missing)}"`
- `"缺少 target(或 path[+startLine/endLine])"` → `"Missing target (or path[+startLine/endLine])"`
- `"{file} 没有可用的提交历史,无从溯源。"` → `"No commit history for {file}"`
- `"工具内部错误：{exc}"` → `"Internal tool error: {exc}"`

- [ ] **Step 4: Update test assertions** that check for Chinese error substrings → English equivalents.

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/test_mcp_server.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```
git add vibetrace/mcp_tools.py tests/test_mcp_server.py
git commit -m "feat(mcp): English descriptions + error messages + readOnlyHint annotations"
```

---

### Task 3: Add `drift_json()` to `drift.py`

**Files:**
- Modify: `vibetrace/drift.py`
- Create: `tests/test_drift_json.py`

**Interfaces:**
- Consumes: `drift.drift_rows()` (existing pure function)
- Produces: `drift.drift_json(project, since="7 days ago")` → JSON string

- [ ] **Step 1: Write failing test**

```python
# tests/test_drift_json.py
import json, tempfile, subprocess, unittest
from pathlib import Path
from vibetrace.drift import drift_json

class TestDriftJson(unittest.TestCase):
    def _git(self, cwd, *args):
        subprocess.run(["git", *args], cwd=cwd, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def test_returns_valid_json_with_keys(self):
        with tempfile.TemporaryDirectory() as t:
            repo = Path(t) / "r"; repo.mkdir()
            self._git(repo, "init"); self._git(repo, "config", "user.email", "t@t")
            self._git(repo, "config", "user.name", "t")
            (repo / "a.py").write_text("x=1\n")
            self._git(repo, "add", "."); self._git(repo, "commit", "-m", "init")
            result = drift_json(str(repo))
            data = json.loads(result)
            self.assertIn("flagged", data)
            self.assertIsInstance(data["flagged"], list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_drift_json.py -v`
Expected: ImportError (drift_json not defined yet)

- [ ] **Step 3: Implement `drift_json` in `drift.py`**

```python
def drift_json(project, since="7 days ago"):
    """MCP-safe JSON output: assemble commits+sessions → drift_rows → JSON string."""
    pp = Path(project).resolve()
    commits, err = gitlog.collect_commit_files(pp)
    if err:
        return json.dumps({"error": err, "flagged": []})
    cfg = load_config()
    cache = Cache(CACHE_DB_PATH)
    try:
        sess, serr = sessions.scan_sessions(pp, _since_to_dt(since), cache)
    finally:
        cache.close()
    all_fw = set()
    for s in sess:
        all_fw |= _relative_files(s, pp)
    exclude = _ignored(all_fw, pp)
    flagged = [r for r in drift_rows(commits, sess, pp, exclude=exclude)
               if r["missing"]]
    return json.dumps({"flagged": flagged, "session_count": len(sess),
                       "warning": serr or None}, ensure_ascii=False)
```

Add `import json` at top of drift.py; import `Cache, CACHE_DB_PATH` from config/cache (already used by drift_cmd pattern).

- [ ] **Step 4: Run test**

Run: `python3 -m pytest tests/test_drift_json.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```
git add vibetrace/drift.py tests/test_drift_json.py
git commit -m "feat(drift): add drift_json() for MCP-safe JSON output"
```

---

### Task 4: Register 3 new tools in `mcp_tools.py` + dispatch

**Files:**
- Modify: `vibetrace/mcp_tools.py`
- Modify: `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: `drift.drift_json(project, since)`, `prompts_view.build_prompts_view(sessions, commits, project_path)`, `adr_export.export(project, target, fmt)`
- Produces: 3 new entries in `TOOLS`, dispatch in `call_tool`

- [ ] **Step 1: Add 3 tool definitions to `TOOLS`**

```python
{"name": "vibetrace_drift",
 "description": "Deviation report: AI tool actions vs actual git commits (zero-LLM, deterministic). "
                "Shows files the AI edited but never committed — catches 'said but didn't do'.",
 "inputSchema": {"type": "object", "properties": {
     "since": {"type": "string", "description": "Time window, e.g. '7 days ago' (default)"},
     "project": {"type": "string", "description": "Project path (default: cwd)"}},
     "required": []},
 "annotations": {"title": "vibetrace drift", "readOnlyHint": True,
                  "destructiveHint": False, "openWorldHint": False}},

{"name": "vibetrace_prompts",
 "description": "Replay your prompts to AI coding agents (zero-LLM, local). "
                "Shows what you asked the AI to do, with soft-aligned commits. "
                "Use when you forgot what you told the AI earlier today.",
 "inputSchema": {"type": "object", "properties": {
     "since": {"type": "string", "description": "Time window, e.g. '1 day ago' (default: '7 days ago')"},
     "project": {"type": "string", "description": "Project path (default: cwd)"}},
     "required": []},
 "annotations": {"title": "vibetrace prompts", "readOnlyHint": True,
                  "destructiveHint": False, "openWorldHint": False}},

{"name": "vibetrace_adr",
 "description": "Export an Architecture Decision Record from real git history (zero-LLM). "
                "Auto-generates MADR/Nygard ADR with verbatim commit citations for a file/line range.",
 "inputSchema": {"type": "object", "properties": {
     "target": {"type": "string", "description": "File or file:start-end, e.g. vibetrace/llm.py:72-78"},
     "path": {"type": "string", "description": "GitHub-MCP style file path (alias for target)"},
     "startLine": {"type": "integer", "description": "Start line (with path)"},
     "endLine": {"type": "integer", "description": "End line (with path)"},
     "format": {"type": "string", "enum": ["madr", "nygard"], "description": "ADR format (default: madr)"},
     "project": {"type": "string", "description": "Project path (default: cwd)"}},
     "required": []},
 "annotations": {"title": "vibetrace adr", "readOnlyHint": True,
                  "destructiveHint": False, "openWorldHint": False}},
```

- [ ] **Step 2: Add dispatch branches in `call_tool`**

For drift: call `drift_json(str(pp), arguments.get("since", "7 days ago"))`.
For prompts: assemble sessions + commits + align → `build_prompts_view`.
For adr: resolve target → call `export(str(pp), target, fmt)`.

- [ ] **Step 3: Add imports** at top of `mcp_tools.py`:

```python
from .drift import drift_json
from .prompts_view import build_prompts_view
from .adr_export import export as adr_export
```

Prompts also needs: `from . import sessions, gitlog; from .align import align; from .digest import _since_to_dt`

- [ ] **Step 4: Write tests for 3 new tools** in `tests/test_mcp_server.py`:

Each tool: (a) mock the underlying function → verify `isError: false` + content, (b) missing required param → `isError: true`.

- [ ] **Step 5: Update `test_lists_four_tools` → `test_lists_seven_tools`**, verify all 7 names + annotations present.

- [ ] **Step 6: Verify line counts**

Run: `wc -l vibetrace/mcp_server.py vibetrace/mcp_tools.py`
Expected: both < 300 lines

- [ ] **Step 7: Run full test suite**

Run: `python3 -m pytest tests/test_mcp_server.py tests/test_drift_json.py -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```
git add vibetrace/mcp_tools.py tests/test_mcp_server.py
git commit -m "feat(mcp): add drift/prompts/adr tools (7 total, all zero-LLM)"
```

---

### Task 5: Documentation + `.mcp.json.example`

**Files:**
- Create: `.mcp.json.example`
- Modify: `docs/mcp-install.md`

- [ ] **Step 1: Create `.mcp.json.example`**

```json
{
  "mcpServers": {
    "vibetrace": {
      "command": "python3",
      "args": ["-m", "vibetrace", "mcp-serve", "--project", "/absolute/path/to/your/repo"]
    }
  }
}
```

- [ ] **Step 2: Update tool table in `docs/mcp-install.md`** from 4 rows to 7:

Add drift, prompts, adr with one-line descriptions + LLM column.

- [ ] **Step 3: Add note** about `.mcp.json` in repo being local dev convenience, point to `.mcp.json.example` as the template.

- [ ] **Step 4: Commit**

```
git add .mcp.json.example docs/mcp-install.md
git commit -m "docs(mcp): 7-tool reference table + .mcp.json.example template"
```
