import json
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
                "unsure": "并发部分没把握"}


def _patch_retrieve(ctx="[sha1aaa] 决策:用 urllib", state="sha1aaaabbbb"):
    return mock.patch.object(ask, "_retrieve",
                             lambda *a, **k: (ctx, ["sha1aaaabbbb"], state, [], [], []))


class TestAskJson(unittest.TestCase):
    def test_llm_mode_json_is_parseable_and_structured(self):
        cache, llm = Cache(":memory:"), _FakeLLM()
        with _patch_retrieve():
            text, err = ask.answer_question(cache, llm, ".", "P", "f.py:1-2",
                                            "为什么", as_json=True)
        self.assertIsNone(err)
        obj = json.loads(text)
        self.assertEqual(obj["mode"], "llm")
        self.assertEqual(obj["answer"], "因为是推理模型")
        self.assertEqual(obj["cited_shas"], ["sha1aaa"])
        self.assertEqual(obj["unsure"], "并发部分没把握")
        self.assertEqual(obj["target"], "f.py:1-2")
        self.assertEqual(obj["question"], "为什么")

    def test_cache_hit_json_reports_cache_mode(self):
        cache, llm = Cache(":memory:"), _FakeLLM()
        with _patch_retrieve():
            ask.answer_question(cache, llm, ".", "P", "f.py:1-2", "为什么",
                                as_json=True)
            text, err = ask.answer_question(cache, llm, ".", "P", "f.py:1-2",
                                            "为什么", as_json=True)
        obj = json.loads(text)
        self.assertEqual(obj["mode"], "cache")
        self.assertEqual(obj["answer"], "因为是推理模型")
        self.assertEqual(llm.calls, 1)

    def test_no_llm_json_gives_deterministic_retrieval(self):
        cache = Cache(":memory:")
        with _patch_retrieve():
            text, err = ask.answer_question(cache, None, ".", "P", "f.py:1-2",
                                            "Q", as_json=True)
        self.assertIsNone(err)
        obj = json.loads(text)
        self.assertEqual(obj["mode"], "degraded")
        self.assertIn("用 urllib", obj["context"])
        self.assertEqual(obj["shas"], ["sha1aaaabbbb"])

    def test_llm_failure_json_degrades_without_crash(self):
        cache = Cache(":memory:")

        class _BoomLLM:
            model = "m"

            def narrate(self, *a, **k):
                from vibetrace.llm import LLMError
                raise LLMError("boom")

        with _patch_retrieve():
            text, err = ask.answer_question(cache, _BoomLLM(), ".", "P",
                                            "f.py:1-2", "Q", as_json=True)
        self.assertIsNone(err)
        obj = json.loads(text)
        self.assertEqual(obj["mode"], "degraded")
        self.assertIn("用 urllib", obj["context"])

    def test_no_history_json_error_still_2tuple(self):
        cache = Cache(":memory:")
        with mock.patch.object(ask, "_retrieve",
                               lambda *a, **k: ("", [], "", [], [], [])):
            text, err = ask.answer_question(cache, _FakeLLM(), ".", "P", "x.py",
                                            "Q", as_json=True)
        self.assertIsNone(text)
        self.assertTrue(err)

    def test_json_redacts_secrets(self):
        cache = Cache(":memory:")

        class _LeakLLM:
            model = "m"

            def narrate(self, *a, **k):
                return {"answer": "key 是 sk-abcdefghijklmnop1234",
                        "cited_shas": []}

        with _patch_retrieve():
            text, err = ask.answer_question(cache, _LeakLLM(), ".", "P",
                                            "f.py:1-2", "Q", as_json=True)
        self.assertNotIn("sk-abcdefghijklmnop1234", text)
        self.assertIn("[REDACTED]", text)


if __name__ == "__main__":
    unittest.main()
