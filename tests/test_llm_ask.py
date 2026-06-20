import json
import unittest
from unittest import mock

from vibetrace.llm import LLMClient
from vibetrace.prompts import ASK_SCHEMA, ASK_SYSTEM_PROMPT


def _cfg():
    return {"provider": "deepseek", "model": "m",
            "providers": {"deepseek": {"base_url": "http://x/v1",
                                       "api_key": "k"}}}


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


class TestAskSystem(unittest.TestCase):
    def test_ask_schema_required_fields(self):
        self.assertEqual(ASK_SCHEMA["required"], ["answer", "cited_shas"])

    def test_system_param_threaded_into_request(self):
        captured = {}
        payload = {"choices": [{"message": {"content":
                   json.dumps({"answer": "a", "cited_shas": []})}}],
                   "usage": {}}

        def fake_urlopen(req, timeout=0):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _FakeResp(payload)

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            out = LLMClient(_cfg()).narrate("Q", schema=ASK_SCHEMA,
                                            system=ASK_SYSTEM_PROMPT)
        self.assertEqual(out["answer"], "a")
        sys_msg = captured["body"]["messages"][0]["content"]
        self.assertIn("单代码问答引擎", sys_msg)  # 用了 ASK 而非默认 SYSTEM_PROMPT

    def test_output_lang_directive_injected(self):
        captured = {}
        payload = {"choices": [{"message": {"content":
                   json.dumps({"answer": "a", "cited_shas": []})}}], "usage": {}}

        def fake_urlopen(req, timeout=0):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _FakeResp(payload)

        cfg = _cfg(); cfg["output_lang"] = "English"
        with mock.patch("urllib.request.urlopen", fake_urlopen):
            LLMClient(cfg).narrate("Q", schema=ASK_SCHEMA, system=ASK_SYSTEM_PROMPT)
        self.assertIn("English", captured["body"]["messages"][0]["content"])


if __name__ == "__main__":
    unittest.main()
