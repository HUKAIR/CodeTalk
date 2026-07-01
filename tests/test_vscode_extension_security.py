import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "vscode-codetalk" / "src" / "extension.ts"


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

    def test_escape_regex_is_not_neutered(self):
        # 行为守门:掏空 escapeMarkdown 的正则(return s 原样)会让 injection 复活,但字符串
        # 存在性检查照过。断言实际转义正则字面量在,neuter 掉正则体即失败。
        self.assertIn(r"replace(/([\\`*_{}\[\]()#+\-.!|>])/g, '\\$1')", self.src)
        # 且必须作用在传入参数上(不是 return 空/原样)
        self.assertRegex(self.src,
                         r"function escapeMarkdown\([^)]*\)\s*(?::[^{]+)?\{\s*return\s*\([^)]*\)\.replace\(")


if __name__ == "__main__":
    unittest.main()
