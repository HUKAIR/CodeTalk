import json, tempfile, unittest
import unittest.mock
from pathlib import Path
from vibetrace import config as cfgmod


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
