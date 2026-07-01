import unittest
from unittest import mock

from codetalk import ask
from codetalk.cache import Cache


class _FakeLLM:
    model = "fake"

    def __init__(self):
        self.calls = 0

    def narrate(self, prompt, *a, **k):
        self.calls += 1
        return {"answer": "因为是推理模型,3000 不够",
                "cited_shas": ["sha1aaa"], "unsure": ""}


def _patch_retrieve(ctx="[sha1aaa] 决策:用 urllib", state="sha1aaaabbbb"):
    return mock.patch.object(ask, "_retrieve",
                             lambda *a, **k: (ctx, ["sha1aaaabbbb"], state, [], [], []))


class TestAnswerQuestion(unittest.TestCase):
    def test_answers_caches_and_second_call_hits_cache(self):
        cache, llm = Cache(":memory:"), _FakeLLM()
        with _patch_retrieve():
            t1, e1 = ask.answer_question(cache, llm, ".", "P", "f.py:1-2", "为什么")
            t2, e2 = ask.answer_question(cache, llm, ".", "P", "f.py:1-2", "为什么")
        self.assertIsNone(e1)
        self.assertIsNone(e2)
        self.assertIn("推理模型", t1)
        self.assertIn("sha1aaa", t1)        # cited_shas 露出
        self.assertEqual(llm.calls, 1)      # 第二次命中缓存,不再调 LLM

    def test_no_llm_degrades_to_raw_history(self):
        cache = Cache(":memory:")
        with _patch_retrieve():
            text, err = ask.answer_question(cache, None, ".", "P", "f.py:1-2", "Q")
        self.assertIsNone(err)
        self.assertIn("用 urllib", text)     # 原始决策史
        self.assertIn("原始决策史", text)

    def test_no_history_returns_error(self):
        cache = Cache(":memory:")
        with mock.patch.object(ask, "_retrieve", lambda *a, **k: ("", [], "", [], [], [])):
            text, err = ask.answer_question(cache, _FakeLLM(), ".", "P", "x.py", "Q")
        self.assertIsNone(text)
        self.assertTrue(err)

    def test_answer_redacted_before_cache(self):
        cache = Cache(":memory:")

        class _LeakLLM:
            model = "m"

            def narrate(self, *a, **k):
                return {"answer": "key 是 sk-abcdefghijklmnop1234",
                        "cited_shas": []}

        with _patch_retrieve():
            text, err = ask.answer_question(cache, _LeakLLM(), ".", "P",
                                            "f.py:1-2", "Q")
        self.assertNotIn("sk-abcdefghijklmnop1234", text)
        self.assertIn("[REDACTED]", text)

    def test_hallucinated_cited_sha_dropped(self):
        """核心承诺:LLM 自报但不在检索证据里的 SHA 不外露、不落缓存。"""
        cache = Cache(":memory:")

        class _HallucLLM:
            model = "m"

            def narrate(self, *a, **k):
                return {"answer": "答案",
                        "cited_shas": ["sha1aaa", "deadbeef", "9999999"], "unsure": ""}

        with _patch_retrieve():   # 检索真 SHA 只有 sha1aaaabbbb
            text, err = ask.answer_question(cache, _HallucLLM(), ".", "P",
                                            "f.py:1-2", "Q")
        self.assertIn("sha1aaa", text)          # 真 SHA 的前缀:保留
        self.assertNotIn("deadbeef", text)      # 编造:丢弃
        self.assertNotIn("9999999", text)


class TestVerifyCited(unittest.TestCase):
    def test_keeps_only_prefix_matches(self):
        real = ["abc1234567890", "def9876543210"]
        cited = ["abc1234", "def9876543210", "ffffff", "abc1234567890extra"]
        # 双向前缀:短引真 SHA、全等、以及真 SHA 是引用前缀 均保留;无关的丢
        self.assertEqual(ask._verify_cited(cited, real),
                         ["abc1234", "def9876543210", "abc1234567890extra"])

    def test_empty_inputs(self):
        self.assertEqual(ask._verify_cited([], ["abc"]), [])
        self.assertEqual(ask._verify_cited(["abc"], []), [])


if __name__ == "__main__":
    unittest.main()
