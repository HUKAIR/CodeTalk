# Release Checklist

Use this checklist before a public CodeTalk release.

## Local Verification

- `python3 -m unittest discover -s tests`
- `python3 -m scripts.scan_secrets`
- `python3 -m scripts.scan_secrets --history`
- `python3 -m scripts.check_static_no_external codetalk/web_chat.html codetalk/console.html codetalk/tunnel.html codetalk/course.html codetalk/graph.html codetalk/trust_ab.html`
- `python3 -m unittest tests.test_product_proof`
- `SOURCE_DATE_EPOCH=<release-commit-epoch> python3 -m build`
- `python3 -m scripts.build_mcpb` → `dist/codetalk-0.3.1.mcpb`
- `python3 -m pip install -e . --no-deps --dry-run --no-build-isolation`
- `git diff --check`

After packaging the editor extension, copy
`vscode-codetalk/vscode-codetalk-0.3.1.vsix` into `dist/`, then run:

- `SOURCE_DATE_EPOCH=<release-commit-epoch> python3 -m scripts.release_artifacts dist`
- `python3 -m scripts.release_promotion validate-candidate dist docs/releases/v0.3.1.md`
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
- `unzip -t vscode-codetalk-0.3.1.vsix`
- Confirm the VSIX contains `extension/LICENSE.txt`.
- Install the VSIX into a clean `--extensions-dir`, confirm
  `codetalk.vscode-codetalk` appears in `--list-extensions --show-versions`,
  then start a VS Code-compatible editor and verify CodeLens plus hover behavior
  on a repository with CodeTalk cache data.

## MCP Bundle

- Build `dist/codetalk-0.3.1.mcpb`.
- Inspect `manifest.json` and confirm package name, command, and version.
- Confirm the bundle contains `LICENSE`.
- Extract into a new temporary directory and run MCP `initialize` and
  `tools/list` using only the bundled `server/` path.
- Confirm all exposed tools are read-only and use the `codetalk_*` names.

## Python Wheel

- Create a new virtual environment outside the repository.
- Install only `dist/hukair_codetalk-0.3.1-py3-none-any.whl` with `--no-deps`.
- Confirm `codetalk --version` reports `0.3.1` and `pip check` passes.
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
- Verify MCP bundle install works: use `codetalk-0.3.1.mcpb` and confirm
  `initialize` + `tools/list` from a clean MCP client.
- Add at least one short demo recording or screenshot for the README or docs.
- Confirm LICENSE, SECURITY, CONTRIBUTING, CHANGELOG, and issue templates are
  present.

## 0.3.1 Promotion

Preparation snapshot; update every item from its public or owner-only endpoint
before promotion:

- [x] Protected `release`, `pypi`, and `github-pages` environments require the
  owner reviewer and accept only the exact `v0.3.1` tag.
- [x] The owner confirmed the PyPI Pending Trusted Publisher for project
  `hukair-codetalk`, repository `HUKAIR/CodeTalk`, workflow `release.yml`, and
  environment `pypi`.
- [x] GitHub immutable Releases are enabled.
- [x] GitHub Pages is enabled with GitHub Actions as its source.

Run the non-publishing rehearsal first:

- `gh workflow run release.yml --ref main -f publish=false`
- The exact `0.3.1` rehearsal `29936384409` passed from preparation commit
  `194dca9`: Python 3.11-3.14, the full test suite, VSIX, history and source
  privacy scans, reproducible distributions, exact candidate validation,
  installed-wheel smoke test, product proof, and Pages staging all passed.
  Every job from `preflight` onward was skipped. A follow-up check found no
  `v0.3.1` tag or Release, no public PyPI version, no Homepage change, and issue
  #142 remained open.
- The authorized `v0.3.1` promotion run `29959650706` completed successfully
  from signed tag target `194dca9`. PyPI OIDC publication, public hash
  verification, immutable Release publication, six asset attestations, the
  two-file Pages deployment, and final clean-client verification all passed.
  GitHub hosted-runner degradation delayed two jobs without changing release
  state or requiring a retry.
- Completed evidence: Actions run `29871281164` passed from `97f5d3c`; all jobs
  after `candidate` were skipped and the public-state recheck was unchanged.
- The first authorized promotion run `29879880097` stopped before draft,
  PyPI, Release, or Pages writes. Candidate and signed-tag checks passed; the
  preflight exposed that `GITHUB_TOKEN` cannot read the Administration-only
  immutable-Releases endpoint. Do not solve this with a PAT. Verify the setting
  from the owner CLI before dispatch and retain the post-public immutable
  Release and asset-attestation checks.
- The authorized `v0.2.0` promotion run `29880629420` passed every repository
  gate and authenticated to PyPI through OIDC, then stopped when PyPI reported
  that both `0.2.0` filenames had been uploaded and deleted previously. No
  GitHub Release or Pages deployment became public. PyPI rule: deleted PyPI
  filenames cannot be reused; never delete a PyPI release to retry, and advance
  the package version after a filename tombstone.
- The synchronized `0.2.1` non-publishing run `29881493075` passed every build,
  test, candidate, privacy, and Pages-staging gate; all public jobs were skipped.
- The authorized `v0.2.1` promotion run `29882535367` also passed every
  repository and OIDC gate, then PyPI reported that the `0.2.1` filenames had
  previously been deleted as well. Release publication and Pages stayed
  skipped, and the Release remained a hidden draft.
- The synchronized `0.2.2` non-publishing run `29884029536` passed the Python
  3.11-3.14 matrix, extension build, history and source privacy scans,
  reproducible distributions, exact candidate validation, product-proof test,
  and Pages staging; all public jobs were skipped.
- The authorized `v0.2.2` promotion run `29884421966` passed every repository,
  signed-tag, candidate, privacy, and OIDC gate. PyPI then reported that the
  deleted `0.2.2` filenames were permanently reserved. Release publication and
  Pages stayed skipped, and the Release remains a hidden draft. After three
  consecutive reserved patch versions, recovery advances directly to `0.3.0`
  instead of probing another patch filename.
- The synchronized `0.3.0` non-publishing run `29885343260` passed from commit
  `9442efd`: Python 3.11-3.14, extension packaging, history and source privacy,
  reproducible distributions, exact candidate validation, product proof, and
  Pages staging all succeeded. `preflight` and all eight downstream public jobs
  were skipped.
- The authorized `v0.3.0` promotion run `29885612746` passed every repository,
  signed-tag, candidate, privacy, hidden-draft, public-state, OIDC, and Sigstore
  gate. PyPI then rejected the wheel because that exact `0.3.0` filename had
  also been uploaded and deleted previously. The public version endpoint
  remains 404; Release publication, Pages, and public verification were
  skipped. Hidden draft `357744277` retains exactly six hashed assets. Do not
  probe another `codetalk` version until the distribution-name decision is
  explicit.
- [x] Require the reusable test workflow, candidate validation, secret scan,
  product-proof test, and Pages artifact upload to pass.
- [x] Confirm every job after `candidate` is skipped.
- [x] Reconfirm that the rehearsal created no `v0.3.1` tag, public PyPI version,
  public GitHub Release, Pages deployment, or Homepage change.

The following owner actions were completed under explicit authorization:

- [x] Configure required reviewers and tag restrictions on the `release`, `pypi`,
  and `github-pages` environments.
- [x] Extend the repository tag ruleset to block update and deletion of `v0.3.1`,
  including administrator bypass during the promotion window.
- [x] Register the PyPI Pending Trusted Publisher with the exact values above.
- [x] Enable immutable Releases and verify
  `gh api repos/HUKAIR/CodeTalk/immutable-releases --jq .enabled` prints `true`.
- [x] Enable GitHub Pages with GitHub Actions as the source and verify
  `gh api repos/HUKAIR/CodeTalk/pages --jq .build_type` prints `workflow`.
- [x] Create a signed annotated `v0.3.1` tag at the fully verified preparation
  commit and confirm GitHub reports its signature as verified.
- [x] Push only that tag, then run
  `gh workflow run release.yml --ref v0.3.1 -f publish=true`.

Any future tag, package, Release, Pages, Homepage, or issue-state change requires
fresh explicit confirmation; this completed authorization does not carry over.

After promotion, verify from public endpoints:

- [x] `python3 -m pip install --no-cache-dir --no-deps hukair-codetalk==0.3.1` in a new
  virtual environment, followed by `codetalk --version`, `doctor`, and
  `review --json` in a synthetic repository.
- [x] `gh release verify v0.3.1` and `gh release verify-asset v0.3.1 <local-file>`
  for the wheel, sdist, MCP bundle, VSIX, SBOM, and `SHA256SUMS`.
- [x] Fetch the Pages root and `docs/images/codetalk-logo-banner.png`, then compare
  them byte-for-byte with a fresh local `stage-pages` output. The staged PNG is
  expected to differ from the source only by removed EXIF/text/time metadata.
- [ ] Set the repository Homepage only after a separate explicit product
  decision. It remains unset; successful publication does not silently change
  repository presentation.
- [x] Leave issue #142 open for a separate scope/title review; release
  verification must not silently close an issue whose title still names 0.2.0.

## Post-Release

- Watch install issues for command drift, MCP client differences, and Python
  version problems.
- Track warnings from full test runs separately from release blockers.
- Convert repeated support questions into README or docs updates.
