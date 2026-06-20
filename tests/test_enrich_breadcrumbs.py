import unittest
from datetime import datetime, timezone

from vibetrace import enrich
from vibetrace.cache import Cache


class _FakeLLM:
    model = "fake"

    def narrate(self, prompt, *args, **kwargs):
        return {"what": "w", "why": "y", "decisions": ["LLM 决定"],
                "risks": ["LLM 风险"], "open_loops": ["LLM 未闭环"]}


def _commit(body):
    return {"sha": "abc123", "author": "x", "subject": "s", "body": body,
            "date": datetime(2026, 6, 17, tzinfo=timezone.utc),
            "stat": "", "diff_excerpt": "", "files": [], "matches": []}


class TestEnrichBreadcrumbs(unittest.TestCase):
    def test_watch_into_risks_decision_into_decisions_and_redacted(self):
        cache = Cache(":memory:")
        body = ("Vibe-Decision: 用 urllib\n"
                "Vibe-Watch: 临时 token=sk-abcdefghijklmnop1234 待移除")
        enrich.enrich_commits([_commit(body)], _FakeLLM(), cache, "P")
        narr = cache.get_narrative("abc123")
        self.assertIn("用 urllib", narr["decisions"])      # 收割决策
        self.assertIn("LLM 决定", narr["decisions"])        # 原 LLM 决策保留
        watch_risks = [r for r in narr["risks"] if "临时" in r]
        self.assertTrue(watch_risks)                        # cons-1: watch 进 risks
        self.assertNotIn("sk-abcdefghijklmnop1234", watch_risks[0])  # priv-1
        self.assertIn("[REDACTED]", watch_risks[0])
        self.assertEqual(narr["open_loops"], ["LLM 未闭环"])  # watch 不进 open_loops

    def test_no_breadcrumb_keeps_llm_narrative(self):
        cache = Cache(":memory:")
        enrich.enrich_commits([_commit("普通 message")], _FakeLLM(), cache, "P")
        narr = cache.get_narrative("abc123")
        self.assertEqual(narr["decisions"], ["LLM 决定"])
        self.assertEqual(narr["risks"], ["LLM 风险"])


class TestNormalizeDropsFiller(unittest.TestCase):
    def test_filler_dropped_from_risks_and_loops_decisions_kept(self):
        raw = {"what": "w", "why": "y",
               "decisions": ["真决定", "材料不足 x"],     # 事实字段:不滤
               "risks": ["真风险", "材料不足以判断", "  "],
               "open_loops": ["真未闭环", "材料不足", ""]}
        out = enrich._normalize(raw)
        self.assertEqual(out["risks"], ["真风险"])          # 不会封出噪声胶囊
        self.assertEqual(out["open_loops"], ["真未闭环"])
        self.assertEqual(out["decisions"], ["真决定", "材料不足 x"])


if __name__ == "__main__":
    unittest.main()
