"""ADR 导出:真实决策史 → MADR/Nygard markdown,逐字引真实 commit、出口脱敏。零 LLM。"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vibetrace import adr_export
from vibetrace.adr_export import to_adr
from vibetrace.cache import Cache


def _git(a, c):
    subprocess.run(["git", *a], cwd=c, check=True, capture_output=True, text=True)


_SEG = [{"sha": "abc1234" + "0" * 33, "date": "2026-06-01T08:00", "subject": "用乐观锁",
         "why": "为了避免写超时", "decisions": ["放弃悲观锁,改版本号 CAS"],
         "risks": ["高并发下重试风暴待验证"], "evidence": [], "test_refs": [], "pr_refs": []}]


class TestToAdr(unittest.TestCase):
    def test_madr_structure_and_verbatim_source(self):
        out = to_adr("f.py:1-5", _SEG, "madr")
        self.assertIn("## Context and Problem Statement", out)
        self.assertIn("为了避免写超时", out)                 # why → Context(逐字)
        self.assertIn("放弃悲观锁,改版本号 CAS", out)        # decision → Decision(逐字)
        self.assertIn("高并发下重试风暴待验证", out)          # risk → Consequences
        self.assertIn("[abc1234]", out)                      # 来源:真实 commit SHA
        self.assertIn("f.py:1-5", out)                       # 目标

    def test_nygard_format(self):
        out = to_adr("f.py", _SEG, "nygard")
        self.assertIn("## Status", out)
        self.assertIn("accepted", out)
        self.assertIn("## Decision", out)
        self.assertNotIn("Context and Problem Statement", out)  # 这是 MADR 段名,nygard 不应有

    def test_no_segments_falls_back(self):
        out = to_adr("x.py", [], "madr")
        self.assertIn("无叙事", out)                          # 空也出友好 ADR 骨架,不崩

    def test_redaction(self):
        seg = [{"sha": "e" * 40, "date": "d", "subject": "s",
                "why": "key sk-abcdefghijklmnop1234 别泄漏", "decisions": [],
                "risks": []}]
        out = to_adr("f", seg, "madr")
        self.assertNotIn("sk-abcdefghijklmnop1234", out)
        self.assertIn("[REDACTED]", out)


class TestExportOnRepo(unittest.TestCase):
    def test_export_grounds_to_real_commit(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        _git(["init", "-q"], d)
        _git(["config", "user.email", "t@t"], d)
        _git(["config", "user.name", "t"], d)
        (Path(d) / "a.py").write_text("x = 1\n"); _git(["add", "."], d)
        _git(["commit", "-q", "-m", "feat: 初版\n\nVibe-Decision: 选三行布局便于演示"], d)
        db = str(Path(d) / "cache.db")
        with mock.patch("vibetrace.config.CACHE_DB_PATH", db):
            out, err = adr_export.export(d, "a.py", fmt="madr")
        self.assertIsNone(err)
        self.assertIn("选三行布局便于演示", out)              # 逐字引真实 Vibe-Decision
        self.assertIn("## Decision Outcome", out)


if __name__ == "__main__":
    unittest.main()
