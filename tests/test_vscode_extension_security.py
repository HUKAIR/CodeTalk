import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "vscode-vibetrace" / "src" / "extension.ts"


class TestVscodeHoverSecurity(unittest.TestCase):
    def setUp(self):
        self.src = EXT.read_text(encoding="utf-8")

    def test_markdown_trust_is_command_scoped(self):
        self.assertNotIn("md.isTrusted = true", self.src)
        self.assertIn("enabledCommands: ['workbench.action.terminal.sendSequence']", self.src)

    def test_untrusted_hover_fields_are_markdown_escaped(self):
        for expr in (
            "escapeMarkdown(seg.subject)",
            "escapeMarkdown(seg.why)",
            "escapeMarkdown(d)",
            "escapeMarkdown(r)",
            "escapeMarkdown(t.path)",
            "escapeMarkdown(names)",
            "escapeMarkdown(p.title)",
            "escapeMarkdown(p.snippet)",
        ):
            self.assertIn(expr, self.src)
        self.assertIn("function escapeMarkdown", self.src)


if __name__ == "__main__":
    unittest.main()
