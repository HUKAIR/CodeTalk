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

## Privacy Review Checklist

Before publishing a release, verify these controls still hold:

- `CODETALK_NO_LLM` and `--no-llm` must prevent all LLM calls and fall back to
  deterministic local retrieval.
- Cache writes must redact common secret patterns before persisting commit
  narratives, session summaries, daily digests, web conversations, and risk
  capsules.
- Web pages must only call same-origin local endpoints, and FastAPI/http.server
  surfaces must bind to `127.0.0.1`.
- MCP tool responses and web JSON/SSE responses must redact both success and
  error payloads before returning them to clients.
- Session parsers for Claude, Cursor, and Codex must be read-only, tolerant of
  malformed records, and cache only bounded summaries.

Release gate commands:

```bash
python3 -m scripts.scan_secrets
python3 -m scripts.scan_secrets --history
python3 -m scripts.check_static_no_external codetalk/web_chat.html codetalk/console.html codetalk/tunnel.html codetalk/course.html codetalk/graph.html
HOME=/private/tmp/codetalk-test-home PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
git diff --check
```
