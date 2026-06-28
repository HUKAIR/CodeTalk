"""Track B v1:债下钻——debt_board 行带真实构成(未回看决策 commit + 待填胶囊),
零-LLM 重派生(debt_board 原只回计数)。降债只认真处理(填胶囊结局);reviewed 是护栏弱信号。"""
import shutil
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path

from vibetrace import debt
from vibetrace.cache import Cache


def _git(a, c):
    subprocess.run(["git", *a], cwd=c, check=True, capture_output=True, text=True)


class TestDebtDrilldown(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)
        _git(["init", "-q"], self.d)
        _git(["config", "user.email", "t@t"], self.d)
        _git(["config", "user.name", "t"], self.d)
        p = Path(self.d) / "a.py"
        p.write_text("1\n"); _git(["add", "."], self.d); _git(["commit", "-q", "-m", "c1"], self.d)
        p.write_text("2\n"); _git(["add", "."], self.d); _git(["commit", "-q", "-m", "c2"], self.d)
        self.pkey = str(Path(self.d).resolve())
        self.cache = Cache(":memory:"); self.addCleanup(self.cache.close)
        self.shas = subprocess.run(["git", "-C", self.d, "log", "--format=%H"],
                                   capture_output=True, text=True).stdout.split()
        # 给较旧的 commit 一条决策叙事(未回看 → 应进 unreviewed)
        self.cache.put_narrative(self.shas[1], self.pkey, "m",
                                 {"decisions": ["用 X 方案"], "risks": ["可能死锁"]})

    def _row(self):
        rows = debt.debt_board(self.pkey, self.cache, date.today())
        return next(r for r in rows if r["file"] == "a.py")

    def test_unreviewed_decisions_in_drilldown(self):
        row = self._row()
        self.assertIn("unreviewed", row)
        decs = [d for u in row["unreviewed"] for d in u["decisions"]]
        self.assertIn("用 X 方案", decs)                 # 未回看决策进下钻
        self.assertEqual(row["unreviewed"][0]["sha"], self.shas[1][:7])

    def test_reviewed_decision_drops(self):
        self.cache.mark_reviewed(self.pkey, self.shas[1][:7])   # 回看 → 降债 + 出下钻
        self.assertEqual(self._row()["unreviewed"], [])

    def test_pending_caps_opened_unfilled(self):
        self.cache.seal_capsule(self.pkey, self.shas[1], 0, "可能死锁", "2026-05-01", "2026-05-22")
        self.cache.open_due_capsules(self.pkey, "2026-06-01")    # 开启、未填
        row = self._row()
        self.assertIn("pending_caps", row)
        self.assertTrue(any(c["risk"] == "可能死锁" for c in row["pending_caps"]))

    def test_filled_capsule_not_pending(self):
        self.cache.seal_capsule(self.pkey, self.shas[1], 0, "可能死锁", "2026-05-01", "2026-05-22")
        self.cache.open_due_capsules(self.pkey, "2026-06-01")
        self.cache.set_capsule_outcome(self.shas[1] + ":0", "已解决", self.pkey)   # capsule_id = 全 sha:idx
        self.assertEqual(self._row()["pending_caps"], [])        # 填了结局即不再待办


if __name__ == "__main__":
    unittest.main()
