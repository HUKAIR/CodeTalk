"""web_chat.html 答案内逐字命中 <mark> 高亮渲染(文本标记断言,不导 fastapi)。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestAnswerHighlight(unittest.TestCase):
    def setUp(self):
        # 直接读文件,避开 import vibetrace.web(fastapi 依赖)
        self.html = (Path(__file__).resolve().parent.parent
                     / "vibetrace" / "web_chat.html").read_text(encoding="utf-8")

    def test_highlight_render_present(self):
        self.assertIn("function setBody", self.html)        # 单一 innerHTML sink
        self.assertIn('<mark class="vb"', self.html)
        self.assertIn("data-cite", self.html)
        self.assertIn("ev.highlights", self.html)
        self.assertIn("高亮=逐字源自来源", self.html)         # legend

    def test_safety_and_invariants(self):
        self.assertIn("var acc", self.html)                 # 累积完整答案
        self.assertIn("renderDone(body, ev, acc)", self.html)
        self.assertIn("dataset.cite", self.html)            # chip 锚点
        self.assertIn("CSS.escape", self.html)              # mark→chip 反查
        self.assertIn("esc(s.text)", self.html)             # 高亮段文本经 esc
        self.assertIn("setBody(esc(acc))", self.html)       # 自检失败回退,仍转义
        self.assertNotIn("${", self.html)                   # 禁模板字面量
        self.assertIn("body.innerHTML = html", self.html)   # 答案体经单一 setBody sink


if __name__ == "__main__":
    unittest.main()
