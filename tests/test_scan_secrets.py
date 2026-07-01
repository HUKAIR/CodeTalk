import unittest

from scripts import scan_secrets


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


if __name__ == "__main__":
    unittest.main()
