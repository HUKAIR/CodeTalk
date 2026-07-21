# Domain Docs

CodeTalk uses a single domain context for the CLI, MCP, web, and editor surfaces.

## Before exploring

- Read `CONTEXT.md` at the repository root when it exists.
- Read ADRs under `docs/adr/` that touch the area being changed.
- If either location does not yet exist, proceed silently. Domain-modeling flows
  create them only when real terminology or durable decisions are resolved.

## Vocabulary

Use the terms defined in `CONTEXT.md` in issue titles, specifications, tests, and
product copy. Do not introduce synonyms for concepts the glossary has already
resolved. A missing concept is a signal to revisit the domain model.

## Decision conflicts

If proposed work contradicts an existing ADR, name the conflict explicitly and
explain why the decision should be reopened. Never override an ADR silently.
