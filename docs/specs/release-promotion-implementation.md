# Release Promotion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a manual, dry-run-first 0.2.0 release workflow that builds once,
uses short-lived publishing identity, and cannot publish until the verified tag
and protected external settings are in place.

**Architecture:** Reuse the existing test workflow as the sole artifact builder.
A focused standard-library helper validates candidate files, stages the exact
Pages allowlist, and compares PyPI hashes. A manual orchestration workflow moves
the same candidate through a hidden Release draft, PyPI Trusted Publishing,
immutable GitHub Release publication, Pages deployment, and public checks.

**Tech Stack:** GitHub Actions, Python 3.11 standard library, GitHub CLI, PyPI
OIDC Trusted Publishing, GitHub Pages.

## Global Constraints

- Preparation must not create a tag, publish a package or Release, enable Pages,
  change the repository Homepage, or close issue #142.
- The only workflow trigger is `workflow_dispatch`; `publish` is a required
  boolean with default `false`.
- Release identity is fixed to package `codetalk`, version `0.2.0`, and tag
  `v0.2.0`.
- Core runtime dependencies remain empty; new validation code uses only the
  Python standard library.
- Every Python module remains below 300 lines.
- Public artifacts are built once and reused byte-for-byte.
- Public writes require the `release`, `pypi`, or `github-pages` protected
  environment and job-level least privilege.
- PyPI publishing uses OIDC and must not reference a token secret.
- All external actions are pinned to full verified commit SHAs.
- Public Pages content is exactly `index.html` and
  `docs/images/codetalk-logo-banner.png`.
- No formal public filename introduced by this work contains a date or
  non-English characters.
- Do not run `npm ci` locally because it replaces `node_modules`; the fresh
  GitHub runner remains responsible for that clean install.

## File Map

- Create `scripts/release_promotion.py`: release candidate, Pages allowlist, and
  PyPI hash checks with a small command-line interface.
- Create `tests/test_release_promotion.py`: tests helper behavior and workflow
  safety contracts.
- Create `.github/workflows/release.yml`: manual dry run and guarded promotion.
- Modify `.github/workflows/test.yml`: expose the existing complete test and
  artifact build as a reusable workflow.
- Modify `docs/releases/v0.2.0.md`: make the notes suitable for both the tag and
  public Release without claiming publication early.
- Modify `RELEASE_CHECKLIST.md`: document external settings, dry run, exact
  promotion command, and public verification.
- Keep `CHANGELOG.md` marked `Unreleased` until the actual tag authorization.

---

### Task 1: Testable Promotion Validation

**Files:**
- Create: `tests/test_release_promotion.py`
- Create: `scripts/release_promotion.py`

**Interfaces:**
- Consumes: `scripts.release_artifacts.VERSION`, `SBOM_NAME`,
  `expected_artifact_names()`, and `validate_artifacts()`.
- Produces: `expected_release_files() -> tuple[str, ...]`,
  `validate_candidate(directory, notes_path) -> None`,
  `stage_pages(repository, destination) -> tuple[Path, ...]`, and
  `pypi_state(directory, payload) -> str`.

- [ ] **Step 1: Write failing tests for the exact release set**

Add tests that create six minimal named files and assert that an extra file,
missing checksum entry, changed digest, or candidate-status release note raises
`ValueError`. Patch `validate_artifacts` only to isolate the new exact-set rule:

```python
@mock.patch("scripts.release_promotion.validate_artifacts")
def test_candidate_rejects_an_unexpected_file(self, validate):
    self.make_candidate()
    (self.dist / "private.txt").write_text("no", encoding="utf-8")
    with self.assertRaisesRegex(ValueError, "unexpected release files"):
        validate_candidate(self.dist, self.notes)
```

- [ ] **Step 2: Run the new tests and verify RED**

Run: `python3 -m unittest tests.test_release_promotion -v`

Expected: `ModuleNotFoundError: No module named 'scripts.release_promotion'`.

- [ ] **Step 3: Implement exact candidate and checksum validation**

Implement constants from the existing artifact module and use `hashlib`,
`json`, and `pathlib`, not shell parsing:

```python
def expected_release_files():
    return expected_artifact_names() + (SBOM_NAME, "SHA256SUMS")

def validate_candidate(directory, notes_path):
    directory = Path(directory)
    found = tuple(sorted(path.name for path in directory.iterdir()
                         if path.is_file()))
    expected = tuple(sorted(expected_release_files()))
    if found != expected:
        raise ValueError("unexpected release files")
    validate_artifacts(directory)
    verify_checksum_manifest(directory)
    validate_sbom(directory)
    validate_release_notes(notes_path)
```

`verify_checksum_manifest()` must reject malformed lines, duplicate names,
absolute or nested paths, unknown files, omitted distributables, and any digest
mismatch. `validate_sbom()` must require CycloneDX 1.6 and exact matching names
and SHA-256 values for all four primary artifacts. `validate_release_notes()`
must reject `Release Candidate`, `not been published`, and `Unreleased`.

- [ ] **Step 4: Add and test the Pages allowlist**

Create a synthetic repository, add both allowed files plus a private file, and
assert only the two allowed paths are staged. Reject missing files, symlinks,
and a non-empty destination:

```python
PAGES_FILES = (
    Path("index.html"),
    Path("docs/images/codetalk-logo-banner.png"),
)
```

Run: `python3 -m unittest tests.test_release_promotion -v`

Expected: the candidate and Pages tests pass.

- [ ] **Step 5: Add and test PyPI state comparison**

Pass decoded PyPI JSON into `pypi_state()`. Return `"verified"` only when the
0.2.0 release contains exactly the expected wheel and sdist and both public
SHA-256 digests match local bytes. Return `"publish"` only for an explicit
not-found payload. Raise `ValueError` for an existing partial or mismatched
release.

The CLI exposes these commands:

```text
python -m scripts.release_promotion validate-candidate DIST NOTES
python -m scripts.release_promotion stage-pages REPOSITORY DESTINATION
python -m scripts.release_promotion pypi-state DIST
```

The network command catches only HTTP 404 as `publish`; every other network or
JSON error fails closed.

- [ ] **Step 6: Verify GREEN and module size**

Run:

```bash
python3 -m unittest tests.test_release_promotion -v
wc -l scripts/release_promotion.py
```

Expected: all tests pass and the module is below 300 lines.

- [ ] **Step 7: Commit the validation boundary**

```bash
git add -- scripts/release_promotion.py tests/test_release_promotion.py
git commit -m "build(release): validate promotion inputs" \
  -m "Vibe-Decision: Validate an exact six-file candidate, an explicit Pages allowlist, and public PyPI hashes with one standard-library boundary."
```

---

### Task 2: Reusable Candidate Build And Guarded Workflow

**Files:**
- Modify: `.github/workflows/test.yml`
- Create: `.github/workflows/release.yml`
- Modify: `tests/test_release_promotion.py`

**Interfaces:**
- Consumes: Actions artifact `codetalk-release-candidate-${{ github.sha }}` produced by
  `.github/workflows/test.yml`.
- Produces: reusable `verify` job, scanned `github-pages` artifact, guarded
  draft/PyPI/Release/Pages jobs, and a no-write dry run.

- [ ] **Step 1: Write failing workflow contract tests**

Add tests that require:

```python
self.assertIn("workflow_call:", test_workflow)
self.assertIn("workflow_dispatch:", release_workflow)
self.assertIn("default: false", release_workflow)
self.assertNotIn("secrets.", release_workflow)
self.assertIn("uses: ./.github/workflows/test.yml", release_workflow)
self.assertNotIn("python -m build", release_workflow)
```

Also assert exact tag/version strings, all three environment names, explicit
job permissions, six artifact names, the two Pages paths, the commit-bound
candidate artifact name, seven-day retention, and the fixed action SHAs below.
Reject every non-local `uses:` value that does not end in 40 lowercase
hexadecimal characters.

- [ ] **Step 2: Run the workflow tests and verify RED**

Run: `python3 -m unittest tests.test_release_promotion -v`

Expected: failure because `.github/workflows/release.yml` is absent.

- [ ] **Step 3: Make the existing test workflow reusable**

Add the reusable trigger:

```yaml
on:
  push:
  pull_request:
  workflow_call:
```

Keep all existing matrix, release-gate, editor, secret-scan, reproducibility,
and build steps unchanged. Change only the complete candidate upload to:

```yaml
- uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a
  with:
    name: codetalk-release-candidate-${{ github.sha }}
    path: dist/*
    if-no-files-found: error
    retention-days: 7
```

- [ ] **Step 4: Implement the dry-run path**

Create `.github/workflows/release.yml` with `contents: read` by default, a
non-cancelling concurrency group, and this flow:

```yaml
jobs:
  verify:
    uses: ./.github/workflows/test.yml
    permissions:
      contents: read
  candidate:
    needs: verify
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0
      - uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1
      - uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c
      - run: python -m scripts.release_promotion validate-candidate dist docs/releases/v0.2.0.md
      - run: python -m scripts.release_promotion stage-pages . pages
      - run: python -m scripts.scan_secrets
      - run: python -m scripts.check_static_no_external pages/index.html
      - uses: actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9
```

Download the exact artifact name
`codetalk-release-candidate-${{ github.sha }}`. Use explicit action inputs,
`persist-credentials: false`, and `if-no-files-found: error`. The dry-run path
ends after `candidate` when `publish` is false.

- [ ] **Step 5: Implement tag and repository-setting preflight**

Add `preflight` with `if: ${{ inputs.publish }}`, environment `release`, and
read-only permissions. It must require:

```text
github.ref == refs/tags/v0.2.0
annotated tag object type == tag
tag verification.verified == true
tag target type == commit
tag target SHA == github.sha
immutable releases enabled == true
Pages build_type == workflow
```

Use `gh api` and `jq -e`; pass `${{ github.token }}` through `GH_TOKEN`. Any
missing API permission or false setting stops promotion. This deliberately
fails closed instead of accepting a long-lived administrator secret.

- [ ] **Step 6: Implement hidden draft and idempotent PyPI flow**

Add jobs in this order:

1. `draft-release` (`release`, `contents: write`) creates the verified-tag draft
   and uploads exactly the validated six files. On re-run, it accepts only an
   existing draft with byte-identical assets.
2. `inspect-pypi` compares local files with public PyPI and outputs `publish` or
   `verified`.
3. `publish-pypi` (`pypi`, `id-token: write`) runs only for `publish` and sends
   only the wheel and sdist through
   `pypa/gh-action-pypi-publish@ba38be9e461d3875417946c167d0b5f3d385a247`.
4. `verify-pypi` runs after success or a safe skip and requires state
   `verified`.

Do not use `skip-existing`; an existing mismatched version is a hard failure.

- [ ] **Step 7: Implement immutable Release and Pages publication**

`publish-release` uses `gh release edit v0.2.0 --draft=false --latest`, then
requires `gh release verify v0.2.0`, `gh release verify-asset` for all six files,
and REST field `immutable == true`.

`deploy-pages` runs last with environment `github-pages`, `pages: write`, and
`id-token: write` using:

```yaml
- id: deployment
  uses: actions/deploy-pages@cd2ce8fcbc39b97be8ca5fce6e763baed58fa128
```

Add `verify-public` after deployment. It must download the candidate, require
`pypi-state` to return `verified`, verify the immutable Release and each local
asset with GitHub CLI, fetch the Pages HTML and local logo, reject external
runtime assets, and install `codetalk==0.2.0` from public PyPI into a clean
virtual environment for `--version`, `doctor`, and local review smoke checks.
No workflow job changes the repository Homepage or closes issue #142.

- [ ] **Step 8: Verify workflow contracts GREEN**

Run:

```bash
python3 -m unittest tests.test_release_promotion -v
python3 -m unittest tests.test_release_candidate -v
git diff --check
```

Expected: all tests pass and no whitespace errors are reported.

- [ ] **Step 9: Commit the guarded workflow**

```bash
git add -- .github/workflows/test.yml .github/workflows/release.yml tests/test_release_promotion.py
git commit -m "ci(release): add guarded 0.2.0 promotion" \
  -m "Vibe-Decision: Reuse the tested candidate and require explicit publish input, verified tag, protected environments, OIDC, and immutable assets." \
  -m "Vibe-Watch: The immutable-release preflight depends on GitHub granting the job token read access to the repository setting and must be proven before promotion."
```

---

### Task 3: Publication-Ready Notes And Operator Checklist

**Files:**
- Modify: `docs/releases/v0.2.0.md`
- Modify: `RELEASE_CHECKLIST.md`
- Modify: `tests/test_release_candidate.py`

**Interfaces:**
- Consumes: the fixed workflow, environment names, and release artifact set.
- Produces: status-neutral release notes and exact owner-operated setup steps.

- [ ] **Step 1: Write failing release-copy tests**

Require the release heading `# CodeTalk 0.2.0`, the four known limitations,
all six artifact names, `workflow_dispatch`, the three environment names,
Trusted Publisher, immutable Releases, and Pages setup. Reject `Release
Candidate`, `not been published`, and any instruction claiming issue #142 is
complete before endpoint checks.

- [ ] **Step 2: Run release-copy tests and verify RED**

Run: `python3 -m unittest tests.test_release_candidate -v`

Expected: failure on the current candidate-status wording.

- [ ] **Step 3: Make release notes status-neutral**

Retitle the notes `# CodeTalk 0.2.0`, preserve the product workflow and honest
limitations, list all six public assets, and replace the candidate gate with an
integrity section explaining `SHA256SUMS`, CycloneDX SBOM, and immutable GitHub
Release verification. Do not state that publication has already occurred.

- [ ] **Step 4: Extend the operator checklist**

Add an exact `0.2.0 Promotion` section recording the current blocked state and
the owner actions:

```text
release, pypi, github-pages environments: not configured
PyPI pending Trusted Publisher: requires owner setup
immutable Releases: currently disabled
Pages: currently disabled
```

Document the dry run first, the owner-side setting checks, the future
`gh workflow run release.yml --ref v0.2.0 -f publish=true` command, public PyPI
install, `gh release verify`, `gh release verify-asset`, Pages asset checks, and
Homepage update only after the site is reachable. State that these public
actions require a fresh explicit confirmation.

- [ ] **Step 5: Verify and commit documentation**

Run:

```bash
python3 -m unittest tests.test_release_candidate -v
python3 -m unittest tests.test_release_promotion -v
git diff --check
```

Then commit:

```bash
git add -- docs/releases/v0.2.0.md RELEASE_CHECKLIST.md tests/test_release_candidate.py docs/specs/release-promotion-implementation.md
git commit -m "docs(release): define 0.2.0 promotion runbook" \
  -m "Vibe-Decision: Keep release notes status-neutral and keep every public repository or registry change behind a fresh owner confirmation."
```

---

### Task 4: Full Verification And Dry Run

**Files:**
- Verify all modified files; make no unrelated edits.

**Interfaces:**
- Consumes: all tasks above.
- Produces: a pushed preparation commit and a successful non-publishing Actions
  run, or a precise blocker with no public release state changed.

- [ ] **Step 1: Run the complete local suite**

Run:

```bash
python3 -m unittest discover -s tests
python3 -m scripts.scan_secrets
python3 -m scripts.scan_secrets --history
python3 -m scripts.check_static_no_external index.html codetalk/web_chat.html codetalk/console.html codetalk/tunnel.html codetalk/course.html codetalk/graph.html codetalk/trust_ab.html
git diff --check HEAD~3
```

Expected: all tests and scans pass. Do not claim completion from partial output.

- [ ] **Step 2: Inspect history and working tree**

Run:

```bash
git status --short --branch
git log -4 --format=fuller
git diff origin/main...HEAD --stat
```

Expected: only the approved design, plan, helper, workflow, tests, notes, and
checklist are ahead of `origin/main`; every implementation commit contains a
`Vibe-Decision:` body.

- [ ] **Step 3: Push preparation only**

Push `main` without tags. Confirm `git tag --list` remains empty and no public
Release exists.

- [ ] **Step 4: Trigger the safe dry run**

Run:

```bash
gh workflow run release.yml --ref main -f publish=false
```

Watch the run to completion. Expected: reusable test and candidate jobs pass;
all promotion, PyPI, Release, and Pages deployment jobs are skipped.

- [ ] **Step 5: Re-check public state**

Confirm no `v0.2.0` tag, GitHub Release, PyPI 0.2.0 project, Pages site, or
Homepage change was created. Leave issue #142 open.

- [ ] **Step 6: Stop at the irreversible gate**

Report the dry-run URL and the remaining owner actions. Request fresh explicit
confirmation before enabling settings, creating the verified tag, or running
with `publish=true`.
