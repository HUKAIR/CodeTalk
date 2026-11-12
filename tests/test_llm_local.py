"""本地 provider(ollama/LM Studio 等):无 key 不报错;no_llm 仍优先;云端空 key 仍报错。"""
import copy
import unittest

from codetalk.config import DEFAULTS
from codetalk.llm import LLMClient, LLMError


def _cfg(provider, providers_extra=None, no_llm=False):
    cfg = copy.deepcopy(DEFAULTS)
    cfg["provider"] = provider
    cfg["no_llm"] = no_llm
    if providers_extra:
        cfg["providers"].update(providers_extra)
    return cfg


class TestLocalProvider(unittest.TestCase):
    def test_ollama_default_constructs_without_key(self):
        llm = LLMClient(_cfg("ollama"))                 # 默认 URL 的主机名是 localhost
        self.assertTrue(llm.local)
        self.assertEqual(llm.base_url, "http://localhost:11434/v1")

    def test_explicit_local_flag_cannot_override_remote_host(self):
        with self.assertRaises(LLMError):
            LLMClient(_cfg("loc", {"loc": {"base_url": "https://api.example/v1",
                                             "api_key": "", "local": True}}))

    def test_localhost_base_url_implies_local(self):
        llm = LLMClient(_cfg("c", {"c": {"base_url": "http://127.0.0.1:8080/v1",
                                         "api_key": ""}}))
        self.assertTrue(llm.local)                      # 本机 base_url 即判 local

    def test_ipv6_loopback_implies_local(self):
        llm = LLMClient(_cfg("c", {"c": {"base_url": "http://[::1]:8080/v1",
                                         "api_key": ""}}))
        self.assertTrue(llm.local)

    def test_localhost_text_inside_remote_hostname_is_not_local(self):
        with self.assertRaises(LLMError):
            LLMClient(_cfg("trap", {"trap": {
                "base_url": "https://localhost.evil.example/v1",
                "api_key": ""}}))

    def test_cloud_empty_key_still_raises(self):
        with self.assertRaises(LLMError):               # 非 local + 空 key → 照旧报错
            LLMClient(_cfg("cloudx", {"cloudx": {"base_url": "https://api.cloudx.com/v1",
                                                 "api_key": ""}}))

    def test_anthropic_destination_is_explicit_not_environment_selected(self):
        llm = LLMClient(_cfg(
            "anthropic", {"anthropic": {"api_key": "configured-key"}}))
        self.assertEqual(llm.base_url, "https://api.anthropic.com")
        self.assertFalse(llm.local)

    def test_no_llm_overrides_local(self):
        with self.assertRaises(LLMError):               # no_llm 优先,本地也拦(数据不出本机)
            LLMClient(_cfg("ollama", no_llm=True))


if __name__ == "__main__":
    unittest.main()
