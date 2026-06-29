"""护城河盲测脚本:确定性部分(泄漏标 / 选 commit / 并排格式)。LLM 反推侧是 I/O,不在此测。"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import scripts.blind_test as bt  # noqa: E402
from scripts.blind_test import (  # noqa: E402
    _real_why, format_comparison, leakage, pick_commits, select_cleanest)


class TestLeakage(unittest.TestCase):
    def test_why_in_diff_flagged_contaminated(self):
        ratio, label = leakage("用乐观锁避免写超时", "+# 用乐观锁避免写超时\n+def save(): pass")
        self.assertGreaterEqual(ratio, 0.6)
        self.assertIn("夹带", label)

    def test_why_absent_flagged_not_in_diff(self):
        # 诚实:只标『字面未夹带』,不宣称反推必败(LLM 仍可推断)
        ratio, label = leakage("因为流式响应不断连才改显式循环",
                               "+def retry(x):\n+    return x + 1\n")
        self.assertLess(ratio, 0.25)
        self.assertIn("未夹带", label)
        self.assertNotIn("只能编", label)        # 不越界宣称反推无效

    def test_empty_why_safe(self):
        self.assertEqual(leakage("", "diff")[0], 0.0)

    def test_ratio_never_exceeds_one(self):
        # 重复子串不应让占比 >1(get_matching_blocks 切分第一序列,不重复计)
        self.assertLessEqual(leakage("用乐观锁", "用乐观锁 用乐观锁 用乐观锁")[0], 1.0)


class TestRealWhy(unittest.TestCase):
    def test_combines_decision_and_rejected(self):
        body = "Vibe-Decision: 用乐观锁\nVibe-Rejected: 悲观锁太重"
        real = _real_why(body)
        self.assertIn("用乐观锁", real)
        self.assertIn("(否决)悲观锁太重", real)


class TestPickCommits(unittest.TestCase):
    def test_filters_breadcrumbless_newest_first(self):
        commits = [{"sha": "a" * 40, "body": "no crumb", "subject": "x"},
                   {"sha": "b" * 40, "body": "Vibe-Decision: d", "subject": "y"},
                   {"sha": "c" * 40, "body": "Vibe-Rejected: r", "subject": "z"}]
        shas = [c["sha"] for c in pick_commits(commits)]
        self.assertNotIn("a" * 40, shas)         # 无面包屑 → 排除
        self.assertEqual(shas[0], "c" * 40)      # 新→旧


class TestSelectCleanest(unittest.TestCase):
    def test_picks_lowest_leakage_ascending(self):
        # 默认挑泄漏最低的(干净样本),而非最新——否则专挑被污染 commit 反向坑人
        scored = [{"ratio": 0.5, "id": "m"}, {"ratio": 0.1, "id": "lo"},
                  {"ratio": 0.8, "id": "hi"}]
        out = select_cleanest(scored, 2)
        self.assertEqual([s["id"] for s in out], ["lo", "m"])   # 0.1, 0.5(升序)

    def test_respects_n(self):
        scored = [{"ratio": i / 10} for i in range(5)]
        self.assertEqual(len(select_cleanest(scored, 2)), 2)


class TestFormat(unittest.TestCase):
    def test_shows_both_sides_and_human_verdict(self):
        out = format_comparison({"sha": "a" * 40, "subject": "s", "date": "2026-06-27"},
                                ["真实:用乐观锁"], "反推:大概为性能", 0.1, "diff 查无(...)")
        self.assertIn("真实:用乐观锁", out)
        self.assertIn("反推:大概为性能", out)
        self.assertIn("你来判", out)             # 不自动判对错
        self.assertIn("diff 查无", out)


class TestCodeOnlyDiff(unittest.TestCase):
    """滤掉散文:doc 文件段从 diff 剔除(doc 编辑的 diff 本身是理由,留着让纯 diff 反推
    变『读散文』而非真考古);doc-only commit 的 diff 变空 → main 将排除。"""
    def test_strips_doc_section_keeps_code(self):
        from scripts.blind_test import _code_only_diff
        diff = ("diff --git a/CLAUDE.md b/CLAUDE.md\n@@ -1 +1 @@\n-x\n+理由散文在此\n"
                "diff --git a/vibetrace/x.py b/vibetrace/x.py\n@@ -1 +1 @@\n-a\n+b\n")
        out = _code_only_diff(diff)
        self.assertIn("vibetrace/x.py", out)
        self.assertNotIn("理由散文在此", out)        # doc 段被剔除
        self.assertNotIn("CLAUDE.md", out)

    def test_doc_only_becomes_empty(self):
        from scripts.blind_test import _code_only_diff
        diff = "diff --git a/docs/spec.md b/docs/spec.md\n@@ -1 +1 @@\n-x\n+散文理由\n"
        self.assertEqual(_code_only_diff(diff).strip(), "")

    def test_no_diff_header_returned_asis(self):
        from scripts.blind_test import _code_only_diff
        self.assertEqual(_code_only_diff("just text no header"), "just text no header")

    def test_is_doc_classification(self):
        from scripts.blind_test import _is_doc
        self.assertTrue(_is_doc("README.md"))
        self.assertTrue(_is_doc("docs/anything.py"))   # docs/ 区一律视为文档
        self.assertFalse(_is_doc("vibetrace/x.py"))
        self.assertFalse(_is_doc("vibetrace/console.html"))


class TestRedactionBeforeEgress(unittest.TestCase):
    """红线:diff 到达 LLM 前必脱敏(唯一出网点)。防未来重构悄悄挪掉 redact。"""
    def test_diff_redacted_before_reaching_llm(self):
        captured = {}

        class FakeClient:
            def __init__(self, cfg):
                pass

            def chat(self, messages):
                captured["payload"] = messages[-1]["content"]
                return "推断"

        commit = {"sha": "a" * 40, "body": "Vibe-Decision: 真决策",
                  "subject": "s", "date": "2026-06-27"}
        with mock.patch.object(bt, "collect_commit_files", return_value=([commit], None)), \
                mock.patch.object(bt, "commit_diff",
                                  return_value="+API_KEY=sk-abcdefghijklmnop1234 泄漏"), \
                mock.patch.object(bt, "LLMClient", FakeClient), \
                mock.patch.object(bt, "load_config", return_value={}):
            bt.main(".", 1)
        self.assertIn("payload", captured)
        self.assertNotIn("sk-abcdefghijklmnop1234", captured["payload"])  # 原 secret 不出网
        self.assertIn("[REDACTED]", captured["payload"])


if __name__ == "__main__":
    unittest.main()
