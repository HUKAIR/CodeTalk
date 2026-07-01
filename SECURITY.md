# Security Policy

CodeTalk is local-first software. Repository data, git history, cache files, and
session transcripts should stay on the user's machine except for explicit LLM
provider calls initiated by the user.

## Supported Versions

Security fixes target the latest `main` branch until formal releases are cut.

## Reporting a Vulnerability

Please report security issues privately before opening a public issue. If GitHub
private vulnerability reporting is enabled for the repository, use that flow.
Otherwise, contact the repository owner through GitHub with a minimal, non-public
reproduction.

Include:

- Affected command, API, or extension surface.
- Steps to reproduce.
- Whether the issue can expose local files, secrets, git history, or session
  content.
- Any logs after removing secrets and personal data.

## Security Expectations

- Do not send project data to third-party services except through explicit LLM
  provider configuration.
- Bind local web surfaces to loopback by default.
- Keep static browser assets free of external network dependencies.
- Redact common API key and token patterns before cache or log writes.
- Treat malformed external data as untrusted input: warn and degrade rather than
  crashing.
