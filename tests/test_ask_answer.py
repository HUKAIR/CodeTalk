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
        return {"answer": "因为是推理模型,3000 不够",
                "cited_shas": ["sha1aaa"], "unsure": ""}


def _patch_retrieve(ctx="[sha1aaa] 决策:用 urllib", state="sha1aaaabbbb"):
    return mock.patch.object(ask, "_retrieve",
                             lambda *a: (ctx, ["sha1aaaabbbb"], state))


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
        with mock.patch.object(ask, "_retrieve", lambda *a: ("", [], "")):
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


if __name__ == "__main__":
    unittest.main()
