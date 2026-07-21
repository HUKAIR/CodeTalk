# Release Checklist

Use this checklist before a public CodeTalk release.

## Local Verification

- `python3 -m unittest discover -s tests`
- `python3 -m scripts.scan_secrets`
- `python3 -m scripts.scan_secrets --history`
- `python3 -m scripts.check_static_no_external codetalk/web_chat.html codetalk/console.html codetalk/tunnel.html codetalk/course.html codetalk/graph.html codetalk/trust_ab.html`
- `python3 -m unittest tests.test_product_proof`
- `SOURCE_DATE_EPOCH=<release-commit-epoch> python3 -m build`
- `python3 -m scripts.build_mcpb` → `dist/codetalk-0.2.0.mcpb`
- `python3 -m pip install -e . --no-deps --dry-run --no-build-isolation`
- `git diff --check`

After packaging the editor extension, copy
`vscode-codetalk/vscode-codetalk-0.2.0.vsix` into `dist/`, then run:

- `SOURCE_DATE_EPOCH=<release-commit-epoch> python3 -m scripts.release_artifacts dist`
- `cd dist && shasum -a 256 -c SHA256SUMS`
- Confirm the CycloneDX SBOM lists the wheel, sdist, MCP bundle, and VSIX with
  the same SHA-256 values as `SHA256SUMS`.

## VS Code Extension

- `cd vscode-codetalk`
- `npm ci`
- `npm run typecheck`
- `npm run build`
- `npm run package`
- `unzip -t vscode-codetalk-0.2.0.vsix`
- Confirm the VSIX contains `extension/LICENSE.txt`.
- Install the VSIX into a clean `--extensions-dir`, confirm
  `codetalk.vscode-codetalk` appears in `--list-extensions --show-versions`,
  then start a VS Code-compatible editor and verify CodeLens plus hover behavior
  on a repository with CodeTalk cache data.

## MCP Bundle

- Build `dist/codetalk-0.2.0.mcpb`.
- Inspect `manifest.json` and confirm package name, command, and version.
- Confirm the bundle contains `LICENSE`.
- Extract into a new temporary directory and run MCP `initialize` and
  `tools/list` using only the bundled `server/` path.
- Confirm all exposed tools are read-only and use the `codetalk_*` names.

## Python Wheel

- Create a new virtual environment outside the repository.
- Install only `dist/codetalk-0.2.0-py3-none-any.whl` with `--no-deps`.
- Confirm `codetalk --version` reports `0.2.0` and `pip check` passes.
- In a synthetic git repository, smoke-test `doctor`, `review --json`, local
  feedback export, default no-request enrichment, payload preview, and explicit
  recording-fake authorization behavior.

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

- Confirm `git log --all --name-only` contains no private strategy docs or
  secrets before flipping (only intentionally-public files should be in history).
- Confirm `https://github.com/HUKAIR/CodeTalk` is reachable from a logged-out or
  clean environment.
- If a hosted provider reports additional secret alerts, revoke affected keys
  before promoting the repository.
- Publish and verify the canonical `pipx install codetalk` path from a clean
  environment; `uv tool install codetalk` is the one documented alternative.
- Generate the shareable A/B trust demo for the announcement:
  `python3 scripts/trust_ab_demo.py . 5 --html demo.html` (needs an LLM key).
- Verify MCP bundle install works: use `codetalk-0.2.0.mcpb` and confirm
  `initialize` + `tools/list` from a clean MCP client.
- Add at least one short demo recording or screenshot for the README or docs.
- Confirm LICENSE, SECURITY, CONTRIBUTING, CHANGELOG, and issue templates are
  present.

## Post-Release

- Watch install issues for command drift, MCP client differences, and Python
  version problems.
- Track warnings from full test runs separately from release blockers.
- Convert repeated support questions into README or docs updates.
