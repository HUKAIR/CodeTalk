"""接地命中率自证 measure():确定性接地覆盖统计(零 LLM)。"""
import unittest

from scripts.grounding_hitrate import measure
from codetalk.cache import Cache


class TestGroundingHitrate(unittest.TestCase):
    def test_counts_each_grounding_source(self):
        c = Cache(":memory:")
        c.put_narrative("a" * 40, "/p", "m", {"why": "为了流式响应", "decisions": []})
        c.put_narrative("b" * 40, "/p", "m", {"why": "", "decisions": [],
                        "evidence": [{"source": "x", "prompts": ["q"]}]})
        commits = [
            {"sha": "a" * 40, "body": ""},                      # 叙事 why → grounded
            {"sha": "b" * 40, "body": ""},                      # evidence 锚点 → grounded
            {"sha": "c" * 40, "body": "feat: x\n\nVibe-Decision: 选 X 不选 Y"},  # 仅面包屑 → grounded
            {"sha": "d" * 40, "body": "chore: 普通提交"},        # 无任何接地源 → 不 grounded
        ]
        m = measure(c, commits)
        c.close()
        self.assertEqual(m["total"], 4)
        self.assertEqual(m["narrated"], 2)          # a,b 有叙事
        self.assertEqual(m["breadcrumb"], 1)        # c 有 Vibe-Decision
        self.assertEqual(m["evidence"], 1)          # b 有 evidence
        self.assertEqual(m["grounded"], 3)          # a,b,c 可接地;d 不可
        self.assertEqual(m["coverage_pct"], 75.0)

    def test_empty_repo(self):
        self.assertEqual(measure(Cache(":memory:"), [])["coverage_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
