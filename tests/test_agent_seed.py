import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path

from vibetrace import cli
from vibetrace.hook import install_agent_seed


class TestInstallAgentSeed(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)

    def test_seeds_both_claude_and_agents_md(self):
        paths, err = install_agent_seed(self.d)
        self.assertIsNone(err)
        self.assertEqual({p.name for p in paths}, {"CLAUDE.md", "AGENTS.md"})
        for name in ("CLAUDE.md", "AGENTS.md"):
            text = (Path(self.d) / name).read_text(encoding="utf-8")
            self.assertIn("vibetrace-agent-seed", text)
            self.assertIn("Vibe-Decision:", text)
            self.assertIn("Vibe-Watch:", text)

    def test_appends_preserving_existing(self):
        claude = Path(self.d) / "CLAUDE.md"
        claude.write_text("# 既有项目说明\n", encoding="utf-8")
        _, err = install_agent_seed(self.d)
        self.assertIsNone(err)
        text = claude.read_text(encoding="utf-8")
        self.assertIn("# 既有项目说明", text)            # 原内容保留
        self.assertIn("vibetrace-agent-seed", text)      # 追加了种子

    def test_idempotent_no_duplicate(self):
        install_agent_seed(self.d)
        _, err = install_agent_seed(self.d)               # 第二次
        self.assertIsNone(err)
        for name in ("CLAUDE.md", "AGENTS.md"):
            text = (Path(self.d) / name).read_text(encoding="utf-8")
            self.assertEqual(text.count("vibetrace-agent-seed"), 1)


class TestAgentSeedCLI(unittest.TestCase):
    def test_cli_install_agent_seed(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        with contextlib.redirect_stdout(io.StringIO()):
            rc = cli.main(["install-agent-seed", "--project", d])
        self.assertEqual(rc, 0)
        for name in ("CLAUDE.md", "AGENTS.md"):
            text = (Path(d) / name).read_text(encoding="utf-8")
            self.assertIn("vibetrace-agent-seed", text)


if __name__ == "__main__":
    unittest.main()
