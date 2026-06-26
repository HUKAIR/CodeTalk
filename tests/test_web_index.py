import unittest
import warnings
from unittest import mock

from fastapi.testclient import TestClient

from vibetrace import web


class TestWebIndex(unittest.TestCase):
    def test_index_renders_tree_data(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = TestClient(web.app).get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("var TREE", r.text)                # $tree_data 已替换注入
        self.assertNotIn("$tree_data", r.text)           # 占位已消费

    def test_index_double_redaction(self):
        # 注入含 secret 模式的合成路径 → 出口须 [REDACTED]、原 secret 不漏
        payload = {"nodes": {"name": "", "type": "dir", "changed": True,
                             "children": [{"name": "k.py", "type": "file",
                                           "path": "sk-abcdef0123456789ABCDEF/k.py",
                                           "code": " M", "label": "已修改"}]},
                   "status": [{"path": "sk-abcdef0123456789ABCDEF/k.py", "code": " M", "label": "已修改"}]}
        with mock.patch.object(web.filetree, "tree_payload", return_value=payload):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                r = TestClient(web.app).get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("[REDACTED]", r.text)
        self.assertNotIn("sk-abcdef0123456789ABCDEF", r.text)
