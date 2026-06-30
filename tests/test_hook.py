import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from codetalk.hook import install_hook


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


class TestInstallHook(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        _git(["init", "-q"], self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_installs_executable_hook(self):
        hook, err = install_hook(self.dir)
        self.assertIsNone(err)
        self.assertTrue(hook.exists())
        self.assertTrue(hook.stat().st_mode & 0o111)        # 可执行
        self.assertIn("Vibe-Decision:", hook.read_text())

    def test_no_clobber_without_force(self):
        h = Path(self.dir) / ".git" / "hooks" / "prepare-commit-msg"
        h.parent.mkdir(parents=True, exist_ok=True)
        h.write_text("# mine\n")
        _, err = install_hook(self.dir)
        self.assertTrue(err)
        self.assertEqual(h.read_text(), "# mine\n")          # 未覆盖
        h2, err2 = install_hook(self.dir, force=True)
        self.assertIsNone(err2)
        self.assertIn("Vibe-Decision:", h2.read_text())

    def test_hook_appends_hint_in_editor_mode_only(self):
        hook, _ = install_hook(self.dir)
        msg = Path(self.dir) / "MSG"
        msg.write_text("feat: x\n")
        subprocess.run(["sh", str(hook), str(msg), ""], check=True)   # src 空=编辑器
        self.assertIn("Vibe-Decision:", msg.read_text())
        msg2 = Path(self.dir) / "MSG2"
        msg2.write_text("feat: y\n")
        subprocess.run(["sh", str(hook), str(msg2), "message"], check=True)  # -m
        self.assertNotIn("Vibe-Decision:", msg2.read_text())

    def test_not_a_repo_errors(self):
        d = tempfile.mkdtemp()
        try:
            _, err = install_hook(d)
            self.assertTrue(err)
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
