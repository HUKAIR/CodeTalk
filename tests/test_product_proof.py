"""Public no-install proof and repository entry stay on one safe path."""
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PROOF = ROOT / "index.html"


class _AssetParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.assets = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag in {"script", "img", "source"} and values.get("src"):
            self.assets.append(values["src"])
        if tag == "link" and values.get("href"):
            self.assets.append(values["href"])


class TestNoInstallProductProof(unittest.TestCase):
    def setUp(self):
        self.html = PROOF.read_text(encoding="utf-8") if PROOF.exists() else ""

    def test_static_entry_exists(self):
        self.assertTrue(PROOF.is_file())

    def test_review_card_is_first_and_exercises_every_outcome(self):
        review = self.html.find('id="review"')
        enrichment = self.html.find('id="enrichment"')
        install = self.html.find('id="install"')
        self.assertGreaterEqual(review, 0)
        self.assertGreaterEqual(enrichment, 0)
        self.assertGreaterEqual(install, 0)
        self.assertLess(review, enrichment)
        self.assertLess(enrichment, install)
        for outcome in (
                "confirmed_conflict", "intentional_exception", "unrelated",
                "insufficient_evidence"):
            self.assertIn(f'value="{outcome}"', self.html)
        self.assertIn("Verified interception", self.html)
        self.assertIn("Original synthetic evidence", self.html)
        self.assertIn("<details", self.html)

    def test_enrichment_discloses_real_privacy_boundary(self):
        for phrase in (
                "Read scope", "Redaction effects", "Still visible",
                "Destination", "Preview redacted payload",
                "Authorize this run", "Redaction is not anonymization",
                "No request is sent from this static demo"):
            self.assertIn(phrase, self.html)

    def test_install_has_one_canonical_command_and_one_alternative(self):
        self.assertEqual(self.html.count("pipx install hukair-codetalk"), 1)
        self.assertEqual(self.html.count("uv tool install hukair-codetalk"), 1)
        self.assertIn("The installed command remains <code>codetalk</code>",
                      self.html)

    def test_has_no_external_runtime_assets_or_request_apis(self):
        parser = _AssetParser()
        parser.feed(self.html)
        self.assertTrue(parser.assets)
        self.assertFalse(any(v.startswith(("http://", "https://", "//"))
                             for v in parser.assets), parser.assets)
        for request_api in ("fetch(", "XMLHttpRequest", "sendBeacon(",
                            "WebSocket(", "EventSource("):
            self.assertNotIn(request_api, self.html)

    def test_synthetic_data_has_no_private_or_stale_material(self):
        for forbidden in (
                "/Users/", "/home/", "docs/discovery", "ghp_", "github_pat_",
                "sk-", "AIza", "PRIVATE KEY", "2026-", "2025-"):
            self.assertNotIn(forbidden, self.html)
        for path in re.findall(r'(?:src|href)="([^"]+)"', self.html):
            self.assertTrue(path.isascii(), path)
            self.assertIsNone(re.search(r"20\d{2}[-_.]\d{2}", path), path)


class TestReadmeEntryPath(unittest.TestCase):
    def test_synthetic_review_screenshot_exists(self):
        screenshot = ROOT / "docs" / "images" / "codetalk-review-demo.png"
        self.assertTrue(screenshot.is_file())
        self.assertGreater(screenshot.stat().st_size, 20_000)

    def test_readme_keeps_demo_install_usage_and_privacy_in_a_short_entry(self):
        for filename, headings, reference in (
                ("README.md", ("## See it work", "## Install", "## Use your own repository", "## Privacy and limits"), "docs/reference.md"),
                ("README.zh-CN.md", ("## 看看它如何工作", "## 安装", "## 用在自己的仓库", "## 隐私与边界"), "docs/reference.zh-CN.md")):
            with self.subTest(readme=filename):
                readme = (ROOT / filename).read_text(encoding="utf-8")
                positions = [readme.find(heading) for heading in headings]
                self.assertTrue(all(position >= 0 for position in positions))
                self.assertEqual(positions, sorted(positions))
                self.assertLess(len(readme.splitlines()), 160)
                self.assertIn("scripts.demo_reading_room", readme)
                self.assertIn("docs/images/codetalk-reading-room.png", readme)
                self.assertIn("docs/images/codetalk-review-demo.png", readme)
                self.assertIn(reference, readme)
                self.assertTrue((ROOT / reference).is_file())
                self.assertIn("--payload-preview", readme)
                self.assertIn("--allow-remote", readme)
                self.assertIn("--no-llm", readme)
        self.assertIn("脱敏不等于匿名化", (ROOT / "README.zh-CN.md").read_text())


if __name__ == "__main__":
    unittest.main()
