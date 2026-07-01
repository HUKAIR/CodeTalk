# Release Checklist

Use this checklist before a public CodeTalk release.

## Local Verification

- `python3 -m unittest discover -s tests`
- `python3 -m scripts.scan_secrets`
- `python3 -m scripts.scan_secrets --history`
- `python3 -m scripts.check_static_no_external codetalk/web_chat.html codetalk/console.html codetalk/tunnel.html codetalk/course.html codetalk/graph.html`
- `python3 -m scripts.build_mcpb`
- `python3 -m pip install -e . --no-deps --dry-run --no-build-isolation`
- `git diff --check`

## VS Code Extension

- `cd vscode-codetalk`
- `npm ci`
- `npm run typecheck`
- `npm run build`
- `npm run package`
- `unzip -t vscode-codetalk-0.2.0.vsix`
- Confirm the VSIX contains `extension/LICENSE`.
- Install the VSIX in at least one VS Code-compatible editor and verify CodeLens
  plus hover behavior on a repository with CodeTalk cache data.

## MCP Bundle

- Build `codetalk.mcpb`.
- Inspect `manifest.json` and confirm package name, command, and version.
- Confirm the bundle contains `LICENSE`.
- Run MCP `initialize` and `tools/list`.
- Confirm all exposed tools are read-only and use the `codetalk_*` names.

## Public Launch

- Confirm `https://github.com/HUKAIR/CodeTalk` is public from a logged-out or
  clean environment.
- If a hosted provider reports additional secret alerts, revoke affected keys
  before promoting the repository.
- Decide whether the launch promise is clone/editable install or PyPI install.
- If claiming PyPI install, publish and verify `pip install codetalk`.
- Add at least one short demo recording or screenshot for the README or docs.
- Confirm LICENSE, SECURITY, CONTRIBUTING, CHANGELOG, and issue templates are
  present.

## Post-Release

- Watch install issues for command drift, MCP client differences, and Python
  version problems.
- Track warnings from full test runs separately from release blockers.
- Convert repeated support questions into README or docs updates.
