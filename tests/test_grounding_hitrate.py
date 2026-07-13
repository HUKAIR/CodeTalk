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
            {"sha": "c" * 40, "body": "feat: x\n\nVibe-Decision: 选 X 不选 Y"},  # 仅决策记录 → grounded
            {"sha": "d" * 40, "body": "chore: 普通提交"},        # 无任何接地源 → 不 grounded
            {"sha": "e" * 40, "body": "fix: x\n\nVibe-Watch: 并发仍待验证"},
            {"sha": "f" * 40, "body": "refactor: x\n\nVibe-Rejected: 不引入队列"},
        ]
        m = measure(c, commits)
        c.close()
        self.assertEqual(m["total"], 6)
        self.assertEqual(m["narrated"], 2)          # a,b 有叙事
        self.assertEqual(m["breadcrumb"], 3)        # c/e/f 各有一种 Vibe-* 决策记录
        self.assertEqual(m["evidence"], 1)          # b 有 evidence
        self.assertEqual(m["grounded"], 5)          # a,b,c,e,f 可接地;d 不可
        self.assertEqual(m["coverage_pct"], 83.3)
        # 真实接地率:只算逐字/决策记录,排除 a 的纯 LLM why → b,c,e,f
        self.assertEqual(m["real_grounded"], 4)
        self.assertEqual(m["real_pct"], 66.7)
        self.assertEqual(m["depth_pct"], 16.7)      # 输入杠杆 depth:仅 b 有逐字锚点 = 1/6

    def test_llm_narrative_alone_not_real_grounded(self):
        c = Cache(":memory:")
        c.put_narrative("a" * 40, "/p", "m",
                        {"why": "LLM 猜的 why", "decisions": ["LLM 决策"]})
        m = measure(c, [{"sha": "a" * 40, "body": "chore: x"}])
        c.close()
        self.assertEqual(m["grounded"], 1)          # 覆盖上限含它
        self.assertEqual(m["real_grounded"], 0)     # 但真实接地率排除纯 LLM 叙事

    def test_empty_repo(self):
        m = measure(Cache(":memory:"), [])
        self.assertEqual(m["coverage_pct"], 0.0)
        self.assertEqual(m["real_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
