"""Web 聊天出口脱敏:整体 redact_data 收口,citation.verbatim / highlights 等
所有字段都不得把原始面包屑 secret 泄露到浏览器(逐字段脱敏曾漏 verbatim/highlights)。"""
import unittest
import warnings
from unittest import mock

from fastapi.testclient import TestClient

from codetalk import web

# redact_secrets 实测能命中的 secret 形(短/随机串不命中,会得假阴性)
_SECRET = 'password="hunter2secretvalue"'
_RAW = "hunter2secretvalue"


def _client():
    return TestClient(web.app, base_url="http://127.0.0.1")


def _planted_out():
    """模拟 chat.answer 返回:verbatim + highlights 携带原始(未脱敏)面包屑 secret。"""
    return {
        "answer": f"设了 {_SECRET} 见引用",
        "citations": [{
            "id": 0, "sha": "abc1234", "kind": "commit",
            "evidence": f"决策:{_SECRET}",
            "verbatim": f"{_SECRET} in db init",     # ← 曾漏脱敏的字段
            "sources": [{"type": "commit", "sha": "abc1234"}],
        }],
        "highlights": [{"text": f"{_SECRET} in db init", "cite_id": 0}],  # ← 曾漏
        "conv_id": "c1", "turn_seq": 0,
    }


class TestWebChatEgressRedaction(unittest.TestCase):
    def _post(self):
        with mock.patch.object(web.chat, "answer", return_value=_planted_out()), \
             mock.patch.object(web, "_llm", return_value=None), \
             mock.patch.object(web, "Cache", lambda *_a, **_k: mock.MagicMock()), \
             warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return _client().post("/api/chat", json={"question": "why"})

    def test_chat_response_fully_redacted(self):
        r = self._post()
        self.assertEqual(r.status_code, 200)
        body = r.text
        self.assertNotIn(_RAW, body)                  # 原始 secret 不得出现在任何字段
        self.assertIn("[REDACTED]", body)
        data = r.json()
        # 逐字段确认:verbatim / highlights 这两个曾漏的字段也脱敏了
        self.assertNotIn(_RAW, data["citations"][0]["verbatim"])
        self.assertNotIn(_RAW, data["highlights"][0]["text"])
        self.assertEqual(data["highlights"][0]["cite_id"], 0)  # 结构/int 保留


if __name__ == "__main__":
    unittest.main()
