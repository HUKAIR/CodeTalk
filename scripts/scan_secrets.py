"""Scan repo files and optional git history for secret-shaped literals.

This is a release gate, not a replacement for provider-side secret revocation.
It reuses codetalk.config.SECRET_PATTERNS so the repository scan and runtime
redaction stay aligned.
"""
import argparse
import subprocess
import sys
from pathlib import Path

from codetalk.config import SECRET_PATTERNS, redact_secrets

ROOT = Path(__file__).resolve().parent.parent
MAX_BYTES = 1_000_000

_PATTERN_NAMES = [
    "openai-style-key",
    "github-token",
    "slack-token",
    "aws-access-key",
    "bearer-token",
    "key-value-secret",
    "google-api-key",
    "google-oauth-client",
    "stripe-key",
    "sendgrid-key",
    "jwt",
    "private-key-block",
    "slack-webhook",
]

_FIXTURE_MARKERS = (
    "sk-...",
    "sk-ABCDEF0123456789",
    "sk-abcdef0123456789",
    "sk-abcdefghijklmnop1234",
    "hunter2secretvalue",
    "ZxCvB12345Mn",
    "QwErTy123456Zx",
    "AIzaSyA1234567890abcdefghijklmnopqrstuvw",
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRST",
    "T00000000/B00000000/XXXXXXXXXXXXXXXX",
    "MIIEowIBAAKCAQEA1234567890abcdefBODYLINE",
)

_FIXTURE_PATHS = (
    "tests/",
    "docs/discovery/2026-06-30-隐私审计-五轮对抗log.md",
)


def _git(args, cwd=ROOT, text=True):
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          text=text, capture_output=True).stdout


def _decode(data):
    if b"\0" in data[:4096]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", "replace")


def _line_at(text, offset):
    line_no = text.count("\n", 0, offset) + 1
    start = text.rfind("\n", 0, offset) + 1
    end = text.find("\n", offset)
    if end == -1:
        end = len(text)
    return line_no, text[start:end]


def _is_fixture(line):
    return any(marker in line for marker in _FIXTURE_MARKERS)


def _is_fixture_path(path):
    return any(path == prefix.rstrip("/") or path.startswith(prefix)
               for prefix in _FIXTURE_PATHS)


def scan_text(text, source, path, ignore_fixtures=True):
    if ignore_fixtures and _is_fixture_path(path):
        return []
    findings = []
    for name, pattern in zip(_PATTERN_NAMES, SECRET_PATTERNS):
        for match in pattern.finditer(text):
            line_no, line = _line_at(text, match.start())
            if ignore_fixtures and _is_fixture(line):
                continue
            findings.append({
                "source": source,
                "path": path,
                "line": line_no,
                "kind": name,
                "context": redact_secrets(line.strip())[:220],
            })
    return findings


def repo_files(root=ROOT):
    raw = _git(["ls-files", "-z", "--cached", "--others", "--exclude-standard"],
               cwd=root)
    return [p for p in raw.split("\0") if p]


def scan_worktree(root=ROOT, max_bytes=MAX_BYTES, ignore_fixtures=True):
    findings = []
    for rel in repo_files(root):
        path = root / rel
        try:
            if path.stat().st_size > max_bytes:
                continue
            text = _decode(path.read_bytes())
        except OSError:
            continue
        if text is None:
            continue
        findings.extend(scan_text(text, "worktree", rel, ignore_fixtures))
    return findings


def history_objects(root=ROOT):
    for line in _git(["rev-list", "--objects", "--all"], cwd=root).splitlines():
        if " " not in line:
            continue
        oid, path = line.split(" ", 1)
        yield oid, path


def scan_history(root=ROOT, max_bytes=MAX_BYTES, ignore_fixtures=True):
    findings = []
    seen = set()
    for oid, path in history_objects(root):
        if oid in seen:
            continue
        seen.add(oid)
        try:
            if _git(["cat-file", "-t", oid], cwd=root).strip() != "blob":
                continue
            if int(_git(["cat-file", "-s", oid], cwd=root).strip()) > max_bytes:
                continue
            data = subprocess.run(["git", "cat-file", "blob", oid], cwd=root,
                                  check=True, capture_output=True).stdout
        except (OSError, subprocess.CalledProcessError, ValueError):
            continue
        text = _decode(data)
        if text is None:
            continue
        src = f"history:{oid[:12]}"
        findings.extend(scan_text(text, src, path, ignore_fixtures))
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Scan repo files and optional git history for secrets.")
    parser.add_argument("--history", action="store_true",
                        help="scan all reachable git blobs, not only HEAD")
    parser.add_argument("--strict-fixtures", action="store_true",
                        help="do not ignore known synthetic test secrets")
    parser.add_argument("--max-bytes", type=int, default=MAX_BYTES,
                        help="skip blobs larger than this size")
    args = parser.parse_args(argv)

    ignore_fixtures = not args.strict_fixtures
    findings = scan_worktree(ROOT, args.max_bytes, ignore_fixtures)
    if args.history:
        findings.extend(scan_history(ROOT, args.max_bytes, ignore_fixtures))

    unique = {(f["source"], f["path"], f["line"], f["kind"], f["context"]): f
              for f in findings}
    for f in unique.values():
        print(f"{f['source']} {f['path']}:{f['line']} "
              f"{f['kind']}: {f['context']}", file=sys.stderr)
    return 1 if unique else 0


if __name__ == "__main__":
    raise SystemExit(main())
