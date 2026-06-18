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


class TestCourseDensity(unittest.TestCase):
    def test_density_rules_in_course_prompt(self):
        # P1.3:course 内容密度规则(无 commit 时 header 仍含规则)
        prompt = course._course_prompt([], {}, None)
        self.assertIn("2-3 句", prompt)
        self.assertIn("跨章", prompt)


if __name__ == "__main__":
    unittest.main()
