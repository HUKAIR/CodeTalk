# Security Policy

CodeTalk is local-first software. Repository data, git history, cache files, and
session transcripts should stay on the user's machine except for explicit LLM
provider calls initiated by the user.

## Supported Versions

Security fixes target the latest `main` branch until formal releases are cut.

## Reporting a Vulnerability

Email **enjoyugavin@gmail.com** with a subject starting with "CodeTalk security".
Do not open a public issue, discussion, or pull request containing vulnerability
details, secrets, personal data, or reproduction steps. If you get no reply,
open an issue asking the maintainer to check the security mailbox, without any
technical details.

### Maintainer handling

Keep reports and reproductions in the agreed private channel. Confirm receipt,
assess exposure and affected versions, and agree on disclosure timing with the
reporter. Do not copy details into public issues, CI logs, or pull requests before
coordinating a fix. This project does not currently promise a response-time SLA.

In the private report, include:

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
python3 -m scripts.check_static_no_external codetalk/web_chat.html codetalk/console.html codetalk/tunnel.html codetalk/course.html codetalk/graph.html codetalk/trust_ab.html
HOME=/private/tmp/codetalk-test-home PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
git diff --check
```
