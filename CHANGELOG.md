# Changelog

All notable changes to CodeTalk will be documented in this file.

This project follows a small, source-backed changelog style: each entry should
describe user-visible behavior and point to the release, PR, or commit that
made it verifiable.

## 0.3.1 - Unreleased

Versions `0.2.0`, `0.2.1`, `0.2.2`, and `0.3.0` were not publicly released
because PyPI had permanently reserved their deleted `codetalk` artifact
filenames. Version `0.3.1` moves only the PyPI distribution identity to the
collision-resistant `hukair-codetalk`; the CLI command, Python import package,
MCP identity, and editor branding remain `codetalk` / CodeTalk.

### Added

- Browser-reachable rich views: `/graph` (decision-impact DAG) and `/course`
  (evolution course) web routes, alongside the existing `/console` and `/tunnel`.
- `diff ▾` on web chat citations opens the real `git show` in-browser via a new
  read-only `/api/commit/<sha>` endpoint (zero-LLM, redacted, strict SHA check).
- Console full-repo full-text search panel wired to `/api/search` (FTS).
- Bilingual zh/en toggle across all web views (persisted locally; defaults to the
  browser language) plus bilingual server-side error pages.
- Shareable interactive A/B trust demo page: `trust_ab_demo.py --html`.
- `grounding_hitrate.py` now reports the "real grounding" north-star input levers
  (breadth = verbatim decision-note coverage, depth = session anchors), excluding
  LLM-generated narratives.
- `codetalk --version`; CI test matrix on Python 3.11 through 3.14.
- `codetalk review --json` exposes the same deterministic decision review cards
  used by terminal output, with stable identifiers, provenance, primary and
  supporting evidence, generated interpretation, and unresolved judgment kept
  as separate fields.
- `codetalk review --serve` opens the same cards in a loopback-only bilingual
  review page with collapsible sources and four locally persisted maintainer
  judgments; only a confirmed conflict that changes the proposed action is
  labeled a verified interception.
- Resolved review cards can preview and explicitly download a local feedback
  JSON allowlist. It includes judgment and evidence metadata but never copies
  repository identity, paths, source material, commits, sessions, or authors;
  optional approved comments are redacted before preview and export.
- `codetalk enrich` now performs deterministic evidence work and prints an
  inspectable no-request privacy plan by default. Remote model calls require
  `--allow-remote` for that command; `--payload-preview` shows one redacted
  request locally without sending it, while exact loopback endpoints remain
  zero egress.
- A sanitized, dependency-free `index.html` product proof now opens on a
  successful synthetic decision review, exercises every judgment outcome,
  demonstrates inspectable enrichment without making a request, and leads to
  the canonical `pipx` install. Both READMEs follow the same review, privacy,
  install, then deeper-documentation path.

### Fixed

- Grounding integrity: `ask` no longer emits LLM-self-reported citation SHAs that
  aren't in the retrieved evidence.
- Non-UTF-8 repositories no longer crash the pipeline (git output decoded with
  replacement).
- Web/chat degrade gracefully when the LLM call fails instead of 500/broken stream.
- Directory names are HTML-escaped in all rendered views (XSS); the A/B demo page
  escapes `</` to prevent `</script>` breakout.
- `self` report labels capsule fill rate as a guardrail (not the north star).
- Docker builds copy an explicit runtime allowlist, so ignored local files such
  as `.mcp.json`, caches, and private notes cannot enter the image accidentally.
- Decision-note coverage consistently counts `Vibe-Decision`, `Vibe-Rejected`,
  and `Vibe-Watch` records from non-merge commits.
- Local LLM endpoints are trusted only when the parsed hostname is exactly
  `localhost`, `127.0.0.1`, or `::1`; a `local` config label and lookalike
  hostnames can no longer bypass API-key requirements.
- The console full-repo search drawer now respects its `hidden` state, so it no
  longer covers the main view on first load or after closing.
- Web startup and UI copy now describe the product as local-first and disclose
  that model calls follow configuration instead of promising unconditional
  zero egress.
- Web tests install Starlette's `httpx2` test-client dependency through a
  dedicated `test` extra, without adding it to Web runtime or core dependencies.
- CI uses read-only token permissions, does not persist checkout credentials,
  and pins official GitHub Actions to immutable Node 24 release SHAs.
- Review cards now treat only explicit commit decision notes and verifiable
  source records as evidence; model-generated decisions and rejected paths stay
  visibly labeled as non-authoritative interpretation.

## 0.1.0 - 2026-07-01

### Added

- Initial local-first `codetalk` CLI for decision provenance from git history,
  commit decision notes, and optional enriched session context.
- Zero-LLM deterministic tools for `blame`, `search`, `graph`, `drift`,
  `prompts`, and ADR export.
- MCP bundle build path via `python3 -m scripts.build_mcpb`, exposing seven
  read-only CodeTalk tools.
- Self-hosted web chat and console surfaces with local loopback defaults and
  static asset checks.
- VS Code-compatible extension under `vscode-codetalk`, with foldable decision
  CodeLens and hover cards.
- Release metadata, project URLs, and CI coverage for Python tests plus VS Code
  extension typecheck/build.
- Release secret scanner for repository files and optional git history, reusing
  the same secret patterns as runtime redaction.
- MCP bundle now includes the AGPL license text, not only a manifest license
  identifier.
- VS Code extension packaging now syncs the repository AGPL license before
  `vsce` packaging.
- `codetalk doctor` provides a zero-LLM first-run diagnostic for git coverage,
  decision notes, local session availability, LLM readiness, and the next
  command to try.

### Fixed

- Renamed public product copy and packaging references from the old prototype
  name to CodeTalk / `codetalk`.
- Corrected release docs where copied commands would fail, including module
  names, directory names, Docker tags, and MCP self-check output.
- Updated runtime web headers, FastAPI title, VS Code display name, and local
  package readme content to the current product name.
- Fixed a stale mixed-case module command in the MCP zero-egress example.
- `usage.log` now creates its parent directory before append, removing first-run
  warning noise while preserving failure-as-warning behavior.
- `Cache` close is now idempotent and guarded by context-manager/destructor
  support, reducing sqlite connection lifecycle warnings.
- `codetalk drift` no longer opens or writes the session cache, keeping the
  CLI/MCP read-only promise and removing readonly database warning noise.

### Known Release Notes

- The supported soft-launch install path is clone plus `pip install -e .`.
  PyPI publishing has not been performed yet; `pip index versions codetalk`
  currently reports no matching distribution.
- Official VSIX packaging has been run locally; the package includes
  `extension/LICENSE.txt`.
- The GitHub repository is public, but no GitHub Release or PyPI distribution has
  been published; source checkout remains the only supported install path.
- Demo media and Marketplace assets are not yet included.
