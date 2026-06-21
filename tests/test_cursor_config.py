# tests/test_cursor_config.py
import unittest
from vibetrace.config import load_config, DEFAULTS

class TestSourcesDefault(unittest.TestCase):
    def test_default_sources_is_claude_only(self):
        self.assertEqual(DEFAULTS["sources"], ["claude"])
        self.assertEqual(load_config()["sources"], ["claude"])

if __name__ == "__main__":
    unittest.main()
