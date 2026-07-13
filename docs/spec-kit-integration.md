# CodeTalk × Spec-Driven Development

How CodeTalk plugs into the [GitHub Spec Kit](https://github.com/github/spec-kit) workflow (or any spec-driven pipeline: AWS Kiro, OpenSpec, BMAD, Tessl, Google Antigravity).

## The gap Spec Kit doesn't close

Spec Kit and its siblings turn specs into code. They produce the **forward** direction: spec → plan → code. But they don't capture the **backward** direction:

- 3 months from now: which spec drove this line?
- Mid-implementation: this commit deviates from the plan — was that intentional?
- Code review: the spec said X, the code does Y — what was the trade-off?

The forward arrow exists. The backward arrow is missing. AI inference (Cursor/Copilot reading the diff) confabulates it: 5/5 misses real decisions in our blind test.

## How CodeTalk fits

CodeTalk adds two grounding edges to the spec ↔ code loop:

```
spec.md ─┐                              ┌─ blame: which spec did this line ground in?
         ├─→ plan.md ─→ code (commits) ─┤
         │                              └─ ask: why did we deviate from the plan?
         └─ adr-export: which decisions came out of this spec round?
```

`blame` and `adr-export` are zero-LLM and SHA-anchored. `ask` uses the same
verbatim evidence deterministically with `--no-llm` or without a provider key;
when LLM synthesis is enabled, its answer remains bounded by cited evidence but
is not itself a verbatim record.

## Concrete workflow

### 1. Author phase — capture spec → decision linkage

When the spec gets refined, the agent leaves decision notes in commits:

```
feat(auth): add JWT refresh rotation

Vibe-Decision: rotate on every refresh (spec.md §3.2 — single-use refresh)
Vibe-Rejected: shared session token (spec.md §3.2 explicitly rejected)
Vibe-Watch:    rotation collisions on retry — see plan.md §5
```

`Vibe-Decision` / `Vibe-Rejected` / `Vibe-Watch` cite the spec section verbatim. No prose summary, no AI-generated link. The spec lives in git too — the citation is grep-able and verifiable.

If you use Claude Code, Cursor, or Copilot:

```bash
codetalk install-agent-seed --project .
```

drops the decision-note instruction into `CLAUDE.md`, `.cursorrules`,
`.cursor/rules/codetalk.mdc`, `.github/copilot-instructions.md`, and `AGENTS.md`.
The append is idempotent; the agent can then leave these records automatically.

### 2. Review phase — ground code-review questions in the spec

During code review, instead of `git blame` (who/when) reach for:

```bash
codetalk blame src/auth/refresh.ts:42-58
```

Output (for a line touched by the JWT commit above):

```
[abc1234] 2026-06-30 feat(auth): add JWT refresh rotation
  Why: spec §3.2 mandates single-use refresh tokens
  Decision: rotate on every refresh (spec.md §3.2)
  Rejected: shared session token (spec.md §3.2 explicitly rejected)
  Risk:     rotation collisions on retry — see plan.md §5
```

Now the reviewer sees the spec-bound rationale verbatim, with click-through to the commit. Or in VS Code/Cursor/Windsurf:

```bash
cd vscode-codetalk && npm install && npm run build && code --install-extension vscode-codetalk-*.vsix
```

CodeLens above the block shows `▸ abc1234 · 决策(2) 风险(1)`. Click to expand the decision tree inline.

### 3. Audit phase — export decisions back as ADR or AIBOM

When a spec round closes:

```bash
# Generate a MADR ADR from the real decisions made under §3.2
codetalk adr-export src/auth/refresh.ts --format madr > docs/adr/0042-refresh-rotation.md

# Or emit a CycloneDX 1.5 BOM for AIBOM ecosystem ingestion
codetalk adr-export src/auth/refresh.ts --format cyclonedx > auth-refresh.bom.json
```

The ADR cites every commit verbatim. The BOM plugs into AIBOM tooling (CISA/G7 SBOM for AI, CycloneDX, SPDX 3.0).

### 4. Agent phase — give your AI tools spec-grounded memory via MCP

If your AI agent (Claude Code, Cursor, Codex) talks to CodeTalk over MCP, it can ground its own answers in real spec decisions instead of re-inferring from the diff:

```json
// .mcp.json
{
  "mcpServers": {
    "CodeTalk": {
      "command": "python3",
      "args": ["-m", "codetalk", "mcp-serve", "--project", "/abs/path/to/repo"]
    }
  }
}
```

7 tools: `ask`, `blame`, `search`, `graph`, `drift`, `prompts`, `adr` — all `readOnlyHint: true` so Claude Code / Cursor auto-approve.

When the agent asks "why did we pick JWT rotation here?" before suggesting a refactor, it now reads the spec-bound rationale verbatim instead of re-inferring it.

## Why this matters for spec-driven teams

Spec Kit makes spec → code clear. CodeTalk makes code → spec verifiable. Combined, the spec ↔ code loop is fully two-way grounded — no AI inference in either direction, no confabulation 3 months later.

If your team is already in the Spec Kit / Kiro / OpenSpec / BMAD / Antigravity universe and the question "why does this code do X?" still requires asking the original author from memory — CodeTalk fills that exact gap.

## Honest boundaries

- CodeTalk doesn't generate specs. It only captures decisions made under existing specs.
- The spec ↔ commit link is a decision-note convention (`Vibe-Decision`,
  `Vibe-Rejected`, and `Vibe-Watch`), not enforced by tooling. If the agent skips
  it, CodeTalk can use optional LLM enrichment of the commit message, which can
  still hallucinate; that is why enrichment is not the deterministic path.
- The CycloneDX export covers base schema only — not `modelCard` / `formulation` / AI-specific sections, because CodeTalk tracks code decisions, not model artifacts. Don't claim AIBOM conformance you don't have.
- Coverage depends on decision notes or `codetalk enrich` having run. On a fresh
  repo with neither, blame is close to `git log`. See
  [README honest boundaries](../README.md).

## Related reading

- [README](../README.md) — what CodeTalk is
- [MCP install guide](mcp-install.md) — agent integration
- [VS Code extension](../vscode-codetalk/README.md) — foldable CodeLens + hover decision cards
- [Spec Kit](https://github.com/github/spec-kit) — the spec-driven workflow this complements
