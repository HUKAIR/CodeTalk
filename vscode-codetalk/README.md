# CodeTalk — Decision Blame

See **why** code was written this way. Foldable CodeLens with real commit decisions + hover cards.

Like GitLens but for "why", not just "who/when". One extension covers VS Code, Cursor, and Windsurf.

## What you see

**CodeLens** (foldable, above each commit block):
```
▸ a1b2c3d · 决策(2) 风险(1)          ← click to expand
def blame(project_path, target):
    ...
```

Expanded:
```
▾ a1b2c3d · 2026-06-21 · refactor cache layer
    Why: Map 够用, LRU 增加复杂度...
    决策: 用 Map 不引 LRU 依赖
    决策: blame 只如实罗列不综合
    风险: 并发安全待验证
def blame(project_path, target):
    ...
```

Click any expanded line to collapse. Commands: `codetalk: Expand All Decisions` / `codetalk: Collapse All Decisions` (Cmd+Shift+P).

**Hover card** (on any line — full context with tests, PR refs, `git show` link):
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
`git show a1b2c3d` · codetalk blame
```

Only blocks with real decisions/why get CodeLens. Hover works on any line.

## Prerequisites

- Python >= 3.11
- `pip install -e .` (or `pip install codetalk`) in the project root
- The project has been enriched: `codetalk enrich --project /path/to/repo`
  (gives CodeTalk commit narratives to display; without this, only `Vibe-Decision` breadcrumbs show)

## Install

```bash
# 1. Build
cd vscode-codetalk
npm install
npm run build

# 2. Package
npx @vscode/vsce package --no-dependencies
# -> vscode-codetalk-0.2.0.vsix

# 3. Install (pick your editor)
cursor --install-extension vscode-codetalk-0.2.0.vsix
# or: code --install-extension vscode-codetalk-0.2.0.vsix
# or: Windsurf -> Extensions -> Install from VSIX -> select file

# 4. Reload
# Cmd+Shift+P -> "Reload Window"
```

If `cursor` / `code` command is not found, use the full path:
```bash
# macOS Cursor:
/Applications/Cursor.app/Contents/Resources/app/bin/cursor --install-extension vscode-codetalk-0.2.0.vsix

# macOS VS Code:
"/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code" --install-extension vscode-codetalk-0.2.0.vsix
```

Or install from the command palette: Cmd+Shift+P -> "Extensions: Install from VSIX..."

## Configuration

| Setting | Type | Default | Purpose |
|---|---|---|---|
| `codetalk.enabled` | boolean | `true` | Master toggle. Turning off immediately clears CodeLens entries. |
| `codetalk.pythonPath` | string | `"python3"` | Python interpreter with CodeTalk installed. Use absolute path if the default doesn't find codetalk. |

Settings live in VS Code/Cursor settings (Cmd+,). No other config needed.

## How it works

1. You open a file
2. Extension runs `codetalk blame <file> --json --project <workspace>` (zero-LLM, local-only)
3. Extension runs `git blame --porcelain <file>` to map each line to its SHA
4. Commits with decision data get a foldable CodeLens entry
5. Hovering shows the full decision card (why / decisions / rejected / risks / tests / PR context)

Data is cached per-file in memory. Cache refreshes on file save or editor switch.

## Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| No CodeLens entries appear | CodeTalk not installed, or no enriched data | Run `codetalk enrich --project .` then reopen the file |
| "python3: command not found" in background | Default python3 not in VS Code's PATH | Set `codetalk.pythonPath` to absolute path (e.g. `/opt/homebrew/bin/python3`) |
| Annotations don't update after commit | File cache stale | Save the file (Cmd+S) to trigger refresh |
| Annotations on wrong lines | File modified since last commit | Save + commit first, then reopen |

## Architecture

```
extension.ts
├── fetchBlameData()           — shell out to CodeTalk + git blame
├── CodetalkCodeLensProvider  — foldable per-commit CodeLens
├── buildHoverCard()           — HoverProvider markdown card
├── segmentHasWhy()            — filter: only commits with real decisions
└── activate/deactivate        — lifecycle + event subscriptions
```

Single TypeScript file, esbuild bundle, no WebView, no React, no panel.

## Limitations (v0.2)

- No gutter icons, no side panel
- No Marketplace publishing (manual .vsix install)
- `git blame` maps lines to the **last** commit that touched them — older decisions on unchanged lines won't appear
- CodeTalk returns at most 50 recent line/file-history commits (LINE_LOG_LIMIT) — very long-lived files may have gaps
- Multi-root workspaces use only the first folder
