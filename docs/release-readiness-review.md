# Release Readiness Review

## Verdict

CodeTalk is ready for a non-publishing 0.2.2 release rehearsal and remains ready
for a source-install pilot from the public repository. It is not yet ready to
claim general package distribution: no immutable GitHub Release, PyPI package,
or Marketplace listing has been published and verified from an independent
clean client.

This review does not claim mathematical certainty. It records the concrete
threats checked, the defects found, the fixes applied, and the evidence needed
to reproduce the conclusion.

## Product Contract

- The CLI and MCP core use the Python standard library only.
- Git history and supported local coding-session files are read locally.
- Deterministic retrieval does not require an LLM.
- Optional LLM synthesis is explicit, uses the shared `llm.py` boundary, and
  receives redacted material.
- `--no-llm`, `CODETALK_NO_LLM=1`, or `no_llm: true` is the documented
  zero-egress mode.
- The web service binds to loopback by default. Docker publication must map the
  container port to host loopback, for example
  `-p 127.0.0.1:8000:8000`.

## Findings And Fixes

### Privacy And Security

- Replaced Docker's broad repository copy with an explicit runtime allowlist.
  `.dockerignore` now denies all inputs by default and admits only package files.
- Hardened local LLM detection by parsing the URL and accepting only exact
  loopback hostnames: `localhost`, `127.0.0.1`, and `::1`. A deceptive hostname
  such as `localhost.example.com` and a remote provider marked `local: true` no
  longer bypass the API-key requirement.
- Kept the web server on loopback by default and retained Host/Origin checks,
  CSP, strict commit-SHA validation, and response-wide secret redaction.
- Corrected absolute privacy claims in the UI, MCP guide, and web startup log.
  The public contract is now local-first, with explicit zero-egress controls.
- Enabled GitHub Private Vulnerability Reporting and linked `SECURITY.md`
  directly to the repository's private advisory form.
- Replaced a fixed shared temporary directory and recursive deletion in the MCP
  guide with `mktemp -d`.

### Correctness And Product Clarity

- Standardized the public term "decision notes" and defined the three concrete
  commit-message records: `Vibe-Decision`, `Vibe-Rejected`, and `Vibe-Watch`.
- Made decision-note coverage count all three record types consistently while
  documenting that `digest` and `graph` intentionally consume narrower subsets.
- Fixed the console search-results drawer so the CSS `hidden` state works on
  first load and after closing.
- Corrected stale capability counts and commands: six console views, seven MCP
  tools, five agent-seed files, and the lowercase Python module name.
- Removed frozen coverage figures from README; the live script is now the source
  for changing repository metrics.
- Replaced unsupported "one-click" distribution language with the actual
  source-build requirement until downloadable releases exist.

### Release Engineering

- Expanded CI to Python 3.11 through 3.14 and Node.js 24.
- Separated Starlette's `httpx2` test-client dependency into a test-only extra;
  it does not enter the Web runtime or stdlib core dependency surfaces.
- Added full-history secret scanning, all six static-page checks, MCP bundle
  creation, Python sdist/wheel build, isolated wheel launch, VSIX packaging, and
  artifact uploads.
- Limited workflow token permissions to read-only, disabled persisted checkout
  credentials, and pinned official actions to full immutable Node 24 release
  SHAs. Release gates install the core package rather than the Web extra.
- Pinned the VS Code packager to `@vscode/vsce` 3.9.2.
- Updated Python metadata to the SPDX `AGPL-3.0-or-later` license expression and
  explicit Python 3.11-3.14 classifiers.
- Added release-contract tests for the Docker boundary, public capability copy,
  formal documentation, package metadata, and CI gates.
- Added a manual release workflow whose required `publish` input defaults to
  false and whose public jobs are separated by protected environments.
- Added exact six-file validation, checksums, CycloneDX 1.6 SBOM validation,
  byte-level PyPI recovery, and a two-file Pages allowlist.
- Added archive privacy inspection before the candidate leaves its builder. The
  sdist excludes test fixtures; wheel, sdist, MCPB, and VSIX contents are scanned
  for secret-shaped text, private build paths, unsafe members, and prohibited
  public filenames.
- Added deterministic removal of PNG EXIF, text, and time metadata while
  preserving the original compressed pixel chunks.
- Recorded that a PyPI 404 cannot reveal deleted-filename tombstones. The
  `0.2.0` and `0.2.1` uploads authenticated through OIDC but failed closed on
  PyPI's permanent filename reservations; recovery advances to `0.2.2` without
  a token, `skip-existing`, or weaker verification.
- Recheck the signed annotated tag immediately before draft creation, PyPI
  publication, and public Release publication. Existing public Releases are
  accepted only when immutable and byte-identical, allowing Pages recovery.

## Verification Evidence

The final local review ran the following checks from a clean, isolated home
directory where applicable:

- Python unit suite: 825 tests passed.
- Worktree and full-git-history secret scans: passed.
- Six standalone HTML pages: no external runtime assets detected.
- Python sdist and wheel: built; wheel installed into a fresh virtual
  environment; `python -P -m codetalk --version` launched the installed copy.
- MCP bundle: built, unpacked, initialized, and returned seven read-only tools.
- VS Code extension: `npm ci`, typecheck, build, package, archive validation, and
  production dependency audit passed; the VSIX contains the AGPL license and
  installed as `codetalk.vscode-codetalk@0.2.2` in isolated VS Code and Cursor
  profiles without touching the existing profiles.
- Docker: image built from the allowlisted context; loopback-mapped home page
  returned HTTP 200; a forged non-loopback Host header returned HTTP 403.
- Browser QA: the current console rendered with an isolated empty CodeTalk cache;
  the hidden search drawer no longer obscured the main interface.
- Repository constraints: all Python modules remain below 300 lines and
  `git diff --check` passed.
- Two independently built 0.2.2 candidates produced byte-identical wheels and
  normalized sdists. The assembled six-file candidate passed exact-set,
  checksum, SBOM, archive privacy, and status-neutral release-note validation.
  Its wheel installed with no dependencies in a fresh environment; `--version`
  and `doctor` launched the installed copy.
- GitHub Actions run
  [`29871281164`](https://github.com/HUKAIR/CodeTalk/actions/runs/29871281164)
  completed successfully from commit `97f5d3c`: all build and candidate jobs
  passed, while preflight and every publication job were skipped.
- The authorized `v0.2.0` promotion run
  [`29880629420`](https://github.com/HUKAIR/CodeTalk/actions/runs/29880629420)
  passed repository, candidate, signed-tag, and OIDC gates. PyPI rejected the
  permanently reserved deleted filenames, so Release publication, Pages, and
  public verification stayed skipped. The Release remains a hidden draft;
  PyPI has no public `codetalk` version and the Homepage remains unchanged.
- The `0.2.1` rehearsal
  [`29881493075`](https://github.com/HUKAIR/CodeTalk/actions/runs/29881493075)
  passed all non-publishing gates. Promotion run
  [`29882535367`](https://github.com/HUKAIR/CodeTalk/actions/runs/29882535367)
  reached OIDC successfully and found the same deleted-filename tombstone for
  `0.2.1`; every downstream public job remained skipped.
- The synchronized `0.2.2` rehearsal
  [`29884029536`](https://github.com/HUKAIR/CodeTalk/actions/runs/29884029536)
  passed the Python 3.11-3.14 matrix, extension build, full-history and source
  privacy scans, reproducible distributions, candidate and product-proof gates,
  and Pages staging. Every public job was skipped.

## Remaining Release Gates

These are evidence gaps, not hidden implementation claims:

- Open the installed VSIX in an independent editor profile and visually verify
  CodeLens and hover cards on a real committed file. Package installation has
  passed in isolated VS Code and Cursor profiles; MCP initialization and
  `tools/list` have passed from the unpacked bundle.
- Replace the protected-environment tag policies with exact `v0.2.2`, then
  create and verify the signed tag at the final recorded source commit.
- Publish and verify a GitHub Release before describing the MCP bundle or VSIX as
  directly downloadable.
- Publish and verify PyPI only if `pip install codetalk` will be advertised.
- Collect at least one external pilot interception. The current blind comparison
  is useful but small (`N=5`, one repository, human judged).
- Add a short current-product demo recording before a broad launch.
- Monitor the optional Web test stack when dependency versions move; CI now
  installs the test client's declared dependency explicitly rather than relying
  on an older transitive `httpx` installation.

## Safest Release Path

1. Merge and publish this source hardening with the install promise limited to
   clone plus local editable install.
2. Run the clean-client checks in `RELEASE_CHECKLIST.md` without personal cache,
   credentials, or preinstalled CodeTalk state.
3. Create immutable GitHub artifacts only after the version and artifact hashes
   are fixed.
4. Expand distribution claims only after each advertised installation path has
   been tested from the public artifact itself.
