import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from scripts import scan_secrets


def _png(*chunks):
    out = bytearray(b"\x89PNG\r\n\x1a\n")
    for kind, body in [(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)),
                       *chunks, (b"IEND", b"")]:
        out += struct.pack(">I", len(body)) + kind + body
        out += struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    return bytes(out)


class TestScanSecrets(unittest.TestCase):
    def test_pattern_names_cover_runtime_patterns(self):
        self.assertEqual(len(scan_secrets._PATTERN_NAMES),
                         len(scan_secrets.SECRET_PATTERNS))

    def test_scan_text_reports_redacted_context(self):
        secret = "sk-realSecretValue1234567890"
        hits = scan_secrets.scan_text(f"token {secret}", "worktree", "x.py")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["kind"], "openai-style-key")
        self.assertNotIn(secret, hits[0]["context"])
        self.assertIn("[REDACTED]", hits[0]["context"])

    def test_known_fixture_secret_is_ignored_by_default(self):
        text = "fake fixture sk-ABCDEF0123456789ABCD"
        self.assertEqual(scan_secrets.scan_text(text, "worktree", "tests/x.py"), [])

    def test_strict_fixture_mode_reports_fixture_secret(self):
        text = "fake fixture sk-ABCDEF0123456789ABCD"
        hits = scan_secrets.scan_text(text, "worktree", "tests/x.py",
                                      ignore_fixtures=False)
        self.assertEqual(len(hits), 1)


    def test_named_home_path_is_reported(self):
        for text in ("cd /home/alice/proj", "open /Users/bob/x",
                     "C:\\Users\\carol\\x"):
            with self.subTest(text=text):
                hits = scan_secrets.scan_text(text, "worktree", "docs/x.md")
                self.assertEqual([h["kind"] for h in hits], ["private-path"])

    def test_home_path_without_named_user_is_allowed(self):
        for text in ("~/proj", "/home/ is a prefix", '"/Users/",',
                     "/home/runner/work/x"):
            with self.subTest(text=text):
                self.assertEqual(
                    scan_secrets.scan_text(text, "worktree", "x.py"), [])

    def test_local_marker_is_reported_case_insensitively_and_hidden(self):
        hits = scan_secrets.scan_text("author: Jane.Doe here", "worktree",
                                      "x.py", markers=["jane.doe"])
        self.assertEqual([h["kind"] for h in hits], ["private-marker"])
        self.assertNotIn("Jane.Doe", hits[0]["context"])

    def test_local_marker_applies_to_fixture_paths_too(self):
        hits = scan_secrets.scan_text("jane.doe", "worktree", "tests/x.py",
                                      markers=["jane.doe"])
        self.assertEqual(len(hits), 1)

    def test_load_markers_skips_blank_and_comment_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "markers.txt"
            path.write_text("# my info\n\n  jane.doe  \njane@mail.test\n",
                            encoding="utf-8")
            self.assertEqual(scan_secrets.load_markers(path),
                             ["jane.doe", "jane@mail.test"])
            self.assertEqual(scan_secrets.load_markers(Path(tmp) / "no"), [])

    def test_png_metadata_is_reported(self):
        clean = _png((b"sRGB", b"\x00"))
        dirty = _png((b"tEXt", b"Author\x00jane"))
        self.assertEqual(scan_secrets.scan_png(clean, "worktree", "a.png"), [])
        hits = scan_secrets.scan_png(dirty, "worktree", "a.png")
        self.assertEqual([h["kind"] for h in hits], ["png-metadata"])

    def test_commit_messages_are_scanned(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = lambda *a: scan_secrets._git(list(a), cwd=Path(tmp))
            run("init", "-q")
            run("-c", "user.name=t", "-c", "user.email=t@example.invalid",
                "commit", "-q", "--allow-empty", "-m", "fix /home/jane/repo")
            hits = scan_secrets.scan_commit_messages(Path(tmp))
            self.assertEqual([h["kind"] for h in hits], ["private-path"])


if __name__ == "__main__":
    unittest.main()
