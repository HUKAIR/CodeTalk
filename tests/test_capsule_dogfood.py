"""#1 dogfood 开关:VIBETRACE_CAPSULE_DAYS 覆盖 21 天到期窗口,显式设值即 dogfood
(绕过 seal-guard,当天就能密封并开胶囊取首个回面数据点)。"""
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from vibetrace import digest
from vibetrace.cache import Cache
from vibetrace.report import _OUTCOMES, read_capsule_answers


class TestCapsuleDays(unittest.TestCase):
    def test_default_21_not_dogfood(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(digest._capsule_days(), (21, False))

    def test_env_override_marks_dogfood(self):
        with mock.patch.dict(os.environ, {"VIBETRACE_CAPSULE_DAYS": "0"}):
            self.assertEqual(digest._capsule_days(), (0, True))     # 0 天 + dogfood

    def test_small_window_dogfood(self):
        with mock.patch.dict(os.environ, {"VIBETRACE_CAPSULE_DAYS": "1"}):
            self.assertEqual(digest._capsule_days(), (1, True))

    def test_bad_value_falls_back_to_default(self):
        with mock.patch.dict(os.environ, {"VIBETRACE_CAPSULE_DAYS": "xyz"}):
            self.assertEqual(digest._capsule_days(), (21, False))   # 坏值不崩,回默认

    def test_negative_clamped_to_zero(self):
        with mock.patch.dict(os.environ, {"VIBETRACE_CAPSULE_DAYS": "-5"}):
            self.assertEqual(digest._capsule_days(), (0, True))


class TestSealOnlyVibeWatch(unittest.TestCase):
    """胶囊只 seal 逐字 Vibe-Watch 面包屑,LLM 预测 risks 不进胶囊。
    诚实底:LLM 预测对账价值低、噪声大,塞进胶囊会污染北极星处理率。"""

    def setUp(self):
        self.cache = Cache(":memory:")
        self.pkey = "/tmp/fake-proj"
        self.commit = {
            "sha": "abc1234567890",
            "date": datetime(2026, 6, 30, tzinfo=timezone.utc),
            "body": "feat: x\n\nVibe-Watch: 用户手写的待验证预测",
            "narrative": {
                "risks": ["用户手写的待验证预测",
                          "LLM 推断的另一条 risk(不该进胶囊)"],
            },
        }

    def tearDown(self):
        self.cache.close()

    def test_only_verbatim_vibe_watch_sealed(self):
        digest._seal_commit_capsules(self.cache, self.pkey,
                                     self.commit, "2026-06-30", "2026-07-21")
        caps = self.cache.all_capsules(self.pkey)
        risks = [c["risk"] for c in caps]
        self.assertEqual(risks, ["用户手写的待验证预测"])

    def test_no_vibe_watch_means_no_capsules(self):
        commit = {**self.commit, "body": "feat: x\n(no breadcrumb)"}
        digest._seal_commit_capsules(self.cache, self.pkey,
                                     commit, "2026-06-30", "2026-07-21")
        self.assertEqual(self.cache.all_capsules(self.pkey), [])

    def test_secret_shaped_vibe_watch_still_seals(self):
        """含 secret 形的手写 Vibe-Watch:narrative.risks 经 enrich 脱敏成 [REDACTED],
        body 里的 watch 是原文。两侧须同口径脱敏后比,否则 exact-match 漏命中、永不封存。"""
        from vibetrace.config import redact_secrets
        watch_raw = 'rotate token="leakTok9988XY" before deploy'
        commit = {
            "sha": "def4567890abc",
            "date": datetime(2026, 6, 30, tzinfo=timezone.utc),
            "body": f"feat: x\n\nVibe-Watch: {watch_raw}",
            "narrative": {"risks": [redact_secrets(watch_raw)]},  # 模拟 enrich 脱敏后的 risk
        }
        digest._seal_commit_capsules(self.cache, self.pkey,
                                     commit, "2026-06-30", "2026-07-21")
        caps = self.cache.all_capsules(self.pkey)
        self.assertEqual(len(caps), 1)                  # 仍封存(脱敏归一后命中)
        self.assertNotIn("leakTok9988XY", caps[0]["risk"])  # 存的是脱敏版


class TestForgotOutcomeReadback(unittest.TestCase):
    """「忘记了」是第 4 个 outcome,回读必须能正确写回 cache(回填环不能漏选项)。"""

    def test_forgot_outcome_in_outcomes(self):
        self.assertIn("忘记了", _OUTCOMES)

    def test_readback_writes_forgot_outcome_to_cache(self):
        with tempfile.TemporaryDirectory() as vault:
            with tempfile.TemporaryDirectory() as proj:
                cache = Cache(":memory:")
                cache.seal_capsule(proj, "sha1", 0, "测试 risk",
                                   "2026-06-01", "2026-06-22")
                cache.open_due_capsules(proj, "2026-06-22")
                caps = cache.all_capsules(proj)
                cap_id = caps[0]["capsule_id"]
                # 模拟用户在 Obsidian 勾「忘记了」
                md = Path(vault) / "2026-06-30-{}.md".format(Path(proj).name)
                md.write_text(
                    f"<!-- vt-capsule:{cap_id} -->\n"
                    "- 你担心:「测试 risk」\n"
                    "\t- [ ] 想多了\n"
                    "\t- [ ] 已解决\n"
                    "\t- [ ] 还在担心\n"
                    "\t- [x] 忘记了\n",
                    encoding="utf-8")
                read_capsule_answers(vault, proj, cache)
                outcome = cache.conn.execute(
                    "SELECT outcome FROM capsules WHERE capsule_id=?",
                    (cap_id,)).fetchone()[0]
                self.assertEqual(outcome, "忘记了")
                cache.close()


if __name__ == "__main__":
    unittest.main()
