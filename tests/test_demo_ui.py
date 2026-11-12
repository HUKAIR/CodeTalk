"""The synthetic gallery renders real templates without project records."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.demo_ui import build_pages


class GalleryCase(unittest.TestCase):
    def test_all_previews_render_without_reading_git_or_sessions(self):
        with tempfile.TemporaryDirectory() as root, \
             patch("subprocess.run", side_effect=AssertionError("unexpected git")), \
             patch("codetalk.recap.parse_session",
                   side_effect=AssertionError("unexpected user session")):
            entries = build_pages(Path(root))
            ids = {entry["id"] for entry in entries}
            self.assertTrue({"console-dark", "console-light", "review", "chat",
                             "review-empty", "review-long", "sessions",
                             "timeline", "graph", "course", "trust"} <= ids)
            for entry in entries:
                page = (Path(root) / "pages" / (entry["id"] + ".html")).read_text()
                self.assertIn("<!doctype html>", page.lower())
                self.assertNotIn("$tree_data", page)
                self.assertNotIn("$index_href", page)
            detail = (Path(root) / "pages/recap-dark.html").read_text()
            self.assertIn('id="back-index" href="sessions.html"', detail)
            gallery = (Path(root) / "index.html").read_text()
            self.assertNotIn("/* ITEMS */[]", gallery)
            self.assertIn('sandbox="allow-scripts allow-modals"', gallery)
