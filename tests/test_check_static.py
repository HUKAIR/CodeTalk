"""静态产物外链扫描守栏(I-6 红线):web 页面必须全内联、只 fetch 同源 /api,
绝不引外部 CDN/telemetry(否则破『不走 CDN / 不 phone home』)。并实测 web_chat.html 干净。"""
import unittest
from pathlib import Path

from scripts.check_static_no_external import check_file, scan

_PKG = Path(__file__).resolve().parent.parent / "codetalk"


class TestCheckStatic(unittest.TestCase):
    def test_flags_external_links(self):
        self.assertEqual(scan("<script src='https://cdn.example.com/x.js'></script>"),
                         ["https://cdn.example.com/x.js"])

    def test_same_origin_and_localhost_ok(self):
        self.assertEqual(scan("fetch('/api/chat'); img('http://127.0.0.1:8000/a')"), [])
        self.assertEqual(scan("a('http://localhost/x')"), [])

    def test_served_pages_have_no_external_links(self):
        # 红线实测:web app 托管的页面(对话页 + 接进来的控制台)绝不外联
        for name in ("web_chat.html", "console.html", "tunnel.html", "review.html"):
            self.assertEqual(check_file(_PKG / name), [], name)


if __name__ == "__main__":
    unittest.main()
