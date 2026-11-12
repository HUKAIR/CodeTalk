# Keep review outcomes local until explicit export

Decision review outcomes are stored locally with enough metadata to determine
whether a confirmed conflict changed the proposed action, but CodeTalk sends no
telemetry. External feedback is a separate, user-reviewed export that omits
repository identity, source content, commit identifiers, sessions, and author
identity. This requires explicit follow-up, but keeps product evaluation from
weakening the privacy boundary the maintainer is being asked to trust.
