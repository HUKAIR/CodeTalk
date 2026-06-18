import unittest

from vibetrace.llm import ASK_SYSTEM_PROMPT


class TestAskGrounding(unittest.TestCase):
    def test_grounding_priority_present(self):
        # P1.2:ask 接地优先级显式化(commit 叙事 > 面包屑 > 推断;冲突取最新)
        self.assertIn("信息优先级", ASK_SYSTEM_PROMPT)
        self.assertIn("最新", ASK_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
