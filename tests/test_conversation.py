"""web 接地对话落库 + 反哺接地(C-2 红线):落库脱敏单点收口;对话 text 接进 FTS,
使 topic_search/search_narratives 能召回「你在 X 讨论过」。"""
import unittest

from codetalk import conversation
from codetalk.cache import Cache


class TestConversation(unittest.TestCase):
    def test_save_redacts_text_at_persist(self):
        c = Cache(":memory:")
        self.addCleanup(c.close)
        conversation.save_turn(c, "t1", "c1", "/proj", "2026-06-24T10:00",
                               "assistant",
                               "用 sk-ABCDEF0123456789ABCD 调试日志的决策")
        got = conversation.get_turn(c, "t1")
        self.assertNotIn("sk-ABCDEF0123456789ABCD", got["text"])   # 落库脱敏
        self.assertIn("[REDACTED]", got["text"])
        self.assertEqual(got["role"], "assistant")

    def test_feedback_recall_via_search_narratives(self):
        # C-2 红线:落一条对话 → 主题召回能命中它(反哺闭环不再是断的)
        c = Cache(":memory:")
        self.addCleanup(c.close)
        conversation.save_turn(c, "t2", "c1", "/proj", "2026-06-24T10:01",
                               "assistant", "我们讨论过为什么用流式响应而非缓冲")
        hits = c.search_narratives("流式响应")
        self.assertIn("conv:t2", hits)
        self.assertTrue(conversation.is_conv_key("conv:t2"))
        self.assertEqual(conversation.turn_id_of("conv:t2"), "t2")

    def test_list_conversation_ordered(self):
        c = Cache(":memory:")
        self.addCleanup(c.close)
        conversation.save_turn(c, "a", "cX", "/p", "2026-06-24T10:00", "user", "问题一")
        conversation.save_turn(c, "b", "cX", "/p", "2026-06-24T10:05", "assistant", "答一")
        turns = conversation.list_conversation(c, "cX")
        self.assertEqual([t["turn_id"] for t in turns], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
