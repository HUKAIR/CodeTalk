import unittest

from vibetrace import course
from vibetrace.llm import ASK_SYSTEM_PROMPT, SYSTEM_PROMPT


class TestAskGrounding(unittest.TestCase):
    def test_grounding_priority_present(self):
        # P1.2:ask 接地优先级显式化(commit 叙事 > 面包屑 > 推断;冲突取最新)
        self.assertIn("信息优先级", ASK_SYSTEM_PROMPT)
        self.assertIn("最新", ASK_SYSTEM_PROMPT)


class TestNarrativeStyle(unittest.TestCase):
    def test_anti_slop_discipline_present(self):
        # P1.1:digest/course 共享的反 AI 腔文风纪律
        self.assertIn("文风纪律", SYSTEM_PROMPT)
        self.assertIn("开场陈词", SYSTEM_PROMPT)


class TestInferenceFieldsEmpty(unittest.TestCase):
    def test_empty_array_not_filler_instruction(self):
        # Level 1:推断字段无依据返回 [],不再教 LLM 写"材料不足"占位
        self.assertNotIn("直说", SYSTEM_PROMPT)        # 旧"直说材料不足"指令已撤
        self.assertIn("空数组", SYSTEM_PROMPT)          # 新:无依据返回 []
        self.assertIn("允许合理推测", SYSTEM_PROMPT)     # 平衡:仍鼓励推断,别变懒


class TestCourseDensity(unittest.TestCase):
    def test_density_rules_in_course_prompt(self):
        # P1.3:course 内容密度规则(无 commit 时 header 仍含规则)
        prompt = course._course_prompt([], {}, None)
        self.assertIn("2-3 句", prompt)
        self.assertIn("跨章", prompt)


if __name__ == "__main__":
    unittest.main()
