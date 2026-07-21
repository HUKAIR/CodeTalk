# Require explicit consent for remote enrichment

CodeTalk keeps deterministic mode as the default activation path and treats
inspectable enrichment as an optional flagship capability. A remote enrichment
must show its bounded read scope, destination, redaction report, remaining
visible data categories, and a locally inspectable payload before the user
explicitly authorizes network egress; configuring an API key alone is not
consent. This adds friction and may reduce enrichment completion, but prevents a
privacy-sensitive user from mistaking secret redaction for anonymization or
local-first storage for zero egress.
