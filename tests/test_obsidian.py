"""Track A v1:Obsidian 自动反链——为每个带决策的 commit 产出一张决策笔记
(vault/codetalk/<slug>/<sha7>.md),链回当天日报 [[{date}-{project}]]。Obsidian 自动在
日报侧生成反链。机器自动产出、非用户手写;零 LLM、落盘前脱敏、容错降级。"""
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from codetalk import obsidian


def _commit(sha, day, decisions, subject="s"):
    return {"sha": sha, "date": datetime(2026, 6, day, tzinfo=timezone.utc),
            "subject": subject, "narrative": {"decisions": decisions}}


class TestEmitDecisionNotes(unittest.TestCase):
    def setUp(self):
        self.vault = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.vault, ignore_errors=True)

    def _emit(self, commits, project="Proj", pkey="/abs/Proj"):
        return obsidian.emit_decision_notes(commits, project, self.vault, pkey)

    def _subdir(self, pkey="/abs/Proj"):
        return Path(self.vault) / "codetalk" / obsidian._slug("Proj", pkey)

    def test_emits_note_per_decision_commit_with_backlink(self):
        n = self._emit([_commit("a" * 40, 1, ["用 urllib 不引第三方"]),
                        _commit("b" * 40, 2, [])])      # 无决策 → 不出笔记
        self.assertEqual(n, 1)
        note = self._subdir() / ("a" * 7 + ".md")
        self.assertTrue(note.exists())
        body = note.read_text(encoding="utf-8")
        self.assertIn("用 urllib 不引第三方", body)        # 决策原文
        self.assertIn("[[2026-06-01-Proj]]", body)         # 链回当天日报(Obsidian 自动反链)
        self.assertFalse((self._subdir() / ("b" * 7 + ".md")).exists())

    def test_secret_redacted_in_note(self):
        self._emit([_commit("c" * 40, 3, ["token=sk-ABCDEF0123456789ABCD 写死了"])])
        body = (self._subdir() / ("c" * 7 + ".md")).read_text(encoding="utf-8")
        self.assertNotIn("sk-ABCDEF0123456789ABCD", body)
        self.assertIn("[REDACTED]", body)

    def test_slug_disambiguates_same_basename(self):
        # 同名 basename、不同绝对路径 → 不同子目录(防文件层串库)
        self.assertNotEqual(obsidian._slug("Proj", "/a/Proj"),
                            obsidian._slug("Proj", "/b/Proj"))

    def test_idempotent_rerun(self):
        c = [_commit("d" * 40, 4, ["决策 X"])]
        self._emit(c)
        self._emit(c)                                   # 重跑覆盖,不重复/不崩
        notes = list(self._subdir().glob("*.md"))
        self.assertEqual(len(notes), 1)

    def test_bad_vault_degrades_to_zero(self):
        self.assertEqual(
            obsidian.emit_decision_notes([_commit("e" * 40, 5, ["d"])], "P", "", "/p"),
            0)

    def test_no_decision_commits_writes_nothing(self):
        n = self._emit([_commit("f" * 40, 6, [])])
        self.assertEqual(n, 0)


if __name__ == "__main__":
    unittest.main()
