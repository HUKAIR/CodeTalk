# RepoWise vs vibetrace — honest comparison

Both mine architectural decisions from git history and ship MCP tools. Different trade-offs, complementary use cases.

## Where they differ

| | RepoWise | vibetrace |
|---|---|---|
| **Core method** | LLM-powered intelligence layers | Zero-LLM deterministic lookup by SHA |
| **Verification** | Evidence-backed (LLM-labeled verified/fuzzy) | Verbatim citations — click SHA to see original |
| **Scope** | Team-oriented (PR Bot, bus factor, multi-repo) | Single-developer, local-only |
| **Dependencies** | Python + LLM required | Pure stdlib, LLM optional (`--no-llm`) |
| **Data residency** | Configurable | Never leaves your machine (LLM calls opt-in) |
| **MCP tools** | 9 (graph, git, docs, decisions, code health) | 7 (ask, blame, search, graph, drift, prompts, adr) |
| **License** | AGPL-3.0 | — |

## Where they overlap

- ADR mining from git history
- Staleness / drift detection
- Decision provenance via MCP
- Local-first option

## When to use which

**Use RepoWise when:** you work in a team, want LLM-powered intelligence across multiple repos, need PR review bots, care about bus factor analysis.

**Use vibetrace when:** you want zero-LLM deterministic grounding you can verify yourself, work solo or want local-only data, need to prove "this is what was actually decided" (not "this is what AI thinks was decided").

**Use both:** RepoWise for team intelligence, vibetrace for personal provenance verification. They don't conflict — different MCP tool names, different data paths.

## What vibetrace does that RepoWise doesn't

- `vibetrace drift`: AI-tool-action vs git-commit deviation report ("said but didn't do")
- `vibetrace prompts`: replay your prompts to AI agents with soft-aligned commits
- `vibetrace review`: zero-LLM review-time grounding with line-level precision labels
- Blind test script: `python3 scripts/blind_test.py . 5` — reproducible proof that AI inference misses real decisions

## What RepoWise does that vibetrace doesn't

- Multi-repo workspaces
- Team features (PR Bot, bus factor, contributor graphs)
- Code health layer (complexity, test coverage gaps)
- 15 language support (vibetrace is language-agnostic via git, but RepoWise does deeper AST analysis)
- LLM-generated documentation from code
