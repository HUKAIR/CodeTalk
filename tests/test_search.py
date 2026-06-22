"""topic_search 测试:主题级零-LLM 确定性接地召回。

命中 → 返回含对应 why/决策/原话锚点;无命中 → 友好提示。绝不调 LLM。
"""
import unittest

from vibetrace.cache import Cache
from vibetrace.search import topic_search


class TestTopicSearch(unittest.TestCase):
    def test_hit_returns_why_and_decisions(self):
        c = Cache(":memory:")
        c.put_narrative(
            "abc1234deadbeef", "P", "m",
            {"why": "用乐观锁避免超时",
             "decisions": ["放弃悲观锁,改用版本号 CAS"]})
        out = topic_search(c, "/tmp/proj", "乐观锁")
        self.assertIn("abc1234", out)            # sha 短码
        self.assertIn("用乐观锁避免超时", out)     # why
        self.assertIn("版本号 CAS", out)          # 决策

    def test_hit_renders_evidence_anchor(self):
        c = Cache(":memory:")
        c.put_narrative(
            "sha_ev0001", "P", "m",
            {"why": "用幂等去重保证一致",
             "evidence": [{"source": "claude", "session_id": "s12345678",
                           "ts": "2026-06-01", "confidence": "high",
                           "prompts": ["怎么防止重复扣款"]}]})
        out = topic_search(c, "/tmp/proj", "幂等去重")
        self.assertIn("怎么防止重复扣款", out)     # 原话锚点

    def test_no_hit_friendly_message(self):
        c = Cache(":memory:")
        c.put_narrative("sha_x0001", "P", "m", {"why": "无关内容"})
        out = topic_search(c, "/tmp/proj", "完全不沾边的关键词xyz")
        self.assertNotIn("sha_x0001", out)
        self.assertTrue(out.strip())             # 有友好提示文本

    def test_empty_query_friendly_message(self):
        c = Cache(":memory:")
        c.put_narrative("sha_y0001", "P", "m", {"why": "用乐观锁"})
        out = topic_search(c, "/tmp/proj", "")    # 无有效 term
        self.assertTrue(out.strip())

    def test_does_not_call_llm(self):
        # search 模块不应 import 或调用任何 LLM——以无网络/无 key 也能跑为证
        import vibetrace.search as s
        src = open(s.__file__, encoding="utf-8").read()
        self.assertNotIn("LLMClient", src)
        self.assertNotIn("llm.narrate", src)

    def test_redaction_inherited_no_plaintext_secret(self):
        c = Cache(":memory:")
        c.put_narrative(
            "sha_sec001", "P", "m",
            {"why": "鉴权用 sk-abcdefghijklmnop1234 这个 key 做幂等去重"})
        out = topic_search(c, "/tmp/proj", "幂等去重")
        self.assertNotIn("sk-abcdefghijklmnop1234", out)


if __name__ == "__main__":
    unittest.main()
