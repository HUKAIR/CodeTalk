import json, tempfile, unittest
import unittest.mock
from pathlib import Path
from codetalk import config as cfgmod


class TestProvidersShapeGuard(unittest.TestCase):
    """config.json 写成合法 JSON 但 providers 非 dict(标量/null)→ 不得让后续 .get 崩。"""

    def test_scalar_providers_falls_back_to_default_dict(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "config.json"
            p.write_text(json.dumps({"providers": "deepseek"}), encoding="utf-8")
            with unittest.mock.patch.object(cfgmod, "CONFIG_PATH", p):
                cfg = cfgmod.load_config()
            self.assertIsInstance(cfg["providers"], dict)        # 回退默认,不是字符串
            self.assertIn("deepseek", cfg["providers"])

    def test_null_providers_falls_back(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "config.json"
            p.write_text(json.dumps({"providers": None}), encoding="utf-8")
            with unittest.mock.patch.object(cfgmod, "CONFIG_PATH", p):
                cfg = cfgmod.load_config()
            self.assertIsInstance(cfg["providers"], dict)


class TestProviderEntries(unittest.TestCase):
    """新增 kimi/豆包/glm/grok/gemini 入口(deepseek/qwen 已有);全复用 llm.py 现成
    OpenAI 兼容 HTTP 路径,纯 stdlib 无新 SDK(守 M0 红线)。每个须有 https base_url,
    api_key 走 <PROVIDER>_API_KEY 环境变量回退。"""
    OPENAI_COMPAT = ["deepseek", "qwen", "kimi", "doubao", "glm", "grok", "gemini"]

    def test_all_requested_providers_registered(self):
        provs = cfgmod.DEFAULTS["providers"]
        for name in self.OPENAI_COMPAT:
            self.assertIn(name, provs, f"{name} 未注册")
            self.assertTrue(
                str(provs[name].get("base_url", "")).startswith("https://"),
                f"{name} 缺 OpenAI 兼容 base_url")

    def test_api_key_env_fallback_for_new_providers(self):
        for name in ("kimi", "glm", "grok", "gemini", "doubao"):
            with unittest.mock.patch.dict(
                    "os.environ", {f"{name.upper()}_API_KEY": "k-" + name}):
                self.assertEqual(
                    cfgmod.resolve_api_key(cfgmod.DEFAULTS, name), "k-" + name)


class TestRedactProseFalsePositive(unittest.TestCase):
    """通用 key-value secret 正则:含数字的真值仍脱敏,纯字母连字符散文不误伤。"""

    def test_prose_not_redacted(self):
        self.assertNotIn("[REDACTED]", cfgmod.redact_secrets("the secret: documentation-here"))
        self.assertNotIn("[REDACTED]", cfgmod.redact_secrets("password = your-account-name-here"))

    def test_real_value_with_digit_still_redacted(self):
        self.assertIn("[REDACTED]", cfgmod.redact_secrets("api_key: ab12cd34ef56gh78"))

    def test_mixed_case_secret_without_digit_still_redacted(self):
        # 无数字但有大小写转换的 key 仍脱敏(复审回归补丁,避免漏纯字母 mixed-case secret)
        self.assertIn("[REDACTED]", cfgmod.redact_secrets("token: AbCdEfGhIjKlMnOp"))


if __name__ == "__main__":
    unittest.main()
