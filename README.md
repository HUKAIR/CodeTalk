<p align="center">
  <a href="README.md"><b>English</b></a> · <a href="README.zh-CN.md">简体中文</a>
</p>

<p align="center">
  <img src="docs/images/codetalk-logo-banner.png" alt="CodeTalk logo banner" width="820">
</p>

<p align="center">
  <strong>Zero-LLM core · Real citations · Local cache · MCP / CLI / VS Code</strong>
</p>

**AI writes your code. Three months later, nobody knows why it was written that way.**

CodeTalk grounds "why" in real commit history — verbatim citations you can click and verify, not AI confabulation. Zero-LLM, local-only, pure stdlib.

---

### Why this matters

- **Trust is collapsing.** 46% of developers actively distrust AI output; only 3% highly trust it. *(Stack Overflow 2025, N=33,244)*
- **AI "explanations" are fabricated.** We blind-tested 5 real commits: AI inferred "why" from diffs alone — **5/5 missed the real decisions, 2/5 completely wrong.** *(This repo, reproducible: `python3 scripts/blind_test.py . 5`)* — or run the shareable A/B blind test on your own repo and judge for yourself: `python3 scripts/trust_ab_demo.py . 5` (real records vs diff-only inference, side by side, reveal at the end; add `--html demo.html` for an interactive shareable page).
- **Your chat history is fragile.** Multiple bug reports across Cursor, Claude Code, and Copilot describe conversations silently vanishing — data still on disk, UI can't surface it. One confirmed Cursor case (~175 agent chats hidden while intact on disk) is written up in `docs/moat-real-records-vs-inference.md`.

### How CodeTalk is different

| | AI inference (Cursor/Copilot) | CodeTalk |
|---|---|---|
| Source | current diff | real commit + session transcript |
| Method | LLM guesses from code | zero-LLM deterministic lookup by SHA |
| Verifiable | no — plausible but ungrounded | yes — click SHA to see original |
| Data | sent to cloud | local-first; LLM calls opt-in (`--no-llm` for zero egress) |

## Pipeline

CodeTalk is a local evidence pipeline. It reads git history and AI coding
session files, parses them defensively, aligns sessions to commits, stores
redacted evidence in a local SQLite cache, then exposes deterministic tools for
`ask`, `blame`, `search`, `review`, `drift`, `graph`, `prompts`, and `adr-export`.
LLM synthesis is optional and sits behind the evidence layer.

![CodeTalk pipeline](docs/images/codetalk-pipeline.png)

### What These Terms Mean

- **Decision notes** (called breadcrumbs internally) are two optional lines in a
  git commit message: `Vibe-Decision: ...` for the reason behind a change, and
  `Vibe-Watch: ...` for a risk to check later. They are stored in git, can be
  written by a person, a git hook, or an AI coding agent, and CodeTalk reads them
  in `blame`, `ask`, `graph`, and `digest`.
- **`enrich`** is optional backfill for old commits. It asks an LLM to read a
  commit plus nearby local session snippets, then stores a redacted narrative in
  `~/.codetalk/cache.db` under that commit SHA. Use it when old commits do not
  already have decision notes.
- **Grounding evidence** is the material CodeTalk can cite: commit messages,
  `Vibe-Decision` / `Vibe-Watch` lines, and local session transcript excerpts.
  If there is no evidence, CodeTalk should fall back to listing what it found,
  not inventing an answer.
- **Zero-LLM / zero egress** means CodeTalk only does local deterministic lookup.
  `--no-llm` also disables optional model calls, so project data stays on your
  machine.
- **Time capsule** means a `Vibe-Watch` line is brought back in a future report
  so you can check whether the risk actually happened.
- **MCP** is the protocol CodeTalk uses to expose its commands inside AI coding
  clients such as Claude Code, Cursor, and Codex.
- **Understanding debt** is CodeTalk's priority list of files or decisions that
  deserve a reread because they changed recently, carried risks, or have not
  been reviewed.

> **Honest boundaries:** Blind test is N=5, this repo only, human-judged — not a population claim. Coverage depends on decision notes + `enrich`: a fresh clone of this repo reproduces **~59% real grounding (114/194 commits — verbatim breadcrumbs + session anchors only, excluding LLM-generated narratives, measured 2026-07-02)** — run `python3 scripts/grounding_hitrate.py .` for the live number (it stars the real-grounding rate; the LLM-narrative-inclusive upper bound is printed below it and is *not* used as a trust claim). After a full `codetalk enrich` backfill the looser coverage reaches ~100%. A separate 605-commit repo **without** enrich starts at 0.3%, reaching ~100% after `codetalk enrich`. Without enrich or decision notes, blame shows commit subjects only — similar to `git log`. Run `grounding_hitrate.py` on your own repo to measure. CodeTalk finds "what was actually said and decided", not "whether the code is correct" — source records themselves may be wrong. Coverage numbers are reproducible with `grounding_hitrate.py` on any repo; blind-test method: `python3 scripts/blind_test.py`; moat comparison write-up: `docs/moat-real-records-vs-inference.md`.

## See it work in 30 seconds

```bash
git clone https://github.com/HUKAIR/CodeTalk && cd CodeTalk && pip install -e .

# This repo uses CodeTalk on itself — most commits carry decision notes
# (Vibe-Decision / Vibe-Watch lines in the commit message; 101/183 so far).
# No API key, no config, no enrich:
codetalk doctor

# Then inspect real decisions straight from git history:
codetalk blame codetalk/cache.py
```

For every commit that carries decision notes, you'll see: the **why**, the **decisions made**, the **alternatives rejected** — verbatim from the commit record, zero LLM. Commits without notes show their subject only. That's the whole pitch in one command.

## On your own repo

```bash
# Step 0 — see coverage, local session availability, and the best next command:
codetalk doctor --project /path/to/repo

# Step 1 — decision notes already in your history? blame works immediately, zero key:
codetalk blame yourfile.py --project /path/to/repo

# Step 2 — for full narratives on a repo without decision notes (needs an LLM key):
codetalk init                              # write config, fill your API key
codetalk enrich --project /path/to/repo    # backfill decision narratives from git+sessions

# Step 3 — make future commits self-document (zero extra effort, no key):
codetalk install-agent-seed --project .    # your AI agent leaves Vibe-Decision notes
```

**Honest cold-start:** a repo with no decision notes and no `enrich` shows commit subjects only — like `git log`. The value comes from decision notes (free, in git) or `enrich` (needs a key). This repo has both, which is why the 30-second demo above is rich. Yours starts empty and fills as you use it.

## Install

```bash
pip install -e .                 # Core: pure standard library, zero third-party dependencies
pip install -e ".[anthropic]"    # Optional: only needed for the anthropic provider
```

Requires Python ≥ 3.11. After installing you get the `codetalk` command (equivalent to `python3 -m codetalk`).

## One-click MCP install (.mcpb)

Expose the zero-LLM grounding capability to MCP clients such as Claude Code / Cursor / Codex, so you can ask "why was this code written this way" right inside your agent workflow. CodeTalk is pure standard library with zero third-party dependencies, so it packs into a single `.mcpb` (a zip of `manifest.json` + source), giving you a **one-click install and a single build that covers every client**. It runs on the `python3` you already have installed and **does not bundle an interpreter**:

```bash
python3 -m scripts.build_mcpb     # produces codetalk.mcpb
```

Drag `codetalk.mcpb` into your client's extension-install entry point, and pick a project root during installation. It exposes **7 tools** (all marked `readOnlyHint: true`, so Claude Code / Cursor can auto-approve them without a confirmation prompt):

| Tool | Purpose | LLM |
|---|---|---|
| `codetalk_ask` | Grounded question "why was this written" | Uses LLM if a key is set; falls back to deterministic without one |
| `codetalk_blame` | Line-level decision provenance | Zero LLM |
| `codetalk_graph` | Decision-impact graph (timeline DAG) | Zero LLM |
| `codetalk_search` | Topic-level "why" retrieval | Zero LLM |
| `codetalk_drift` | Drift self-check: files AI changed but never committed | Zero LLM |
| `codetalk_prompts` | Instruction recall: what you told the AI to do | Zero LLM |
| `codetalk_adr` | ADR export: MADR / Nygard / CycloneDX (AIBOM) | Zero LLM |

> Step-by-step install, self-check, and troubleshooting per client: **[`docs/mcp-install.md`](docs/mcp-install.md)**.
> Spec-driven workflow integrations (GitHub Spec Kit / AWS Kiro / OpenSpec / Antigravity):
> **[`docs/spec-kit-integration.md`](docs/spec-kit-integration.md)**.

## IDE Extension (VS Code / Cursor / Windsurf)

Foldable decision CodeLens + hover cards — see **why** a line was written that way, with real commit citations. Like GitLens but for decisions, not just authorship.

```bash
cd vscode-codetalk
npm install && npm run build                        # build
npx @vscode/vsce package --no-dependencies          # package the .vsix
```

Install (pick one):

```bash
cursor --install-extension vscode-codetalk-0.2.0.vsix   # Cursor
code --install-extension vscode-codetalk-0.2.0.vsix      # VS Code
# Windsurf: Extensions → Install from VSIX → pick the file
```

After installing, run Cmd+Shift+P → **Reload Window**, then open a project that has a CodeTalk cache to see the expandable decision CodeLens; hover a line to view the full card.

| Setting | Default | Description |
|---|---|---|
| `codetalk.enabled` | `true` | Master switch |
| `codetalk.pythonPath` | `"python3"` | Path to the Python interpreter that has CodeTalk installed |

> Detailed install + troubleshooting + configuration: **[`vscode-codetalk/README.md`](vscode-codetalk/README.md)**.

## codetalk web — self-hosted grounded conversation (new)

A local-first interactive web page: hold a multi-turn discussion with an LLM about "why was this code written this way", but on every turn it **first runs a zero-LLM retrieval over your project's real records** (commit narratives / decision notes / verbatim session transcripts), feeds that real evidence to the model, and puts **side-by-side verifiable citations** next to the answer. The discussion itself is redacted before being stored, feeding back into future `ask` / `search`. **Self-hosted = your data stays on your own machine; we sell software, not a service.**

```bash
pip install -e ".[web]"                            # optional web extra (FastAPI/uvicorn; CLI/MCP stay pure stdlib)
codetalk web --project /path/to/repo              # binds 127.0.0.1, auto-opens the browser, verbatim streaming
codetalk web --project /path/to/repo --no-llm     # zero egress: falls back to a zero-LLM grounded listing
```

- **Grounded and verifiable**: answers are anchored to real commits / decisions / verbatim session transcripts, and the citation next to each conclusion can be clicked to verify — this is the line that separates it from a "chat wrapper"; **the model won't answer when detached from real material** (empty material → the model isn't called, just a deterministic listing). Each commit citation carries a **`diff ▾`** button that opens the real `git show` in-browser (zero-LLM, local) — the "click the SHA to verify" loop, now in the web UI.
- **All views are browser-reachable**: besides `/` (chat), the server serves `/console` (unified console), `/tunnel` (timeline), `/graph` (decision-impact DAG), and `/course` (evolution course) — the same rich views the CLI writes as static files. A header **EN / 中文** toggle switches the whole UI language (persisted locally; defaults to the browser language).
- **Privacy red lines**: by default it only binds `127.0.0.1`, never phones home (except the LLM call), redacts before going out to the network and before persisting, and the frontend has zero external links (CSP `connect-src 'self'`; static artifacts are guarded by `scripts/check_static_no_external.py`); the backend rejects non-loopback Host and cross-Origin requests, preventing other web pages from using localhost to trigger local retrieval / LLM calls.
- **Self-host for customers**: single-image Docker (see `Dockerfile`: `docker build -t codetalk .` → `docker run`).
- The first frontend release is a zero-build single-file vanilla-JS; React/Vite comes only if the chat UX truly needs it (streaming already exists; message management later if required).

## Configuration

```bash
codetalk init        # write a config template to ~/.codetalk/config.json (auto chmod 600)
```

`~/.codetalk/config.json`:

```json
{
  "vault_path": "/path/to/obsidian/vault/folder",
  "provider": "deepseek",
  "model": "deepseek-v4-pro",
  "diff_token_budget": 3000,
  "output_lang": "中文",
  "providers": {
    "deepseek":  {"base_url": "https://api.deepseek.com/v1", "api_key": "sk-..."},
    "openai":    {"base_url": "https://api.openai.com/v1", "api_key": ""},
    "qwen":      {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "api_key": ""},
    "kimi":      {"base_url": "https://api.moonshot.cn/v1", "api_key": ""},
    "doubao":    {"base_url": "https://ark.cn-beijing.volces.com/api/v3", "api_key": ""},
    "glm":       {"base_url": "https://open.bigmodel.cn/api/paas/v4", "api_key": ""},
    "grok":      {"base_url": "https://api.x.ai/v1", "api_key": ""},
    "gemini":    {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "api_key": ""},
    "anthropic": {"api_key": ""},
    "ollama":    {"base_url": "http://localhost:11434/v1", "api_key": "ollama", "local": true}
  }
}
```

To switch models: change the top-level `provider` to any of the above and set the matching `model` (e.g. kimi→`kimi-k2-0905-preview`, glm→`glm-4.6`, grok→`grok-4`, gemini→`gemini-2.5-pro`, doubao→endpoint ID or `doubao-seed-1-6`). The API key can also come from the environment variable `<PROVIDER>_API_KEY` (e.g. `DEEPSEEK_API_KEY` / `KIMI_API_KEY` / `GLM_API_KEY` / `GROK_API_KEY` / `GEMINI_API_KEY` / `DOUBAO_API_KEY` / `ANTHROPIC_API_KEY`). Except for anthropic, which goes through the official SDK (json_schema structured output + prompt caching), everything else uses the OpenAI-compatible protocol (stdlib urllib, zero extra dependencies; DeepSeek context caching kicks in automatically).

**Zero-egress local inference**: set `provider` to `ollama` (or any OpenAI-compatible endpoint that is `local: true` / points at `localhost` or `127.0.0.1`, such as LM Studio / llama.cpp / vLLM), and the synthesis runs on your own machine — **even that single network exception, the "LLM call", stays off the network** (no key needed locally). Local 32B-class code models are already closing in on the cloud for generation-style tasks; position them as "local polishing/explanation after grounding", while agentic / complex synthesis is still better on the cloud. Together with `--no-llm` (never call an LLM at all), this forms a two-tier privacy gradient.

## Commands

| Command | What it does | Example |
|---|---|---|
| `doctor` | **First-run diagnosis**: evidence coverage, session sources, LLM config status, and next-step suggestions (**pure local, zero LLM**) | `codetalk doctor --project .` |
| `digest` | Enrich a span of commits + sessions into a **change-narrative daily report** (anti-hallucination, letter style, embedded time capsules) | `codetalk digest --since "3 days ago"` |
| `brief` | **Kickoff brief**: where you left off + top 3 understanding debts (**pure local, zero LLM**); `--all` gives a **cross-project overview** (across all projects: those with due capsules + those with the highest understanding debt, ordered by urgency) | `codetalk brief` · `codetalk brief --all` |
| `graph` | **Decision-impact graph**: which decision drove which later changes (timeline DAG, **zero LLM**; `--canvas` exports an Obsidian Canvas) | `codetalk graph --canvas` |
| `course` | **Evolution course**: how the project grew into what it is, step by step (chaptered + plain-language + scenario quizzes, single-file HTML) | `codetalk course` |
| `ask` | **Ask about a piece of code**, with answers wired to project memory (narratives + decision notes), citing real commits | `codetalk ask codetalk/llm.py:72-78 "why written this way"` |
| `console` | **Unified console (web entry)**: kickoff overview / timeline / decision graph / understanding debt — four views on one page, overview-first with click-to-drill, no more full-page dumps (**zero LLM**; `--serve` writes capsules back) | `codetalk console --serve` |
| `tunnel` | **Timeline**: a linear commit timeline, newest on top, grouped by day, click to read the narrative (`--serve` writes capsule answers back instantly) | `codetalk tunnel` |
| `install-hook` | Install a git hook: when hand-writing a commit, prompt in the editor to leave `Vibe-Decision`/`Vibe-Watch` decision notes | `codetalk install-hook` |
| `install-agent-seed` | Plant the decision-capture convention into the project `CLAUDE.md` + `AGENTS.md`, so an **AI coding agent** (Claude / others) automatically leaves decision notes on commit (**capture-at-write-time > inferring from the diff afterward**) | `codetalk install-agent-seed` |

`digest` output: `<vault>/YYYY-MM-DD-<project>.md` — a-year-ago-today / a-month-ago-today reflowed → today's overview (letter style) + today's decisions → due time capsules (to backfill) → per-commit narratives → an open-loop summary → run stats. Time capsules seal each risk for 21 days and, when due, bring it back in front of you in the daily report, closing the "predict → verify" loop.

### Decision Notes (make `ask` / `graph` sharper)

When you make a key technical tradeoff, leave a line in the commit message body:

```
Vibe-Decision: 用 urllib 不引第三方——M0 禁三方依赖
Vibe-Watch:    先这么扛,并发安全待验证
```

`digest` folds `Vibe-Decision` into that commit's decisions and `Vibe-Watch` into its risks (sealed into a verifiable capsule on due date); `ask` uses them to ground its answers, and `graph` uses them to connect decision-impact edges. You already write code with AI — let it leave a trail while it's at it. Matched exactly at line start, case-sensitive.

Committers who hand-write commits (without `-m`) can run `codetalk install-hook` once to install the `prepare-commit-msg` hook, and the editor will auto-prompt these two lines — fill them in and they stay in the commit message; leave them blank and git strips them. Git hooks aren't version-controlled with the repo, so **install once per clone**.

## Cache & privacy

- Commit narratives are cached by SHA in `~/.codetalk/cache.db` and **never recomputed**; re-running the same day's digest is 0 LLM calls and sub-second. `graph:` / `course:` / `ask:` derived results are cached in the same table under prefixed keys.
- Session parsing is incrementally cached by (session_id, mtime, size); every run's parameters are appended to `~/.codetalk/usage.log`.
- **Data does not leave your machine** (except LLM API calls); **before** writing the cache / writing the vault / injecting HTML, common secret patterns (API key / token / JWT / private key / Google / Stripe / Slack …) are always redacted.
- **`no_llm` hard switch**: turn off even that "LLM call" exception to **guarantee zero egress**. Any of three ways takes effect, applying globally (including the MCP `ask` tool): set `"no_llm": true` in config.json, set the environment variable `CODETALK_NO_LLM=1`, or pass `--no-llm` to `digest`/`ask`/`course`. Once on, blame/graph/search/brief/prompts work as usual, ask/course/MCP ask fall back to deterministic retrieval, and digest — which must use an LLM — exits directly (clearly stated, never silent).

## Known limitations (M0)

- The session source is not a complete audit log: Claude main sessions and `*/subagents/**/agent-*.jsonl` are included, but side files like journal/meta are not collected; Cursor / Codex local session sources are opt-in and depend on unofficial local formats.
- Session-to-commit alignment is a soft association (±30-minute time window + file intersection), targeting 80% accuracy, annotated with high/low confidence — **not guaranteed to be all correct**.
- Once a commit is amended / rebased and its SHA changes, it's treated as a new commit; the old SHA's cache becomes dead data.
- `graph`'s file-level edges get dense on very small projects and are suppressed with sparse nodes; line-level precision is deferred as a non-goal.
- The local session formats of Claude Code / Cursor / Codex are all unofficial, non-stable APIs; a version upgrade may break parsing — the parser ignores unknown fields and degrades on missing ones, worst-case falling back to pure-git mode.

## Architecture

```
cli → gitlog (commit/diff/line history/decision notes) ─┐
      sessions (Claude/Cursor/Codex, fault-tolerant) ─┼→ align (soft assoc.) → enrich (LLM, SHA cache) → report → vault
      cache (SQLite single source of truth)          ─┘
Zero-LLM tools: brief / debt / graph read cache + git directly, bypassing enrich/llm.
Unified LLM wrapper: llm.py (multi-provider / retry / token log / prompt caching / anti-hallucination + style discipline).
```

## Design philosophy (M0)

The core CLI/MCP surface stays on standard library + anthropic SDK (optional); LangGraph / vector DBs / heavy frontend chains are **forbidden**. `codetalk web` is an optional web extra — only that surface allows FastAPI / uvicorn, and it's lazily imported so it doesn't pollute the core dependencies. Modules stay <300 lines; parsing external data is always fault-tolerant, degrading on failure and never crashing. Behavioral guidelines are in `CLAUDE.md` (Karpathy coding discipline: think before writing / simplicity first / surgical changes / goal-driven).

## Release & contributing

- Pre-release checks: [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md)
- Change log: [`CHANGELOG.md`](CHANGELOG.md)
- Contribution constraints: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Security reports: [`SECURITY.md`](SECURITY.md)
