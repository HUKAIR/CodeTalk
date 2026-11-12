import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path

from codetalk import cli
from codetalk.hook import install_agent_seed


class TestInstallAgentSeed(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)

    def test_seeds_all_agent_targets(self):
        paths, err = install_agent_seed(self.d)
        self.assertIsNone(err)
        expected = {"CLAUDE.md", "AGENTS.md", ".cursorrules",
                    "codetalk.mdc", "copilot-instructions.md"}
        self.assertEqual({p.name for p in paths}, expected)
        for p in paths:
            text = p.read_text(encoding="utf-8")
            self.assertIn("codetalk-agent-seed", text)
            self.assertIn("Vibe-Decision:", text)
            self.assertIn("Vibe-Watch:", text)

    def test_appends_preserving_existing(self):
        claude = Path(self.d) / "CLAUDE.md"
        claude.write_text("# 既有项目说明\n", encoding="utf-8")
        _, err = install_agent_seed(self.d)
        self.assertIsNone(err)
        text = claude.read_text(encoding="utf-8")
        self.assertIn("# 既有项目说明", text)            # 原内容保留
        self.assertIn("codetalk-agent-seed", text)      # 追加了种子

    def test_idempotent_no_duplicate(self):
        install_agent_seed(self.d)
        paths, err = install_agent_seed(self.d)            # 第二次
        self.assertIsNone(err)
        for p in paths:
            text = p.read_text(encoding="utf-8")
            self.assertEqual(text.count("codetalk-agent-seed"), 1)


class TestAgentSeedCLI(unittest.TestCase):
    def test_cli_install_agent_seed(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        with contextlib.redirect_stdout(io.StringIO()):
            rc = cli.main(["install-agent-seed", "--project", d])
        self.assertEqual(rc, 0)
        text = (Path(d) / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("codetalk-agent-seed", text)
        self.assertTrue((Path(d) / ".cursorrules").exists())
        self.assertTrue((Path(d) / ".github" / "copilot-instructions.md").exists())


if __name__ == "__main__":
    unittest.main()
