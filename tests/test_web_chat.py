import unittest
from pathlib import Path

from vibetrace import web


class TestWebChatFiletree(unittest.TestCase):
    def setUp(self):
        self.html = (Path(web.__file__).parent / "web_chat.html").read_text(encoding="utf-8")

    def test_drawer_and_render_present(self):
        self.assertIn('id="filesbtn"', self.html)
        self.assertIn('id="ftdrawer"', self.html)
        self.assertIn("function renderFiletree", self.html)
        self.assertIn("<details", self.html)             # 原生折叠

    def test_click_wires_q_and_target(self):
        self.assertIn("pendingTarget", self.html)        # 点文件记 target
        self.assertIn('querySelectorAll(".ftf")', self.html)  # 树节点绑键循环
        self.assertIn('"Enter"', self.html)              # 树 keydown(Tab handler 在 :65,Enter 为树独有)
        self.assertIn('" "', self.html)                  # Space + preventDefault
        self.assertIn('target: pendingTarget', self.html)  # fetch body 带 target
        self.assertIn("pendingTarget = null", self.html)   # 发送后清空,防误带

    def test_safety_and_invariants(self):
        self.assertIn('data-path="\'+esc(', self.html)   # 路径经 esc 转义
        self.assertIn(".children.length", self.html)     # 空树守卫判 children
        self.assertNotIn("${", self.html)                # 禁模板字面量
        self.assertEqual(self.html.count("$"), 1)        # 唯一 $ = $tree_data 占位
