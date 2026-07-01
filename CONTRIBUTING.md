# Contributing

Thanks for helping improve CodeTalk. The project is intentionally small and
local-first, so contributions should preserve that shape.

## Development Setup

```bash
git clone https://github.com/HUKAIR/CodeTalk
cd CodeTalk
python3 -m pip install -e ".[web]"
python3 -m unittest discover -s tests
```

For the VS Code extension:

```bash
cd vscode-codetalk
npm ci
npm run typecheck
npm run build
```

## Design Constraints

- Python 3.11+.
- The core package must stay standard-library only.
- Optional Anthropic support belongs behind the `anthropic` extra.
- The existing FastAPI/uvicorn web surface must stay isolated behind the `web`
  extra and lazy imports.
- Do not add LangGraph, vector databases, or new web frameworks.
- Route LLM calls through `codetalk/llm.py` so prompts, retries, token logging,
  and provider behavior stay centralized.
- External data parsing must degrade gracefully: warn, skip, or fall back rather
  than crashing on malformed JSONL, git data, or session records.
- Redact common API keys and tokens before writing cache or diagnostics.
- Keep modules under 300 lines. If a change would exceed that, split the work or
  discuss the design first.

## Commit Breadcrumbs

Commit bodies should capture important technical decisions:

```text
Vibe-Decision: <one-sentence decision, with rejected alternative if useful>
Vibe-Watch: <one-sentence uncertainty to verify later>
```

These exact prefixes are part of the product. CodeTalk reads them back to answer
"why was this code written this way?" with grounded evidence.

## Pull Request Checklist

- Run the smallest relevant tests first, then broaden if you touched shared
  behavior.
- For Python changes, run `python3 -m unittest discover -s tests` before merge.
- For extension changes, run `npm run typecheck` and `npm run build` in
  `vscode-codetalk`.
- If public commands, install steps, or packaging change, update README and the
  relevant release docs in the same PR.
- Keep the diff surgical. Avoid unrelated refactors or formatting churn.
