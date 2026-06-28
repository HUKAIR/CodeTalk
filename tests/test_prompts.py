import unittest

from vibetrace import course
from vibetrace.prompts import ASK_SYSTEM_PROMPT, SYSTEM_PROMPT


class TestAskGrounding(unittest.TestCase):
    def test_grounding_priority_present(self):
        # P1.2:ask 接地优先级显式化(commit 叙事 > 面包屑 > 推断;冲突取最新)
        self.assertIn("信息优先级", ASK_SYSTEM_PROMPT)
        self.assertIn("最新", ASK_SYSTEM_PROMPT)

    def test_anti_slop_discipline_present(self):
        # ask 回答也加去-AI-腔文风纪律(与叙事同口径)
        self.assertIn("文风纪律", ASK_SYSTEM_PROMPT)
        self.assertIn("开场陈词", ASK_SYSTEM_PROMPT)

    def test_counter_evidence_self_check(self):
        # A2:材料含「否决备选」/「风险/待验证」时,须在 unsure 显式核对结论是否与之冲突
        # (零成本反证据自洽,复用现有 unsure 字段;_retrieve 已把这两类拼进 context)
        self.assertIn("否决备选", ASK_SYSTEM_PROMPT)
        self.assertIn("风险/待验证", ASK_SYSTEM_PROMPT)
        self.assertIn("冲突", ASK_SYSTEM_PROMPT)


class TestNarrativeStyle(unittest.TestCase):
    def test_anti_slop_discipline_present(self):
        # P1.1:digest/course 共享的反 AI 腔文风纪律
        self.assertIn("文风纪律", SYSTEM_PROMPT)
        self.assertIn("开场陈词", SYSTEM_PROMPT)

    def test_style_balance_guard_protects_accuracy(self):
        # 去味平衡护栏(research-backed:防过度去味伤准确 + 护逐字护城河):
        # 技术术语/SHA/逐字照原样,准确高于文风。digest 与 ask 同口径。
        for p in (SYSTEM_PROMPT, ASK_SYSTEM_PROMPT):
            self.assertIn("照原样", p)
            self.assertIn("准确高于文风", p)


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
