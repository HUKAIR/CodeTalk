# Product Polish Release

## Problem Statement

A target maintainer using coding agents on an established repository cannot
reliably see why a relevant approach was previously chosen or rejected while
reviewing a new local change. Existing CodeTalk output is verifiable but dense,
optional enrichment can send data as soon as a remote provider is configured,
and the project has no canonical installable release or immediate public proof.
The maintainer must be able to understand the relevant history, inspect any
network boundary, make the final judgment, and keep private repository data
local.

## Solution

Turn the local pre-commit review moment into CodeTalk's primary workflow.
CodeTalk presents a focused decision review card that separates decision
evidence, generated interpretation, and review judgment. Inspectable enrichment
becomes the flagship optional backfill: it previews the bounded input,
redaction effects, remote destination, and remaining visible data before a
remote model call can be explicitly approved. Judgments stay local and can be
exported only as a user-reviewed, sanitized summary. The complete experience is
distributed through PyPI, immutable GitHub Release assets, and a no-install
static demonstration.

## User Stories

1. As a target maintainer, I want CodeTalk to review my current local diff, so
   that relevant historical decisions return before I commit the change.
2. As a target maintainer, I want each potential conflict shown as one focused
   decision review card, so that I do not have to read a chronological history
   dump.
3. As a target maintainer, I want the previously rejected approach and its
   reason prioritized, so that I can understand the practical constraint first.
4. As a target maintainer, I want to see why the card appeared for this change,
   so that line-level or file-level association is not mistaken for semantic
   certainty.
5. As a target maintainer, I want human-authored decision evidence labeled
   separately from model-generated interpretation, so that readable prose is
   not mistaken for proof.
6. As a target maintainer, I want exact commit, diff, test, pull request, and
   verbatim session sources available behind the card, so that I can verify the
   original record when necessary.
7. As a target maintainer, I want generated interpretation labeled as generated,
   so that I know it can be incomplete or wrong.
8. As a target maintainer, I want CodeTalk to leave semantic applicability to
   me, so that a deterministic association does not become an unreliable
   automatic block.
9. As a target maintainer, I want to resolve a card as confirmed conflict,
   intentional exception, unrelated, or insufficient evidence, so that my real
   judgment is represented without forcing a binary answer.
10. As a target maintainer, I want to record whether a confirmed conflict
    changed my action, so that a verified interception is not confused with a
    warning I ignored.
11. As a target maintainer, I want terminal review output to remain concise and
    deterministic, so that coding agents and scripts can consume it safely.
12. As a target maintainer, I want a local review page with judgment controls
    and collapsible sources, so that I can make a careful human decision without
    parsing raw terminal output.
13. As a target maintainer, I want the terminal and local page to use the same
    card data, so that different surfaces cannot disagree about the evidence.
14. As a privacy-sensitive maintainer, I want deterministic mode to remain the
    default activation path, so that first use requires no model or network
    egress.
15. As a privacy-sensitive maintainer, I want remote enrichment to begin with a
    no-network plan, so that configuring an API key alone is never treated as
    consent.
16. As a privacy-sensitive maintainer, I want the plan to show the exact remote
    origin, provider, model, and commit scope, so that I know where data would go
    and how much work is proposed.
17. As a privacy-sensitive maintainer, I want the plan to list every input
    category and its size limit, so that "local-first" is not a vague promise.
18. As a privacy-sensitive maintainer, I want secret-redaction counts by
    category, so that I can see which protections actually matched.
19. As a privacy-sensitive maintainer, I want the plan to name ordinary source
    code, business logic, filenames, author data, and non-secret conversation
    text as potentially visible, so that redaction is not presented as
    anonymization.
20. As a privacy-sensitive maintainer, I want to inspect one fully redacted
    outbound payload locally, so that I can evaluate the actual material rather
    than trusting a badge.
21. As a privacy-sensitive maintainer, I want remote enrichment to require an
    explicit command flag, so that unattended scripts cannot start egress after
    a key is added.
22. As a privacy-sensitive maintainer, I want exact-loopback providers treated
    as local while still showing their input plan, so that local inference is
    transparent without being mislabeled as remote.
23. As a privacy-sensitive maintainer, I want provider retention described as
    outside CodeTalk's control, so that the product does not make promises for a
    third party.
24. As a target maintainer, I want review judgments stored locally without
    telemetry, so that product learning does not expose my repository.
25. As a target maintainer, I want to preview a feedback export before creating
    it, so that I control every field that leaves my machine.
26. As a target maintainer, I want feedback exports to omit repository identity,
    paths, source content, commit identifiers, sessions, and author identity, so
    that I can share product feedback safely.
27. As a new user, I want one canonical CLI installation command, so that I do
    not need a source checkout or editable Python install.
28. As a release user, I want Python, MCP, and editor artifacts to share one
    version, so that compatibility is understandable.
29. As a release user, I want immutable artifacts, checksums, an SBOM, release
    notes, and known limitations, so that I can verify what I install.
30. As a prospective user, I want to operate a sanitized decision review card
    without installing CodeTalk, so that I can understand the product before
    trusting it with a repository.
31. As a prospective user, I want inspectable enrichment demonstrated near the
    top of the public page, so that the privacy boundary is a primary product
    capability rather than fine print.
32. As a prospective user, I want the public page to lead from review card to
    inspectable enrichment to installation, so that there is one clear path
    instead of a catalogue of commands.
33. As a non-English reader, I want long labels and evidence to remain readable
    across supported languages and viewport sizes, so that the review decision
    is not obscured by layout failures.
34. As a reduced-motion user, I want the same information and controls without
    animation, so that visual presentation does not change the decision path.

## Implementation Decisions

- The primary workflow is local review after a coding agent has produced a diff
  and before commit or pull request submission.
- Review remains deterministic. CodeTalk surfaces potentially relevant rejected
  decisions but does not claim to detect semantic repetition or automatically
  block a change.
- Decision review cards are a shared structured contract consumed by terminal,
  local browser, and future editor or MCP surfaces. Renderers do not independently
  reconstruct or reinterpret evidence.
- A card separates current-change association, decision evidence, generated
  interpretation, provenance precision, and review judgment. Human-authored
  rejected paths with line-level provenance are shown first; supporting history
  is collapsed by default.
- The local browser runs on loopback through the existing standard-library local
  server boundary. It does not require the optional web application dependency.
- The four judgment outcomes are confirmed conflict, intentional exception,
  unrelated, and insufficient evidence. A confirmed conflict counts as a
  verified interception only when the maintainer also records that the proposed
  action changed.
- Judgment records stay in the local cache. They may retain local card and commit
  references, but no record is transmitted automatically.
- Feedback export is a separate user action with a preview. Its exported schema
  contains product version, judgment, action-changed status, evidence type,
  provenance precision, elapsed review time, and an optional approved comment.
  It excludes repository identity, paths, source content, commit identifiers,
  sessions, and author identity.
- Enrichment always completes deterministic evidence backfill first. Remote
  narrative generation cannot begin merely because a provider key exists.
- A remote enrichment plan identifies provider, exact destination origin, model,
  uncached commit count, input categories and caps, redaction counts, data still
  visible after redaction, local cache effects, and the provider-retention
  boundary. Producing the plan sends no request.
- A payload-preview option displays one post-redaction request locally. The
  default plan does not print repository content.
- Remote inference requires an explicit per-command authorization flag.
  Non-interactive execution without that flag cannot send project data.
- Exact loopback endpoints remain zero egress and do not require remote
  authorization, but their plan remains inspectable.
- Redaction reporting extends the existing redaction boundary without changing
  the rule that all network and persistence paths receive redacted data.
  Redaction statistics never include matched secret values.
- Secret redaction is always described as pattern-based protection, not
  anonymization. Ordinary code, business logic, filenames, author details, and
  conversation text may remain in a remote payload.
- Generated interpretation may improve readability but is never accepted as
  decision evidence. The original source remains available beside it.
- The initial public package version is synchronized to `0.2.1` across Python,
  MCP, and editor artifacts before release.
- PyPI is the canonical CLI distribution. The primary command is
  `pipx install codetalk`; `uv tool install codetalk` is a documented alternative.
- The GitHub Release contains wheel, source distribution, MCP bundle, editor
  package, SHA-256 checksums, SBOM, release notes, and known limitations.
- The static public demonstration contains synthetic, sanitized data and no
  remote runtime dependencies. It presents the review card first, inspectable
  enrichment second, and installation third.
- The repository's standard-library core, optional dependency boundaries,
  defensive external-data parsing, module-size limit, immutable SHA narrative
  cache, and redaction rules remain in force.

## Testing Decisions

- Prefer tests at user-visible seams. Unit tests supplement edge cases but do not
  substitute for real command, browser, and clean-install verification.
- Command tests run the real CLI against temporary Git repositories. A fake
  model client records attempted calls so tests prove that plans and previews
  perform no egress and that remote generation requires explicit authorization.
- Enrichment tests cover input categories, caps, exact destination reporting,
  category-only redaction statistics, post-redaction preview, loopback handling,
  non-interactive behavior, and existing immutable-cache behavior.
- Review tests begin with real committed decision notes and a local diff, then
  assert the structured card and terminal rendering. Existing review and blame
  tests provide the prior pattern.
- Card tests assert that source evidence, generated interpretation, provenance
  precision, and review judgment remain separate fields and labels.
- Local browser tests exercise all four outcomes, action-changed recording,
  source expansion, long text, invalid card identifiers, and loopback-only write
  behavior. Existing local console-server tests provide the prior pattern.
- Feedback tests complete a real local judgment and inspect the exported result,
  including adversarial repository names, paths, commit metadata, source text,
  session excerpts, author identity, and secret-shaped values.
- Browser QA uses desktop and mobile viewports, reduced-motion mode, interaction
  screenshots, overlap checks, and external-request monitoring.
- Release tests build every artifact, verify synchronized versions, install the
  wheel in a clean environment, launch the CLI, inspect archive contents, verify
  checksums and SBOM, and install the editor and MCP artifacts in clean clients.
- Static publication checks reject external scripts, network resources, private
  paths, sensitive values, stale internal document references, and formal public
  filenames containing dates or non-English characters.

## Out of Scope

- Automatic semantic classification of whether a change repeats a rejected
  approach.
- Automatic blocking, enforcement hooks, or cloud pull-request checks.
- Telemetry, automatic feedback upload, repository analytics, or customer-data
  collection.
- Design-partner recruitment, community promotion, Show HN, or paid acquisition.
- New model providers, vector databases, retrieval frameworks, or hosted memory.
- New graph, course, ADR, reporting, or export capabilities unrelated to the
  decision review and feedback loop.
- Marketplace publication as a blocker for the first polished release.
- Treating generated interpretation as evidence or correctness validation.
- Product renaming or a broad visual-brand redesign.

## Further Notes

- The product goal remains five external design partners and one verified
  interception, but recruitment starts only after this product-polish release
  meets its gates.
- Activation means a target maintainer finds evidence relevant to a recent or
  proposed change in their own repository and verifies its original source
  within five minutes of installation.
- A repository with no usable historical evidence is honestly recorded as not
  activated. The demo and enrichment plan must not conceal this cold-start
  boundary.
- The accepted privacy and review boundaries are recorded in the repository's
  domain glossary and ADRs.
