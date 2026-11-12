# Contributing

Thanks for helping improve CodeTalk. The project is intentionally small and
local-first, so contributions should preserve that shape.

## Workflow

Start with [the development and merge policy](docs/development.md): branches,
exact-SHA review, required checks, owner acceptance, integration and rollback.
Fork the repository and open a pull request against `main`. Test CI runs on every
PR; package publishing remains disabled. `main` is protected: the six required CI
checks must pass, and force pushes and branch deletion are blocked.

## Development Setup

```bash
git clone https://github.com/HUKAIR/CodeTalk
cd CodeTalk
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[web,test]"
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
- Never commit real home paths (write `~/`), real usernames, non-noreply email
  addresses, session IDs or content, screenshots with real data, or third-party
  logos. Git history cannot be taken back. List your own username and email,
  one per line, in the gitignored `.private/scan-markers.txt`, and install the
  pre-push gate once:

  ```bash
  printf '#!/bin/sh\nexec python3 -m scripts.scan_secrets --history\n' > .git/hooks/pre-push && chmod +x .git/hooks/pre-push
  ```

  The scanner cannot judge image content; reviewers check screenshots and logos.
- Keep modules under 300 lines. If a change would exceed that, split the work or
  discuss the design first.

## UI and documentation

Use [the synthetic review demo](docs/demo.md) for screenshots; do not capture your
real repository, sessions, usernames, or secrets. Verify image metadata with
`python -m unittest tests.test_release_privacy.PublicSourcePrivacyCase`.
Keep English and Chinese README entry paths consistent. Label illustrative
examples, shipped behavior, and unverified claims separately.

## Decision Notes

Commit bodies should capture important technical decisions:

```text
Vibe-Decision: <one-sentence decision and rationale>
Vibe-Rejected: <one-sentence alternative and why it was rejected>
Vibe-Watch: <one-sentence uncertainty to verify later>
```

These three exact, case-sensitive prefixes are part of the product. They record
what was chosen, what was deliberately not chosen, and what still needs to be
verified. CodeTalk reads them back to answer "why was this code written this
way?" with grounded evidence.

## Pull Request Checklist

- Run the smallest relevant tests first, then broaden if you touched shared
  behavior.
- For Python changes, run `python3 -m unittest discover -s tests` before merge.
- For extension changes, run `npm run typecheck` and `npm run build` in
  `vscode-codetalk`.
- If public commands, install steps, or packaging change, update README and the
  relevant release docs in the same PR.
- Keep the diff surgical. Avoid unrelated refactors or formatting churn.
