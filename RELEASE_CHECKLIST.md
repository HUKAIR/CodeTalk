# Release Checklist

Use this checklist before a public CodeTalk release.

This repository is public. Only test CI is authorized; release.yml is disabled. Publishing
identities, protected environments, immutable Releases, and Pages settings have
not been transferred from the previous repository. The public-release checks
below apply only after separate owner authorization.

## Local Verification

- `python3 -m unittest discover -s tests`
- `python3 -m scripts.scan_secrets`
- `python3 -m scripts.scan_secrets --history`
- `python3 -m scripts.check_static_no_external codetalk/web_chat.html codetalk/console.html codetalk/tunnel.html codetalk/course.html codetalk/graph.html codetalk/trust_ab.html codetalk/recap.html codetalk/recap_index.html`
- `python3 -m unittest tests.test_product_proof`
- `SOURCE_DATE_EPOCH=<release-commit-epoch> python3 -m build`
- `python3 -m scripts.build_mcpb` → `dist/codetalk-0.4.1.mcpb`
- `python3 -m pip install -e . --no-deps --dry-run --no-build-isolation`
- `git diff --check`

After packaging the editor extension, copy
`vscode-codetalk/vscode-codetalk-0.4.1.vsix` into `dist/`, then run:

- `SOURCE_DATE_EPOCH=<release-commit-epoch> python3 -m scripts.release_artifacts dist`
- `python3 -m scripts.release_promotion validate-candidate dist docs/releases/v0.4.1.md`
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
- `unzip -t vscode-codetalk-0.4.1.vsix`
- Confirm the VSIX contains `extension/LICENSE.txt`.
- Install the VSIX into a clean `--extensions-dir`, confirm
  `codetalk.vscode-codetalk` appears in `--list-extensions --show-versions`,
  then start a VS Code-compatible editor and verify CodeLens plus hover behavior
  on a repository with CodeTalk cache data.

## MCP Bundle

- Build `dist/codetalk-0.4.1.mcpb`.
- Inspect `manifest.json` and confirm package name, command, and version.
- Confirm the bundle contains `LICENSE`.
- Extract into a new temporary directory and run MCP `initialize` and
  `tools/list` using only the bundled `server/` path.
- Confirm all exposed tools are read-only and use the `codetalk_*` names.

## Python Wheel

- Create a new virtual environment outside the repository.
- Install only `dist/hukair_codetalk-0.4.1-py3-none-any.whl` with `--no-deps`.
- Confirm `codetalk --version` reports `0.4.1` and `pip check` passes.
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
- Publish and verify the canonical `pipx install hukair-codetalk` path from a
  clean environment; `uv tool install hukair-codetalk` is the one documented
  alternative, and both must install the `codetalk` command.
- Generate the shareable A/B trust demo for the announcement:
  `python3 scripts/trust_ab_demo.py . 5 --html demo.html` (needs an LLM key).
- Verify MCP bundle install works: use `codetalk-0.4.1.mcpb` and confirm
  `initialize` + `tools/list` from a clean MCP client.
- Add at least one short demo recording or screenshot for the README or docs.
- Confirm LICENSE, SECURITY, CONTRIBUTING, CHANGELOG, and issue templates are
  present.

## 0.4.1 Promotion

Preparation snapshot; update every item from its public or owner-only endpoint
before promotion. The `0.3.1` promotion completed on 2026-07-22; none of the
checks below carry over automatically.

- [ ] Protected `release`, `pypi`, and `github-pages` environments require the
  owner reviewer and accept only the exact `v0.4.1` tag.
- [ ] Before a future release from this repository, separately configure and
  verify a PyPI Trusted Publisher for project `hukair-codetalk`, repository
  `HUKAIR/CodeTalk`, workflow `release.yml`, and environment `pypi`.
  The old repository's publishing identity was not migrated. That repository is
  now `HUKAIR/CodeTalk-legacy`; remove any Trusted Publisher created for the old
  `HUKAIR/CodeTalk` name before adding one for this repository.
- [ ] GitHub immutable Releases are enabled for this repository before promotion.
- [ ] GitHub Pages is configured with GitHub Actions as its source before promotion.

Run the non-publishing rehearsal first:

- `gh workflow run release.yml --ref main -f publish=false`
- [ ] Require the reusable test workflow, candidate validation, secret scan,
  product-proof test, and Pages artifact upload to pass.
- [ ] Confirm every job after `candidate` is skipped.
- [ ] Reconfirm that the rehearsal created no `v0.4.1` tag, public PyPI version,
  public GitHub Release, Pages deployment, or Homepage change.

Durable lessons from the `0.2.0`-`0.3.1` promotion history (full run-by-run
narrative lives in the `0.3.1` revision of this checklist in git history):

- PyPI rule: deleted PyPI filenames cannot be reused; never delete a PyPI
  release to retry, and advance the package version after a filename tombstone.
- `GITHUB_TOKEN` cannot read the Administration-only immutable-Releases
  endpoint. Do not solve this with a PAT; verify the setting from the owner CLI
  before dispatch and retain the post-public immutable Release and
  asset-attestation checks.
- GitHub hosted-runner degradation can delay jobs without changing release
  state; check public state before considering a retry.

Owner actions requiring explicit authorization:

- [ ] Extend the repository tag ruleset to block update and deletion of
  `v0.4.1`, including administrator bypass during the promotion window.
- [ ] Create a signed annotated `v0.4.1` tag at the fully verified preparation
  commit and confirm GitHub reports its signature as verified.
- [ ] Push only that tag, then run
  `gh workflow run release.yml --ref v0.4.1 -f publish=true`.

Any tag, package, Release, Pages, Homepage, or issue-state change requires
fresh explicit confirmation; the completed `0.3.1` authorization does not carry
over.

After promotion, verify from public endpoints:

- [ ] `python3 -m pip install --no-cache-dir --no-deps hukair-codetalk==0.4.1` in a new
  virtual environment, followed by `codetalk --version`, `doctor`, and
  `review --json` in a synthetic repository.
- [ ] `gh release verify v0.4.1` and `gh release verify-asset v0.4.1 <local-file>`
  for the wheel, sdist, MCP bundle, VSIX, SBOM, and `SHA256SUMS`.
- [ ] Fetch the Pages root and `docs/images/codetalk-logo-banner.png`, then compare
  them byte-for-byte with a fresh local `stage-pages` output. The staged PNG is
  expected to differ from the source only by removed EXIF/text/time metadata.
- [ ] Set the repository Homepage only after a separate explicit product
  decision. It remains unset; successful publication does not silently change
  repository presentation.
- [ ] Leave issue #142 open for a separate scope/title review; release
  verification must not silently close an issue whose title still names 0.2.0.

## Post-Release

- Watch install issues for command drift, MCP client differences, and Python
  version problems.
- Track warnings from full test runs separately from release blockers.
- Convert repeated support questions into README or docs updates.
