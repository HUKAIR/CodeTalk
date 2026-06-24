"""接地对话护城河核心(retrieval + chat,Phase 1a,LLM 作注入依赖):
C-3 同源(喂模型材料含真实原话锚点、citations 同源)· C-1 出网前整体脱敏 ·
no_llm/材料空 不调 LLM 降级 · 落库反哺。全 stdlib，无需 key/网络。"""
import unittest

from vibetrace import chat, retrieval
from vibetrace.cache import Cache


def _seed(c):
    c.put_narrative("a" * 40, "/proj", "m", {
        "why": "为了流式响应不断连,把重试从装饰器改成显式循环",
        "decisions": ["用显式循环不引依赖"],
        "evidence": [{"source": "claude", "session_id": "s1", "ts": "t",
                      "confidence": "high",
                      "prompts": ["把重试改成显式循环别再用装饰器"], "excerpts": []}],
        "test_refs": [], "pr_refs": []})


class _FakeLLM:
    def __init__(self):
        self.calls = []

    def chat(self, messages):
        self.calls.append(messages)
        return "综合答:因为要支持流式响应"


class TestRetrieval(unittest.TestCase):
    def test_material_has_real_anchors_and_citations_same_source(self):
        c = Cache(":memory:"); self.addCleanup(c.close); _seed(c)
        out = retrieval.assemble(c, "/proj", "流式响应")
        self.assertIn("为了流式响应不断连", out["material"])          # 叙事 why 进材料
        self.assertIn("把重试改成显式循环别再用装饰器", out["material"])  # C-3:evidence 原话喂 LLM
        self.assertEqual(len(out["citations"]), len(out["hits"]))    # 同源:citations ≡ hits
        self.assertTrue(any(ci["sha"].startswith("aaaaaaa") for ci in out["citations"]))

    def test_citation_carries_evidence_for_verification(self):
        # 可点开核验:每条 citation 带真实记录(意图/原话),点开即看,无需再请求后端
        c = Cache(":memory:"); self.addCleanup(c.close); _seed(c)
        cit = retrieval.assemble(c, "/proj", "流式响应")["citations"][0]
        self.assertIn("为了流式响应不断连", cit["evidence"])           # 真实意图
        self.assertIn("把重试改成显式循环别再用装饰器", cit["evidence"])  # 真实会话原话锚点


class TestChat(unittest.TestCase):
    def test_grounded_answer_llm_actually_reads_material(self):
        c = Cache(":memory:"); self.addCleanup(c.close); _seed(c)
        llm = _FakeLLM()
        out = chat.answer(c, llm, "/proj", "流式响应", now="2026-06-24T10:00")
        self.assertFalse(out["degraded"])
        self.assertEqual(out["answer"], "综合答:因为要支持流式响应")
        self.assertIn("为了流式响应不断连", llm.calls[0][-1]["content"])  # LLM 真读到材料
        self.assertGreaterEqual(len(out["citations"]), 1)

    def test_final_payload_redacted_before_llm(self):
        # C-1:出网前整体脱敏(key="value" 形式也收口)
        msg = chat.build_user_message("问题", "", '决策:token="hunter2hunter2X" 见 commit')
        self.assertNotIn("hunter2hunter2X", msg)
        self.assertIn("[REDACTED]", msg)

    def test_empty_material_never_calls_llm(self):
        c = Cache(":memory:"); self.addCleanup(c.close)   # 不 seed → 材料空
        llm = _FakeLLM()
        out = chat.answer(c, llm, "/proj", "查无此生僻主题zzz", now="t")
        self.assertEqual(llm.calls, [])                   # 护城河红线:材料空不让 LLM 凭空答
        self.assertTrue(out["degraded"])

    def test_no_llm_degrades_zero_egress(self):
        c = Cache(":memory:"); self.addCleanup(c.close); _seed(c)
        out = chat.answer(c, None, "/proj", "流式响应", now="t")  # llm=None = no_llm/无 key
        self.assertTrue(out["degraded"])
        self.assertIn("流式响应", out["answer"])           # 降级为零-LLM 材料罗列

    def test_turn_persisted_and_recallable(self):
        c = Cache(":memory:"); self.addCleanup(c.close); _seed(c)
        chat.answer(c, _FakeLLM(), "/proj", "流式响应", conv_id="cv", now="t", turn_seq=0)
        from vibetrace import conversation
        turns = conversation.list_conversation(c, "cv")
        self.assertEqual([t["role"] for t in turns], ["user", "assistant"])


class _FakeStreamLLM:
    def __init__(self, chunks):
        self.chunks = chunks
        self.stream_calls = 0

    def chat_stream(self, messages):
        self.stream_calls += 1
        for c in self.chunks:
            yield c


class TestChatStream(unittest.TestCase):
    def test_streams_deltas_and_saves_full_answer(self):
        c = Cache(":memory:"); self.addCleanup(c.close); _seed(c)
        llm = _FakeStreamLLM(["因为要支持", "流式响应"])
        events = list(chat.answer_stream(c, llm, "/proj", "流式响应",
                                         conv_id="s", now="t"))
        tokens = [e["text"] for e in events if e["type"] == "token"]
        self.assertEqual("".join(tokens), "因为要支持流式响应")
        self.assertEqual(events[-1]["type"], "done")
        self.assertFalse(events[-1]["degraded"])
        self.assertGreaterEqual(len(events[-1]["citations"]), 1)
        from vibetrace import conversation
        turns = conversation.list_conversation(c, "s")
        self.assertEqual(turns[-1]["text"], "因为要支持流式响应")   # 落库=完整答案

    def test_no_llm_stream_single_block_degraded(self):
        c = Cache(":memory:"); self.addCleanup(c.close); _seed(c)
        events = list(chat.answer_stream(c, None, "/proj", "流式响应", now="t"))
        self.assertEqual(events[-1]["type"], "done")
        self.assertTrue(events[-1]["degraded"])
        self.assertTrue(any(e["type"] == "token" for e in events))

    def test_empty_material_stream_never_calls_llm(self):
        c = Cache(":memory:"); self.addCleanup(c.close)            # 不 seed → 材料空
        llm = _FakeStreamLLM(["不该被调用"])
        events = list(chat.answer_stream(c, llm, "/proj", "查无生僻zzz", now="t"))
        self.assertEqual(llm.stream_calls, 0)                     # 护城河:材料空不调 LLM
        self.assertTrue(events[-1]["degraded"])


if __name__ == "__main__":
    unittest.main()
