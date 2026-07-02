# Release Checklist

Use this checklist before a public CodeTalk release.

## Local Verification

- `python3 -m unittest discover -s tests`
- `python3 -m scripts.scan_secrets`
- `python3 -m scripts.scan_secrets --history`
- `python3 -m scripts.check_static_no_external codetalk/web_chat.html codetalk/console.html codetalk/tunnel.html codetalk/course.html codetalk/graph.html codetalk/trust_ab.html`
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
- Confirm the VSIX contains `extension/LICENSE.txt`.
- Install the VSIX in at least one VS Code-compatible editor and verify CodeLens
  plus hover behavior on a repository with CodeTalk cache data.

## MCP Bundle

- Build `codetalk.mcpb`.
- Inspect `manifest.json` and confirm package name, command, and version.
- Confirm the bundle contains `LICENSE`.
- Run MCP `initialize` and `tools/list`.
- Confirm all exposed tools are read-only and use the `codetalk_*` names.

## Docker Self-Host (if promoting the Docker path)

- On a machine with a running Docker daemon: `docker build -t codetalk .`
- `docker run --rm -p 127.0.0.1:8000:8000 -v "$PWD:/repo:ro" codetalk`
- `curl -sS http://127.0.0.1:8000/ | head` returns the chat page (confirms the
  container binds `0.0.0.0` via `CODETALK_WEB_HOST` and the host loopback
  port-map reaches it).
- Confirm a request with a non-loopback `Host:` header is rejected (403), so the
  `_local_request_guard` still holds with the wider bind.
- This path is not exercisable in the CI sandbox (no daemon); it must pass on a
  real machine before the README Docker claim goes public.

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
