"""search 跨项目隔离:多仓共享 cache.db 下,搜 A 仓绝不召回 B 仓 commit(正确性 + 隐私 +
逐字接地三杀的修复)。FTS narrative_fts 是全局无 project 列虚拟表,必须 JOIN commit_narratives
按 project 过滤;MATCH 路径与 LIKE 回退都要过滤。"""
import unittest

from vibetrace import search
from vibetrace.cache import Cache


def _nar(decisions):
    return {"decisions": decisions, "risks": [], "open_loops": [], "why": ""}


class TestSearchProjectIsolation(unittest.TestCase):
    def setUp(self):
        self.c = Cache(":memory:")
        if not self.c.fts_ok:
            self.skipTest("FTS5/trigram 不可用")
        self.c.put_narrative("a" * 40, "/proj/A", "m", _nar(["用 compose 组装落地页"]))
        self.c.put_narrative("b" * 40, "/proj/B", "m", _nar(["用 compose 组装落地页"]))

    def test_search_narratives_filters_by_project(self):
        a_only = self.c.search_narratives("compose", "/proj/A")
        self.assertIn("a" * 40, a_only)
        self.assertNotIn("b" * 40, a_only)            # B 仓绝不泄漏进 A 的检索
        b_only = self.c.search_narratives("compose", "/proj/B")
        self.assertIn("b" * 40, b_only)
        self.assertNotIn("a" * 40, b_only)

    def test_like_fallback_also_filters(self):
        # 2 字中文走 LIKE 回退(trigram 对 2 字 CJK 无 shingle)——回退路径也不得跨仓
        self.c.put_narrative("c" * 40, "/proj/A", "m", _nar(["脱敏收口"]))
        self.c.put_narrative("d" * 40, "/proj/B", "m", _nar(["脱敏收口"]))
        a = self.c.search_narratives("脱敏", "/proj/A")
        self.assertIn("c" * 40, a)
        self.assertNotIn("d" * 40, a)

    def test_topic_search_output_has_no_other_project_sha(self):
        out = search.topic_search(self.c, "/proj/A", "compose")
        self.assertIn("a" * 7, out)                   # A 仓 commit 在
        self.assertNotIn("b" * 7, out)                # B 仓 commit 不在输出


if __name__ == "__main__":
    unittest.main()
