# Release Promotion Safety

## Status

Approved direction for preparing the CodeTalk 0.3.0 public release. This design
does not authorize creating a tag, publishing to PyPI, publishing a GitHub
Release, enabling GitHub Pages, or changing repository public settings.

## Goal

Promote one already-tested source commit to PyPI, GitHub Releases, and GitHub
Pages without long-lived publishing credentials, accidental tag-triggered
publication, artifact drift, or claims that become public before they can be
verified.

Success means:

- a manual dry run can build and validate the complete candidate without any
  publishing permission;
- public promotion requires an explicit boolean choice and protected GitHub
  environments;
- every public artifact is built once from the authenticated release tag and
  reused byte-for-byte across all publication steps;
- every archive is scanned before it leaves the builder for secret-shaped
  content, private build paths, unsafe member types, and prohibited public
  filenames;
- PyPI uses OpenID Connect Trusted Publishing rather than an API token;
- the GitHub Release exposes the wheel, source distribution, MCP bundle, VSIX,
  checksums, SBOM, release notes, and known limitations;
- GitHub Pages contains only the reviewed static proof page and its allowlisted
  local image;
- public endpoints are checked before issue #142 is closed.

## Alternatives Considered

### Selected: manual workflow with a safe default

A `workflow_dispatch` workflow defaults to dry-run mode. Publication jobs run
only when the operator explicitly enables promotion and all protected
environment approvals pass. This is slower than automatic release-on-tag, but
it makes intent visible and supports rehearsal before irreversible actions.

### Rejected: publish automatically when a tag is pushed

This is conventional, but a mistaken or prematurely pushed tag would begin
irreversible PyPI publication before the complete release could be reviewed.

### Rejected: publish each surface manually from a workstation

This avoids workflow complexity but weakens reproducibility, auditability,
least-privilege isolation, and proof that every surface received identical
bytes.

## Fixed Release Identity

The 0.3.0 workflow is release-specific:

- package version: `0.3.0`;
- tag: `v0.3.0`;
- release notes: `docs/releases/v0.3.0.md`;
- expected artifact names come from `scripts/release_artifacts.py`.

Dry runs build the immutable commit that started the workflow. Promotion must
be manually dispatched from the exact `v0.3.0` tag after that tag contains the
workflow. It must stop unless the tag resolves to the workflow run's commit and
GitHub reports the annotated tag signature as verified. This avoids a mutable
branch checkout and the impossible self-reference of embedding a commit's own
future hash inside that commit.

## Workflow Architecture

### 1. Candidate job

The candidate job has read-only repository permission. It checks out the exact
commit identified by the workflow event, runs the existing full release gates,
builds the Python, MCP, and editor packages once, validates metadata and archive
contents, writes the SBOM and checksums, and uploads one internal GitHub Actions
artifact named with that commit identity.

The job also stages the Pages payload from an explicit allowlist:

- `index.html`;
- `docs/images/codetalk-logo-banner.png`.

Static dependency and secret scans run against the staged payload before it is
uploaded. PNG text, EXIF, and time metadata are removed deterministically during
staging. No source tree, cache, local path, discovery document, or environment
file is included.

### 2. Promotion preflight

Promotion is disabled by default. When explicitly enabled, a preflight job
checks all of the following before any public write:

- the workflow was manually dispatched from the exact fixed release tag;
- the release tag resolves to the workflow run's immutable commit;
- GitHub reports the annotated tag signature as verified;
- the candidate artifact contains exactly the expected release files;
- `SHA256SUMS` validates every distributable and the SBOM;
- all package metadata reports version `0.3.0`;
- the release notes are publication-ready and do not claim candidate status;
- GitHub Pages is configured to deploy from Actions workflows.

Immediately before dispatch, the repository owner separately verifies that
immutable Releases are enabled through the administration endpoint. GitHub's
job token cannot read repository Administration settings, and the workflow
must not introduce a long-lived PAT merely to repeat that owner-side check.

The signed tag identity is checked again immediately before draft creation,
PyPI publication, and public Release publication. A repository tag ruleset must
also block updates and deletion of the fixed release tag.

### 3. Hidden GitHub Release draft

A job protected by the `release` environment creates or updates a draft for
the existing verified tag and attaches the validated candidate files. The
draft remains non-public while PyPI publication is pending. Re-runs may update
only this draft and must reject any existing asset with a different checksum.

### 4. PyPI Trusted Publishing

A separate job protected by the `pypi` environment receives only the wheel and
source distribution. It has `id-token: write` and no repository write
permission. The official PyPI publishing action is pinned to a full commit SHA.
No PyPI API token or other long-lived publishing secret is accepted.

Before first use, the PyPI pending publisher must be configured for repository
`HUKAIR/CodeTalk`, the exact workflow filename, and environment `pypi`.

A 404 from the public release endpoint proves only that no files are currently
listed. PyPI permanently reserves a filename after upload even if the release
is later deleted. If upload reports a deleted-filename tombstone, stop the
promotion, keep downstream publication closed, and advance the version. Never
enable `skip-existing` or weaken Trusted Publishing to recover.

### 5. Public GitHub Release

After PyPI succeeds, the `release` environment job confirms that the public
PyPI files have the expected SHA-256 values, then publishes the draft. The
repository's immutable releases setting must already be enabled. After
publication, the job requires the public Release itself to report
`immutable == true` and verifies the Release and every asset attestation.

### 6. GitHub Pages

Pages deploys last through the standard `github-pages` environment. Its job has
only `pages: write` and `id-token: write`, consumes the previously scanned
allowlisted payload, and uses official GitHub Pages actions pinned to full
commit SHAs. Pages source configuration remains an explicit repository setting
and is not changed by the preparation work.

### 7. Public verification

The workflow and the release checklist verify:

- PyPI metadata and hashes;
- installation of the public wheel in a clean environment;
- `codetalk --version`, `doctor`, and local review behavior;
- GitHub Release tag, assets, hashes, SBOM, notes, and immutable status;
- Pages availability, local asset loading, privacy copy, and absence of external
  runtime assets;
- repository Homepage URL after Pages is confirmed.

Issue #142 remains open if any public endpoint or hash cannot be verified.

## Permission Boundaries

The workflow declares `contents: read` by default and grants write permissions
only at job level:

- candidate and preflight: no write permission;
- release draft and publication: `contents: write`;
- PyPI: `id-token: write` only in addition to repository read access;
- Pages: `pages: write` and `id-token: write` only.

All third-party and GitHub-maintained actions are pinned to full commit SHAs.
Only actions with a direct role in checkout, runtime setup, artifact transfer,
PyPI Trusted Publishing, or Pages deployment are allowed.

## Failure And Recovery

Publication across PyPI, GitHub Releases, and Pages is not atomic.

- Failure before PyPI leaves only an internal Actions artifact and possibly a
  hidden GitHub Release draft.
- Failure after PyPI is an externally visible partial release. Marketing and
  issue closure stop; a re-run may only verify and reuse the exact PyPI bytes,
  then continue the remaining steps.
- Failure after the GitHub Release is public does not alter immutable assets;
  a later run accepts only the same immutable Release body and exact asset
  bytes, then resumes Pages deployment and verification.
- A checksum mismatch, version mismatch, unverified tag, missing environment,
  or unexpected public file is a hard stop. The workflow never overwrites a
  public package or silently skips a conflicting artifact.

## Tests

Repository tests will parse the workflow as text and structured YAML-compatible
data where the standard library permits, and assert:

- manual dispatch is the only trigger and dry run is the default;
- promotion conditions and fixed 0.3.0 identity are present;
- permissions are least-privilege and assigned per job;
- protected environments guard every public write;
- no token secret is referenced;
- expected artifacts, checksums, SBOM, release notes, and Pages allowlist are
  explicit;
- public jobs consume the candidate artifact rather than rebuilding it;
- official actions are pinned to full commit SHAs.

The workflow must also pass a real dry run on GitHub Actions before any tag is
created. Local verification continues to include the complete unit suite,
secret scans over the current tree and history, static dependency checks,
artifact validation, checksum verification, and clean package smoke tests.

## External Setup Gate

Preparation can be committed and pushed without changing public release state.
Promotion remains blocked until the owner explicitly confirms all of these:

- create and approve the protected `release`, `pypi`, and `github-pages`
  environments;
- register the PyPI pending Trusted Publisher;
- enable GitHub Actions as the Pages source;
- enable immutable GitHub Releases;
- create the verified annotated `v0.3.0` tag at the recorded source commit;
- protect `v0.3.0` against update and deletion with a repository tag ruleset;
- authorize the workflow's promotion input.

These actions are intentionally outside the preparation change because they
either alter public repository state or enable an irreversible publication
path.

## Out Of Scope

- publishing to an editor marketplace;
- publishing a Docker image;
- automatic publication for future versions;
- analytics or tracking on the Pages site;
- changing CodeTalk runtime privacy behavior;
- closing issue #142 before public verification succeeds.
