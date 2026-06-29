# VS Code Extension: Inline Decision Blame

## Goal

VS Code extension that shows real decision history inline — like GitLens but for "why", not just "who/when". Inline annotation at line end + hover card with full decision record. Covers VS Code + Cursor + Windsurf (VS Code forks).

## Architecture

**Backend:** Shell out to `vibetrace blame <file> --json --project <root>`. One call per file, cached in memory. Line-to-SHA mapping via `git blame --porcelain`.

**Frontend:** Single `extension.ts` — DecorationProvider for inline annotations, HoverProvider for expanded cards. No WebView, no React, no panel.

**Build:** esbuild single-file bundle. Independent directory `vscode-vibetrace/`, not part of `pip install vibetrace`.

## File Structure

```
vscode-vibetrace/
├── package.json          # Extension manifest
├── tsconfig.json         # TypeScript config
├── esbuild.mjs           # Single-file bundle script
├── src/
│   └── extension.ts      # All logic: activate, blame provider, hover, decoration
├── .vscodeignore
└── README.md
```

Python side: add `--json` flag to `vibetrace blame` (~10 lines).

## Data Flow

1. User opens/switches file
2. Extension runs `vibetrace blame <file> --json --project <workspaceRoot>`
3. Parses JSON: `[{sha, date, subject, why, decisions, risks, rejected, evidence, ...}]`
4. Runs `git blame --porcelain <file>` to map lines → SHA
5. Matches line SHAs to vibetrace segments
6. DecorationProvider: line-end gray text `sha7 · decisions[0]` (max 80 chars)
7. On hover: HoverProvider builds markdown card from cached segment

## Display Rules

**Inline annotation:**
- Format: `sha7 · decisions[0]` truncated to 80 chars
- Color: `editorInlayHint.foreground` (follows theme)
- Only on lines where `segment_has_why(seg)` is true (has why or decisions)
- Consecutive lines with same SHA: only show on first line

**Hover card (markdown):**

```
**[sha7]** date · subject

**Why:** ...

**Decisions:**
- ...

**Rejected:** (if any)
- ...

**Risks:** (if any)
- ...

---
`git show sha` · vibetrace blame
```

Bottom `git show` is a clickable command link to run in terminal.

## Configuration

| Setting | Type | Default | Purpose |
|---|---|---|---|
| `vibetrace.enabled` | boolean | `true` | Master toggle |
| `vibetrace.pythonPath` | string | `"python3"` | Python interpreter path |

No other config. Hardcode everything until someone asks.

## Activation

- `onStartupFinished` — not `*` (too early), not `onLanguage` (blame is language-agnostic)
- On activate: check `git rev-parse --git-dir` in workspace — if not a git repo, silently exit
- On deactivate: dispose decorations + kill pending child processes

## Caching

- Per-file, in memory (Map<filePath, BlameData>)
- Invalidated on: file save, active editor change
- No persistent cache, no disk writes

## Python Side Change

Add `--json` flag to `vibetrace blame`:
- `cli.py`: `blm.add_argument("--json", action="store_true")`
- `blame.py`: `blame()` gains `json_output` param — `collect_segments` → `json.dumps` → `redact_secrets` → print
- `commands.py`: pass `json_output=getattr(args, "json", False)` to `blame()`
- Exit redaction: JSON output goes through `redact_secrets` (same as MCP)
- Test: one case verifying `--json` returns valid JSON with expected keys

## Constraints

- M0 red line: extension is independent from core `vibetrace/` package (no cross-import)
- Zero new Python dependencies
- esbuild only (no webpack/rollup)
- Target: `extension.ts` ~200-300 lines
- VS Code engine: `^1.85.0` (stable API only, no proposed)

## Out of Scope (v1)

- CodeLens
- Side panel / TreeView
- File-level decision summary
- Auto-enrich (running `vibetrace enrich` from extension)
- Marketplace publishing (manual `.vsix` install first)
