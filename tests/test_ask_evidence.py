"""ask:在综合答案后追加「原话佐证(可自行核验)」块 + 软关联置信度警示。
evidence 由 _retrieve 从命中 SHA 的 narrative 汇总(此处直接以 4 元组喂入,
聚焦 answer_question 的拼接/警示/降级路径);无 evidence 不输出块。"""
import unittest
from unittest import mock

from vibetrace import ask
from vibetrace.cache import Cache


class _FakeLLM:
    model = "fake"

    def __init__(self):
        self.calls = 0

    def narrate(self, prompt, *a, **k):
        self.calls += 1
        return {"answer": "因为是推理模型", "cited_shas": ["sha1aaa"],
                "unsure": ""}


def _ev(sid, source, confidence, prompts, excerpts, ts="2026-06-17T10:00:00+00:00"):
    return {"session_id": sid, "source": source, "ts": ts,
            "confidence": confidence, "prompts": prompts, "excerpts": excerpts}


def _patch_retrieve(evidence, ctx="[sha1aaa] 决策:用 urllib",
                    state="sha1aaaabbbb"):
    return mock.patch.object(
        ask, "_retrieve",
        lambda *a, **k: (ctx, ["sha1aaaabbbb"], state, evidence, []))


class TestAskEvidenceBlock(unittest.TestCase):
    def test_high_evidence_appended_after_answer(self):
        cache = Cache(":memory:")
        ev = [_ev("highsess1", "claude", "high",
                  ["为什么 3000 不够", "上下文太长"], ["扩到 8000"])]
        with _patch_retrieve(ev):
            text, err = ask.answer_question(cache, _FakeLLM(), ".", "P",
                                            "f.py:1-2", "为什么")
        self.assertIsNone(err)
        self.assertIn("推理模型", text)              # LLM 综合答案在
        self.assertIn("原话佐证", text)              # 佐证块标题
        self.assertIn("为什么 3000 不够", text)      # 原话片段
        self.assertIn("扩到 8000", text)             # AI 关键陈述片段
        self.assertIn("highses", text)               # session 短 id
        self.assertIn("claude", text)                # 来源
        self.assertNotIn("置信较低", text)           # 有 high → 无警示

    def test_only_low_evidence_adds_confidence_warning(self):
        cache = Cache(":memory:")
        ev = [_ev("lowsess99", "cursor", "low", ["顺手问一句"], [])]
        with _patch_retrieve(ev):
            text, err = ask.answer_question(cache, _FakeLLM(), ".", "P",
                                            "f.py:1-2", "为什么")
        self.assertIsNone(err)
        self.assertIn("原话佐证", text)
        self.assertIn("顺手问一句", text)
        self.assertIn("置信较低", text)              # 仅 low → 警示

    def test_no_evidence_no_block(self):
        cache = Cache(":memory:")
        with _patch_retrieve([]):
            text, err = ask.answer_question(cache, _FakeLLM(), ".", "P",
                                            "f.py:1-2", "为什么")
        self.assertIsNone(err)
        self.assertNotIn("原话佐证", text)           # 无 evidence 不输出块

    def test_cache_hit_path_also_shows_evidence(self):
        cache = Cache(":memory:")
        # 预置 ask: 缓存命中(payload),evidence 仍由 _retrieve 提供
        ev = [_ev("highsess1", "claude", "high", ["原话A"], [])]
        with _patch_retrieve(ev):
            llm = _FakeLLM()
            ask.answer_question(cache, llm, ".", "P", "f.py:1-2", "为什么")
            text, err = ask.answer_question(cache, llm, ".", "P",
                                            "f.py:1-2", "为什么")
        self.assertIsNone(err)
        self.assertEqual(llm.calls, 1)               # 第二次命中缓存
        self.assertIn("原话佐证", text)              # 缓存路径也附原话锚点
        self.assertIn("原话A", text)

    def test_evidence_shown_on_degraded_no_llm(self):
        cache = Cache(":memory:")
        ev = [_ev("highsess1", "claude", "high", ["原话A"], ["陈述B"])]
        with _patch_retrieve(ev):
            text, err = ask.answer_question(cache, None, ".", "P",
                                            "f.py:1-2", "Q")
        self.assertIsNone(err)
        self.assertIn("原始决策史", text)            # 降级路径
        self.assertIn("原话佐证", text)              # 降级也展示原话锚点
        self.assertIn("原话A", text)


class TestFormatEvidence(unittest.TestCase):
    def test_empty_returns_blank(self):
        self.assertEqual(ask.format_evidence([]), "")

    def test_mixed_high_low_no_warning(self):
        out = ask.format_evidence([
            _ev("s1", "claude", "high", ["a"], []),
            _ev("s2", "cursor", "low", ["b"], [])])
        self.assertNotIn("置信较低", out)            # 有 high 即不警示

    def test_missing_keys_tolerated(self):
        # 旧/残缺 evidence 条目缺键不崩
        out = ask.format_evidence([{"confidence": "low"}])
        self.assertIn("原话佐证", out)
        self.assertIn("置信较低", out)


if __name__ == "__main__":
    unittest.main()
