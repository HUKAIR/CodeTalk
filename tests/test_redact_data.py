"""redact_data:在 json.dumps / HTML 编码前递归脱敏字符串叶子。

根因:编码会把 " 转义成 \\",使 redact_secrets 的 key="value" 定界模式匹配不到,
secret 逃过末端整页脱敏。故 put_narrative 等落盘点须在「未编码的原始文本」上脱敏。"""
import json
import unittest

from vibetrace.cache import Cache
from vibetrace.config import redact_data


class TestRedactData(unittest.TestCase):
    def test_redacts_string_leaves_recursively(self):
        out = redact_data({"a": 'password="hunter2hunter2X"',
                           "b": ['token="Abcd1234Efgh5"', 3, None],
                           "c": {"d": "plain prose"}})
        blob = json.dumps(out, ensure_ascii=False)
        self.assertNotIn("hunter2hunter2X", blob)
        self.assertNotIn("Abcd1234Efgh5", blob)
        self.assertIn("[REDACTED]", blob)
        self.assertEqual(out["c"]["d"], "plain prose")   # 非 secret 原样
        self.assertEqual(out["b"][1], 3)                 # 非字符串原样

    def test_put_narrative_redacts_quoted_keyvalue_before_dumps(self):
        # 旧版 redact_secrets(json.dumps(...)) 在转义后脱敏,key="value" 漏网落盘
        c = Cache(":memory:")
        c.put_narrative("a" * 40, "/p", "m",
                        {"what": 'set password="hunter2hunter2X" done', "why": "w"})
        got = json.dumps(c.get_narrative("a" * 40), ensure_ascii=False)
        c.close()
        self.assertNotIn("hunter2hunter2X", got)
        self.assertIn("[REDACTED]", got)


if __name__ == "__main__":
    unittest.main()
