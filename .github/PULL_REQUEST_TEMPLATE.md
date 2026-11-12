## Problem and result

Describe the concrete problem and the resulting behavior. Link the relevant issue
or decision, and identify scope deliberately left out.

## Validation

- Commands and results (include skipped checks and why):
- CI run on the final head:
- UI screenshots or demo, if relevant (synthetic data only):

## Review and integration

- Full reviewed head SHA:
- Reviewer / owner acceptance and unresolved findings:
- [ ] Final head matches the reviewed SHA; any new commit gets re-reviewed
- [ ] Required CI jobs passed and main has not moved
- [ ] Conversations resolved; merge commit with `--match-head-commit`; keep branch

`main` protection requires the six CI checks; approvals are not required while
there is a single maintainer. See [development policy](../docs/development.md).

## Impact and rollback

- Privacy, cache, compatibility, or dependency impact:
- Publication remains disabled; describe any CI / packaging impact:
- Revert or recovery steps:

Record durable choices in commit bodies using `Vibe-Decision:`, `Vibe-Rejected:`,
and `Vibe-Watch:` as defined by `codetalk/agent_seed.md`.
