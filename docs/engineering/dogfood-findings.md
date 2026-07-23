# Dogfood Engineering Findings

## Purpose

Use CodeTalk against several real local repositories before wider promotion, then turn reproducible product gaps into regression tests and minimal fixes.

This review covered four anonymized repository shapes:

| Sample | Shape | Evidence profile |
|---|---|---|
| A | Large, long-lived repository | Commit decisions plus many agent sessions |
| B | Large, long-lived repository | Many agent sessions, no structured decision notes |
| C | Medium repository | Many agent sessions and an active working tree |
| D | Small repository | Short history and sparse evidence |

## Privacy Boundary

- All runs used local-only mode with remote enrichment disabled.
- Cache and configuration writes were redirected to an isolated temporary home.
- Source repositories were read but not modified.
- Repository names, absolute paths, session identifiers, prompts, source text, and raw transcripts are not recorded here.
- No LLM request or other source-data upload was made during dogfooding.

## Findings And Fixes

### Drift counted only a narrow commit window

**Observed:** files committed later in the same workstream were reported as missing because the old implementation reused the short session-to-commit alignment window.

**Risk:** false positives weaken trust in the primary drift signal.

**Fix:** a file now counts as landed when a commit at or after its known action time touches the same path. A commit from before the action is not accepted as proof.

**Regression coverage:** later commit accepted; earlier commit rejected.

### Parent and subagent summaries appeared as duplicate sessions

**Observed:** one logical session could appear in several rows because subagent summaries share the parent session identifier.

**Risk:** inflated issue counts and a noisy review experience.

**Fix:** summaries with the same source and session identifier are merged. Each file retains its latest known summary start, so an earlier commit cannot prove that a later subagent action landed.

**Regression coverage:** duplicate summaries merge; per-file latest action time is preserved.

### Default review ignored untracked text files

**Observed:** a repository with meaningful untracked work returned zero review cards.

**Risk:** the review command could report a clean result while new work was waiting outside Git's tracked diff.

**Fix:** the default working-tree review includes at most 60 untracked regular text files, each no larger than 1 MB. Symlinks, binary files, ignored files, directories, and oversized files are skipped.

**Regression coverage:** an untracked text file produces a review card with no fabricated evidence.

### Cold-start guidance overpromised the first result

**Observed:** the health check recommended `blame` as the first proof step even when a repository had no structured decisions or enriched narratives.

**Risk:** a new user could see only commit titles and conclude that the product had failed.

**Fix:** cold-start guidance now prioritizes installing the future decision recorder, then planning enrichment, and labels immediate blame output as a baseline that may contain only commit subjects.

**Regression coverage:** cold-start order and limitation text are asserted.

### Drift wording implied more certainty than the detector has

**Observed:** the interface could be read as proving that work was never committed or that the agent had made a false natural-language claim.

**Risk:** the product would overstate deterministic evidence as semantic judgment.

**Fix:** output now says that no later same-path commit was found. It explicitly states that the signal observes tool actions, not prose plans, completion percentage, design validity, or execution quality.

## Cross-Repository Result

- Previously reported late-commit false positives disappeared in the active medium repository.
- Repeated parent-session rows collapsed into a smaller set of logical sessions in the large session-heavy repository.
- Default review surfaced bounded untracked text changes that were previously invisible.
- Binary-only untracked noise remained excluded by design.
- Repositories with structured decision notes continued to produce grounded blame output.

## Known Limits

These are product boundaries, not resolved defects:

1. A fresh local-only `enrich --no-llm` run can attach deterministic evidence to existing narrative records, but it does not create full narratives from raw history. Cold-start value still depends on recorded decisions, prior narratives, or explicit remote enrichment.
2. Scanning a very large local session history can take about a minute. Incremental cache behavior exists, but first-run progress and source-level timing are not yet visible enough.
3. Drift remains a same-path temporal signal. It does not understand renames, equivalent changes elsewhere, reverted intent, no-op edits, or whether the final implementation is correct.
4. The bounded untracked review may omit files beyond its count or size limits. The current command does not yet summarize skipped-file counts.
5. Human review is still required before labeling a remaining drift row as an agent failure.

## Verification

- Drift regression suites: 12 tests passed.
- Review suite: 21 tests passed.
- Doctor suite: 4 tests passed.
- Release-contract and product-proof suites: 20 tests passed.
- Full suite: 832 tests passed in an isolated home with loopback access enabled for web tests.
- Patch whitespace validation passed.
- Touched production modules remain below the 300-line project limit.

## Release Assessment

The repaired flows are suitable for continued private dogfooding and carefully scoped external evaluation. They should not be presented as semantic proof that an AI lied, completed a task, or produced correct code. The defensible product behavior is narrower: CodeTalk preserves local evidence and highlights reviewable mismatches between recorded tool actions, repository history, and stated engineering decisions.
