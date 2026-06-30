import unittest

from codetalk.config import redact_secrets


class TestRedactSecrets(unittest.TestCase):
    def test_redacts_new_secret_kinds(self):
        cases = {
            "Google API key": "AIzaSyA1234567890abcdefghijklmnopqrstuvw",
            "Google OAuth": "123456789012-abcdefghijklmnopqrstuvwxyz123456"
                            ".apps.googleusercontent.com",
            "Stripe": "sk_live_0123456789abcdefghijABCD",
            "SendGrid": "SG.abcdefghijklmnopqrstuv."
                        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRST",
            "JWT": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
                   ".eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36",
            "Slack webhook": "https://hooks.slack.com/services/"
                             "T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX",
        }
        for name, secret in cases.items():
            out = redact_secrets("前缀 " + secret + " 后缀")
            self.assertNotIn(secret, out, name)
            self.assertIn("[REDACTED]", out, name)
            self.assertIn("后缀", out, name)  # 周边保留

    def test_redacts_whole_pem_block_not_just_header(self):
        pem = ("-----BEGIN RSA PRIVATE KEY-----\n"
               "MIIEowIBAAKCAQEA1234567890abcdefBODYLINE\n"
               "-----END RSA PRIVATE KEY-----")
        out = redact_secrets("key:\n" + pem + "\ndone")
        self.assertNotIn("BODYLINE", out)        # 密钥正文也被脱敏,非仅头行
        self.assertIn("[REDACTED]", out)
        self.assertIn("done", out)

    def test_benign_text_untouched(self):
        for benign in ["普通一句话", "def foo():\n    return 42",
                       "AI 替我做了什么、为什么"]:
            self.assertEqual(redact_secrets(benign), benign)

    def test_non_str_passthrough(self):
        self.assertIsNone(redact_secrets(None))
        self.assertEqual(redact_secrets(123), 123)


if __name__ == "__main__":
    unittest.main()
