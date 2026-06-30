import json
import unittest
from unittest import mock

from vibetrace.llm import LLMClient


def _cfg(provider="deepseek"):
    return {"provider": provider, "model": "m",
            "providers": {provider: {"base_url": "http://x/v1",
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


class TestOpenAICachePrefix(unittest.TestCase):
    def _capture(self, **narrate_kw):
        captured = {}
        payload = {"choices": [{"message": {"content":
                   json.dumps({"what": "x", "why": "y", "decisions": [],
                               "risks": [], "open_loops": []})}}], "usage": {}}

        def fake_urlopen(req, timeout=0):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _FakeResp(payload)

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            LLMClient(_cfg()).narrate("Q", **narrate_kw)
        return captured["body"]

    def test_prefix_joined_into_system_message(self):
        body = self._capture(cache_prefix="项目背景PREFIX_ABC")
        sys_msg = body["messages"][0]["content"]
        self.assertIn("项目背景PREFIX_ABC", sys_msg)

    def test_prefix_precedes_user_prompt(self):
        # 稳定前缀必须在 system 里、且不混进 user,才能让自动前缀缓存命中
        body = self._capture(cache_prefix="PREFIX_ABC")
        self.assertNotIn("PREFIX_ABC", body["messages"][1]["content"])

    def test_no_prefix_omits_block(self):
        body = self._capture()
        self.assertNotIn("PREFIX", body["messages"][0]["content"])


class TestOpenAITruncationSalvage(unittest.TestCase):
    """finish_reason==length(响应被 max_tokens 截断)时,提 max_tokens 重试抢救,
    而非原样重试 4 次烧 token 后丢一条 commit。"""

    def test_length_truncation_bumps_max_tokens_and_recovers(self):
        good = json.dumps({"what": "x", "why": "y", "decisions": [],
                           "risks": [], "open_loops": []})
        seq = [
            {"choices": [{"finish_reason": "length",
                          "message": {"content": '{"what":"x","wh'}}],  # 半截 JSON
             "usage": {}},
            {"choices": [{"finish_reason": "stop",
                          "message": {"content": good}}], "usage": {}},
        ]
        bodies = []

        def fake_urlopen(req, timeout=0):
            bodies.append(json.loads(req.data.decode("utf-8")))
            return _FakeResp(seq[len(bodies) - 1])

        with mock.patch("urllib.request.urlopen", fake_urlopen), \
             mock.patch("time.sleep", lambda *_: None):
            out = LLMClient(_cfg()).narrate("Q")
        self.assertEqual(out["what"], "x")                 # 抢救成功、返回完整结果
        self.assertEqual(len(bodies), 2)                   # 截断重试了一次
        self.assertGreater(bodies[1]["max_tokens"],
                           bodies[0]["max_tokens"])        # 第二次 max_tokens 提升了

    def test_truncation_capped_does_not_loop_forever(self):
        # 持续截断:max_tokens 涨到封顶后不再原地刷,最终 4 次内抛 LLMError(不无限)
        from vibetrace.llm import LLMError
        trunc = {"choices": [{"finish_reason": "length",
                              "message": {"content": "{"}}], "usage": {}}
        calls = []

        def fake_urlopen(req, timeout=0):
            calls.append(json.loads(req.data.decode("utf-8"))["max_tokens"])
            return _FakeResp(trunc)

        with mock.patch("urllib.request.urlopen", fake_urlopen), \
             mock.patch("time.sleep", lambda *_: None):
            with self.assertRaises(LLMError):
                LLMClient(_cfg()).narrate("Q")
        self.assertLessEqual(len(calls), 4)                # 不超过 MAX_ATTEMPTS
        self.assertLessEqual(max(calls), 8000)             # 封顶 MAX_TOKENS_CEIL


class _FakeAnthropicResp:
    class _Usage:
        input_tokens = 1
        output_tokens = 1
        cache_read_input_tokens = 0

    def __init__(self, text):
        class _Block:
            type = "text"
        self._block = _Block()
        self._block.text = text
        self.content = [self._block]
        self.usage = self._Usage()


class TestAnthropicCachePrefix(unittest.TestCase):
    def _capture(self, **narrate_kw):
        captured = {}
        text = json.dumps({"what": "x", "why": "y", "decisions": [],
                           "risks": [], "open_loops": []})

        fake_mod = mock.MagicMock()

        class _APIError(Exception):
            pass
        fake_mod.APIError = _APIError

        def fake_create(**kw):
            captured["kw"] = kw
            return _FakeAnthropicResp(text)

        fake_mod.Anthropic.return_value.messages.create.side_effect = fake_create
        with mock.patch.dict("sys.modules", {"anthropic": fake_mod}):
            LLMClient(_cfg("anthropic")).narrate("Q", **narrate_kw)
        return captured["kw"]

    def test_prefix_is_second_cached_system_block(self):
        kw = self._capture(cache_prefix="项目背景PREFIX_ABC")
        system = kw["system"]
        self.assertGreaterEqual(len(system), 2)
        self.assertEqual(system[1]["text"], "项目背景PREFIX_ABC")
        self.assertEqual(system[1]["cache_control"], {"type": "ephemeral"})

    def test_first_block_still_cached(self):
        kw = self._capture(cache_prefix="P")
        self.assertEqual(kw["system"][0]["cache_control"], {"type": "ephemeral"})

    def test_no_prefix_single_system_block(self):
        kw = self._capture()
        self.assertEqual(len(kw["system"]), 1)


if __name__ == "__main__":
    unittest.main()
