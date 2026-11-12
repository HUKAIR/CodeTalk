"""llm.chat():多轮自由文本对话补全(非 JSON,接地材料已在调用方拼好并脱敏)。
mock urlopen 测请求构造 + 文本解析;no_llm 闸门继承自 LLMClient.__init__(test_no_llm 已覆盖)。"""
import copy
import json
import unittest
from unittest import mock

from codetalk.config import DEFAULTS
from codetalk.llm import LLMClient


class _Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._b


class TestLlmChat(unittest.TestCase):
    def _client(self):
        cfg = copy.deepcopy(DEFAULTS)
        cfg["providers"]["deepseek"]["api_key"] = "sk-test1234567890abcd"
        return LLMClient(cfg)

    def test_openai_compat_chat_returns_text_no_json_mode(self):
        llm = self._client()
        captured = {}

        def fake_urlopen(req, timeout=180):
            captured["body"] = req.data
            return _Resp({"choices": [{"message": {"content": "接地综合答"}}],
                          "usage": {"prompt_tokens": 10, "completion_tokens": 5}})

        with mock.patch("codetalk.llm.urllib.request.urlopen", fake_urlopen):
            out = llm.chat([{"role": "system", "content": "S"},
                            {"role": "user", "content": "为什么用流式"}])
        self.assertEqual(out, "接地综合答")
        body = json.loads(captured["body"])
        self.assertNotIn("response_format", body)        # 自由文本,非 JSON 模式
        self.assertEqual(body["messages"][-1]["content"], "为什么用流式")
        self.assertEqual(llm.stats["output_tokens"], 5)  # 流式外也累计 token

    def test_chat_stream_yields_deltas(self):
        llm = self._client()
        sse = [b'data: {"choices":[{"delta":{"content":"\xe6\x8e\xa5\xe5\x9c\xb0"}}]}\n',
               b'data: {"choices":[{"delta":{"content":"\xe7\xad\x94\xe6\xa1\x88"}}]}\n',
               b'data: [DONE]\n']

        class _Stream:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def __iter__(self):
                return iter(sse)

        with mock.patch("codetalk.llm.urllib.request.urlopen",
                        lambda *a, **k: _Stream()):
            out = list(llm.chat_stream([{"role": "user", "content": "为什么"}]))
        self.assertEqual("".join(out), "接地答案")     # SSE delta 拼成完整文本


if __name__ == "__main__":
    unittest.main()
