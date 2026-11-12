"""Selected design applies to real renderers and stays self-contained offline."""
import tempfile
import unittest
from pathlib import Path

from codetalk.review_web import render_review_html
from scripts.demo_ui import build_pages, review_card


class SelectedDesignCase(unittest.TestCase):
    def test_all_function_pages_use_the_selected_design(self):
        with tempfile.TemporaryDirectory() as root:
            build_pages(Path(root))
            for name in ("console-dark", "console-light", "review", "chat",
                         "timeline", "graph", "sessions", "recap-dark",
                         "course", "trust"):
                with self.subTest(page=name):
                    page = (Path(root) / "pages" / (name + ".html")).read_text()
                    self.assertIn('data-ui-design="archive-v3"', page)
                    self.assertIn('class="ui-rail"', page)
                    self.assertNotIn("/* include:", page)
                    self.assertNotRegex(page, r'<script[^>]+src=')
                    self.assertNotRegex(page, r'<link[^>]+rel=[\"\']stylesheet')

    def test_review_keeps_real_card_identity_and_redacted_data(self):
        card = review_card()
        card["id"] = "actual-local-card"
        card["change"]["file"] = "real/module.py"
        page = render_review_html("local-project", [card], {})
        self.assertIn('data-ui-design="archive-v3"', page)
        self.assertIn('"id": "actual-local-card"', page)
        self.assertIn('"file": "real/module.py"', page)
        self.assertNotIn("CT-002", page)
        self.assertNotIn("cache-service", page)
        self.assertIn('fetch(apiPath("/judgment"', page)
        self.assertIn('fetch(apiPath("/feedback/export"', page)

    def test_all_inlined_assets_are_valid_template_content(self):
        with tempfile.TemporaryDirectory() as root:
            entries = build_pages(Path(root))
            for entry in entries:
                page = (Path(root) / "pages" / (entry["id"] + ".html")).read_text()
                self.assertNotRegex(page, r'\$(ui_style|ui_script|data|serve|chat)\b')
                self.assertNotIn("/* include:", page)
