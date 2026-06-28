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


class TestWebChatUX(unittest.TestCase):
    """聊天 UX 打磨:Enter 发送(IME 安全)/ 自动滚到底 / aria-live 朗读 / Esc 关抽屉。"""
    def setUp(self):
        self.html = (Path(web.__file__).parent / "web_chat.html").read_text(encoding="utf-8")

    def test_enter_sends_ime_safe(self):
        self.assertIn("isComposing", self.html)          # IME 合成中不发(中文选词按 Enter 不误发)
        self.assertIn("requestSubmit", self.html)        # Enter → 触发表单提交
        self.assertIn("shiftKey", self.html)             # Shift+Enter 仍换行

    def test_autoscroll_sticky_bottom(self):
        self.assertIn("atBottom", self.html)             # 用户上滚阅读时不打断
        self.assertIn("scrollTo", self.html)             # 滚到最新

    def test_live_region_and_esc_drawer(self):
        self.assertIn('aria-live="polite"', self.html)   # 流式答读屏可达
        self.assertIn("Escape", self.html)               # Esc 关文件抽屉

    def test_copy_answer_button(self):
        self.assertIn("copybtn", self.html)              # 每条答案的复制按钮
        self.assertIn("clipboard", self.html)            # 复制到剪贴板(127.0.0.1 安全上下文)
        self.assertIn("已复制", self.html)                # 复制后反馈

    def test_still_single_dollar_placeholder(self):
        self.assertEqual(self.html.count("$"), 1)        # 改动不得引入 $(模板占位仅 $tree_data)
