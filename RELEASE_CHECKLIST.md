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
- `python3 -m scripts.release_promotion validate-candidate dist docs/releases/v0.2.0.md`
- `cd dist && shasum -a 256 -c SHA256SUMS`
- Confirm the sdist contains no `tests/` tree and all four archives pass the
  secret, private-path, member-type, and public-filename scan.
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

## 0.2.0 Promotion

Preparation snapshot; update every item from its public or owner-only endpoint
before promotion:

- [ ] Protected `release`, `pypi`, and `github-pages` environments are not yet
  configured.
- [ ] The PyPI Pending Trusted Publisher still requires owner setup for project
  `codetalk`, repository `HUKAIR/CodeTalk`, workflow `release.yml`, and
  environment `pypi`.
- [ ] GitHub immutable Releases are currently disabled.
- [ ] GitHub Pages is currently disabled; its source must be GitHub Actions.

Run the non-publishing rehearsal first:

- `gh workflow run release.yml --ref main -f publish=false`
- Watch the run and require the reusable test workflow, candidate validation,
  secret scan, product-proof test, and Pages artifact upload to pass.
- Confirm every job after `candidate` is skipped.
- Reconfirm that no tag, PyPI project, GitHub Release, Pages site, or Homepage
  change exists.

The following owner actions require fresh explicit confirmation because they
enable or perform public, partly irreversible changes:

- Configure required reviewers and tag restrictions on the `release`, `pypi`,
  and `github-pages` environments.
- Add a repository tag ruleset that blocks update and deletion of `v0.2.0`,
  including administrator bypass during the promotion window.
- Register the PyPI Pending Trusted Publisher with the exact values above.
- Enable immutable Releases and verify
  `gh api repos/HUKAIR/CodeTalk/immutable-releases --jq .enabled` prints `true`.
- Enable GitHub Pages with GitHub Actions as the source and verify
  `gh api repos/HUKAIR/CodeTalk/pages --jq .build_type` prints `workflow`.
- Create a signed annotated `v0.2.0` tag at the fully verified preparation
  commit and confirm GitHub reports its signature as verified.
- Push only that tag, then run
  `gh workflow run release.yml --ref v0.2.0 -f publish=true`.

After promotion, verify from public endpoints:

- `python3 -m pip install --no-cache-dir --no-deps codetalk==0.2.0` in a new
  virtual environment, followed by `codetalk --version`, `doctor`, and
  `review --json` in a synthetic repository.
- `gh release verify v0.2.0` and `gh release verify-asset v0.2.0 <local-file>`
  for the wheel, sdist, MCP bundle, VSIX, SBOM, and `SHA256SUMS`.
- Fetch the Pages root and `docs/images/codetalk-logo-banner.png`, then compare
  them byte-for-byte with a fresh local `stage-pages` output. The staged PNG is
  expected to differ from the source only by removed EXIF/text/time metadata.
- Set the repository Homepage only after the Pages URL and local asset resolve
  from a clean session.
- Leave issue #142 open until every public endpoint, hash, install smoke test,
  and Homepage check succeeds.

## Post-Release

- Watch install issues for command drift, MCP client differences, and Python
  version problems.
- Track warnings from full test runs separately from release blockers.
- Convert repeated support questions into README or docs updates.
