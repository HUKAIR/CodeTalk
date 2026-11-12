# Development and merge policy

This policy applies to **HUKAIR/CodeTalk**, a public repository.
It does not authorize changes to any previous repository or publication service.

## Current enforcement

`main` is protected with the checked-in
[protection configuration](../.github/main-protection.json): the six required
checks below must pass on an up-to-date branch, conversations must be resolved,
and force pushes and branch deletion are blocked, including for administrators.
Read the live setting back with `gh api repos/HUKAIR/CodeTalk/branches/main/protection`
rather than assuming the file is applied.

Required approvals are set to **0**. GitHub disallows approving your own PR and
there is currently one maintainer, so a required approval would block every merge.
The owner chose this on 2026-11-12. Raise it to 1 once a second maintainer exists.

GitHub Actions is enabled with GitHub-owned actions only, full-SHA pinning,
read-only default tokens, and no token permission to approve PRs. Only merge
commits are enabled; auto-merge and automatic branch deletion are off.

Only `test.yml` is intended to run. It tests Python 3.11–3.14, extension builds,
secret/privacy boundaries, and reproducible candidate packages. Candidate artifacts
are internal CI outputs, not a release. `release.yml` must stay disabled in GitHub;
its root job is also disabled in source. Never dispatch it as part of development.
No PyPI, Marketplace, Release, or Pages publication is authorized by a passing CI.

## Branch and commit

1. Start from current `main`; use a short `codex/…`, `feat/…`, `fix/…`, or `docs/…`
   branch. Do not commit directly to main or force-push shared branches.
2. Keep one outcome per PR. Inspect the diff, untracked files, and staged paths.
   Exclude caches, transcripts, credentials, private workspace data, and build outputs.
3. Use the GitHub noreply identity. Stage named paths and commit those same paths:
   `git add -- path/to/file` then `git commit -m "Explain the change" -- path/to/file`.
   Immediately run `git show --name-status HEAD` and verify the file list.
4. Record durable choices using the exact prefixes in
   [agent_seed.md](../codetalk/agent_seed.md), including genuinely rejected alternatives.
5. Before each push or PR creation, run `git remote -v` separately and verify the
   selected remote resolves to `https://github.com/HUKAIR/CodeTalk.git`.
   Push to an explicit remote and always use `-R HUKAIR/CodeTalk` with `gh`.

## Validation before review

| Change | Required evidence |
|---|---|
| Every PR | `git diff --check`, focused checks, full CI on the final head |
| Python or shared behavior | Full `python -m unittest discover -s tests` with `.[web,test]` |
| Extension | `npm ci`, `npm run typecheck`, `npm run build`, `npm run package` |
| UI | Real desktop-browser interaction; desktop layout, keyboard and console checks |
| README / screenshots | Commands and relative links checked; synthetic data and image metadata verified |
| CI / packaging | Release contracts, secret scan, candidate build and validation |

The product targets desktop use. Mobile development and phone/touch-device
acceptance are outside scope, per the owner's 2026-11-05 direction.

A failed, cancelled, skipped, or never-started required job is not a passing check.
Billing/network failures remain blocked; do not weaken requirements to obtain green.
Record environment-specific test skips and their reasons in the PR.

## Review and merge

- PRs target `main` and use the repository template. Explain behavior, scope,
  validation, privacy/release impact, and rollback. Draft status means not ready.
- Record the **full 40-character head SHA** in the review evidence. Review the whole
  diff against the current base; new commits invalidate the previous review.
- An independent reviewer should examine correctness, security/privacy, tests,
  compatibility, and documented claims. Resolve actionable findings and discussions.
  Stop after three inconclusive review rounds and ask the owner to decide.
- If an independent reviewer is unavailable, only the owner may explicitly accept
  the exact SHA and its limitations. Self-review is not independent approval.
  Changes to governance, licensing, or publication controls need owner acceptance.
- Recheck that main has not moved, all six required job names below passed, and the
  final reviewed SHA is still the PR head. If main changed, update the branch and
  revalidate the resulting SHA before merging.
- Prefer a merge commit to preserve reviewed commit identity. Pin the merge:
  `gh pr merge NUMBER -R HUKAIR/CodeTalk --merge --match-head-commit FULL_SHA`.
  Do not use `--admin`, auto-merge around a blocker, or automatic branch deletion.
- Read back main and verify it contains the reviewed commit. Fast-forward the local
  checkout only when clean. Record the PR, reviewed SHA, merge SHA and checks.
- Retain the branch by default. Branch/worktree deletion requires proof that main
  contains every commit, plus any applicable explicit deletion approval.

## Apply or reapply server-side protection

An administrator applies the reviewed JSON:

```bash
git remote -v
gh api --method PUT repos/HUKAIR/CodeTalk/branches/main/protection \
  --input .github/main-protection.json
gh api repos/HUKAIR/CodeTalk/branches/main/protection
```

The target requires an up-to-date branch, resolved conversations, a PR (zero
approvals, see above), stale-review dismissal, and the checks `python (3.11)`, `python (3.12)`,
`python (3.13)`, `python (3.14)`, `release-gates`, and `vscode-extension` from
GitHub Actions (app ID 15368). Force-push and branch deletion are prohibited,
including for administrators. Verify actual job names against the latest PR run
before applying; the JSON must match GitHub's emitted contexts.

Do not lower the required checks to get a green merge. Repository merge-method
settings alone do not enforce this policy.

## Rollback and incidents

Revert the faulty change on a new branch and use the same PR/check/review path.
Do not rewrite main or silently discard user data. For an urgent blocker, stop
merging and ask the owner for a documented decision; no automatic bypass exists.

If CI can publish unexpectedly, disable `release.yml` immediately and tell the
owner. Disabling all Actions is a containment option if the affected workflow is
uncertain. Re-enabling requires verification of the publishing boundary.
Report accidental exposure before any cleanup; follow [SECURITY.md](../SECURITY.md).
