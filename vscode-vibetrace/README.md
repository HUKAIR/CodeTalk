# vibetrace — Inline Decision Blame

Hover any line to see **why** it was written that way. Real commit decisions, not AI guesses.

Like GitLens but for "why", not just "who/when". One extension covers VS Code, Cursor, and Windsurf.

## What you see

**Inline annotations** (line end, gray italic):
```
const cache = new Map()   a1b2c3d · 用 Map 不引 LRU 依赖
```

**Hover card** (full decision context):
```
[a1b2c3d] 2026-06-29 · refactor cache layer

Why: Map 够用, LRU 增加复杂度但此场景无淘汰需求

Decisions:
- 用 Map 不引 LRU 依赖

Rejected:
- lru-cache 包(M0 禁三方依赖)

Tests:
- tests/test_cache.py — test_map_lookup, test_invalidation

---
`git show a1b2c3d` · vibetrace blame
```

Only lines with real decisions/why get annotated. Consecutive lines from the same commit only show once.

## Prerequisites

- Python >= 3.11
- `pip install -e .` (or `pip install vibetrace`) in the project root
- The project has been enriched: `vibetrace enrich --project /path/to/repo`
  (gives vibetrace commit narratives to display; without this, only `Vibe-Decision` breadcrumbs show)

## Install

```bash
# 1. Build
cd vscode-vibetrace
npm install
npm run build

# 2. Package
npx @vscode/vsce package --no-dependencies
# -> vscode-vibetrace-0.1.0.vsix

# 3. Install (pick your editor)
cursor --install-extension vscode-vibetrace-0.1.0.vsix
# or: code --install-extension vscode-vibetrace-0.1.0.vsix
# or: Windsurf -> Extensions -> Install from VSIX -> select file

# 4. Reload
# Cmd+Shift+P -> "Reload Window"
```

If `cursor` / `code` command is not found, use the full path:
```bash
# macOS Cursor:
/Applications/Cursor.app/Contents/Resources/app/bin/cursor --install-extension vscode-vibetrace-0.1.0.vsix

# macOS VS Code:
"/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code" --install-extension vscode-vibetrace-0.1.0.vsix
```

Or install from the command palette: Cmd+Shift+P -> "Extensions: Install from VSIX..."

## Configuration

| Setting | Type | Default | Purpose |
|---|---|---|---|
| `vibetrace.enabled` | boolean | `true` | Master toggle. Turning off immediately clears annotations. |
| `vibetrace.pythonPath` | string | `"python3"` | Python interpreter with vibetrace installed. Use absolute path if the default doesn't find vibetrace. |

Settings live in VS Code/Cursor settings (Cmd+,). No other config needed.

## How it works

1. You open a file
2. Extension runs `vibetrace blame <file> --json --project <workspace>` (zero-LLM, local-only)
3. Extension runs `git blame --porcelain <file>` to map each line to its SHA
4. Lines whose commit has decision data get an inline annotation
5. Hovering shows the full decision card (why / decisions / rejected / risks / tests / PR context)

Data is cached per-file in memory. Cache refreshes on file save or editor switch.

## Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| No annotations appear | vibetrace not installed, or no enriched data | Run `vibetrace enrich --project .` then reopen the file |
| "python3: command not found" in background | Default python3 not in VS Code's PATH | Set `vibetrace.pythonPath` to absolute path (e.g. `/opt/homebrew/bin/python3`) |
| Annotations don't update after commit | File cache stale | Save the file (Cmd+S) to trigger refresh |
| Annotations on wrong lines | File modified since last commit | Save + commit first, then reopen |

## Architecture

```
extension.ts (249 lines)
├── fetchBlameData()     — shell out to vibetrace + git blame
├── applyDecorations()   — DecorationProvider (inline line-end text)
├── buildHoverCard()     — HoverProvider (markdown card)
├── segmentHasWhy()      — filter: only lines with real decisions
└── activate/deactivate  — lifecycle + event subscriptions
```

Single file, esbuild bundle (~8KB), no WebView, no React, no panel.

## Limitations (v0.1)

- No CodeLens, no gutter icons, no side panel
- No Marketplace publishing (manual .vsix install)
- `git blame` maps lines to the **last** commit that touched them — older decisions on unchanged lines won't appear
- vibetrace returns at most 12 recent commits per file (LINE_LOG_LIMIT) — very long-lived files may have gaps
- Multi-root workspaces use only the first folder
