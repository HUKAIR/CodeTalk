# Changelog

All notable changes to CodeTalk will be documented in this file.

This project follows a small, source-backed changelog style: each entry should
describe user-visible behavior and point to the release, PR, or commit that
made it verifiable.

## 0.1.0 - 2026-07-01

### Added

- Initial local-first `codetalk` CLI for decision provenance from git history,
  decision breadcrumbs, and optional enriched session context.
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
  decision breadcrumbs, local session availability, LLM readiness, and the next
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
  PyPI publishing has not been performed yet.
- Official VSIX packaging still needs to be rerun in a trusted network-enabled
  environment because local npm registry access was intentionally not approved.
- Demo media and marketplace assets are not yet included.
