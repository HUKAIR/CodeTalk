"""codetalk review:统一 diff 解析 + 逐改动块零-LLM 历史决策溯源。纯本地 git,无 key/网络。"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from codetalk import review as review_mod
from codetalk.blame import collect_graded, segment_has_why
from codetalk.cache import Cache
from codetalk.review import parse_unified_diff, review


def _git(a, c):
    subprocess.run(["git", *a], cwd=c, check=True, capture_output=True, text=True)


class TestParseUnifiedDiff(unittest.TestCase):
    def test_extracts_per_hunk_post_image_ranges(self):
        diff = ("diff --git a/foo.py b/foo.py\n--- a/foo.py\n+++ b/foo.py\n"
                "@@ -1,3 +1,4 @@\n a\n+b\n c\n"
                "@@ -10,2 +12,3 @@\n x\n+y\n z\n")
        self.assertEqual(parse_unified_diff(diff),
                         [("foo.py", 1, 4), ("foo.py", 12, 14)])

    def test_single_line_hunk_and_dev_null_skipped(self):
        diff = ("--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+only\n"
                "--- a/gone.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n")
        # new.py 单行 hunk(+1 无 count → 1 行);删除到 /dev/null 的块 cur=None 跳过
        self.assertEqual(parse_unified_diff(diff), [("new.py", 1, 1)])

    def test_empty_or_garbage_no_crash(self):
        self.assertEqual(parse_unified_diff(""), [])
        self.assertEqual(parse_unified_diff("not a diff at all"), [])


class TestReview(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)
        _git(["init", "-q"], self.d)
        _git(["config", "user.email", "t@t"], self.d)
        _git(["config", "user.name", "t"], self.d)
        self.f = Path(self.d) / "a.py"
        self.f.write_text("l1\nl2\nl3\n")
        _git(["add", "."], self.d)
        _git(["commit", "-q", "-m", "feat: 初版\n\nVibe-Decision: 选三行布局便于演示"], self.d)
        self.db = str(Path(self.d) / "cache.db")

    def test_review_grounds_changed_lines_to_real_commit(self):
        self.f.write_text("l1\nCHANGED\nl3\n")          # 改第 2 行(未提交)
        diff = subprocess.run(["git", "-C", self.d, "diff", "HEAD"],
                              capture_output=True, text=True).stdout
        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.db):
            out, err = review(self.d, diff)
        self.assertIsNone(err)
        self.assertIn("a.py", out)                       # 命中文件
        self.assertIn("commit 触达", out)                # 复用 blame 头:有历史
        self.assertIn("选三行布局便于演示", out)          # 引到真实 Vibe-Decision 原话

    def test_review_labels_line_precision(self):
        # 改有历史的行 → 块尾标「溯源精度:行级精确 · 有据」(确定性准度信号)
        self.f.write_text("l1\nCHANGED\nl3\n")
        diff = subprocess.run(["git", "-C", self.d, "diff", "HEAD"],
                              capture_output=True, text=True).stdout
        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.db):
            out, err = review(self.d, diff)
        self.assertIsNone(err)
        self.assertIn("溯源精度:行级精确", out)
        self.assertIn("有据", out)                        # 命中真实 Vibe-Decision

    def test_review_labels_file_precision_on_out_of_range_hunk(self):
        # hunk 行范围超出文件长度 → line_log(-L)失败 → 文件级降级 → 标「文件级降级」
        diff = "--- a/a.py\n+++ b/a.py\n@@ -1 +999 @@\n+x\n"
        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.db):
            out, err = review(self.d, diff)
        self.assertIsNone(err)
        self.assertIn("溯源精度:文件级降级", out)

    def test_review_surfaces_rejected_alternative(self):
        # 带 Vibe-Rejected 的提交 → review/blame 把「否决备选」作一等公民标出(防重引入)
        self.f.write_text("l1\nl2\nl3\nl4\n")            # 第 4 行由带 Vibe-Rejected 的提交引入
        _git(["commit", "-aqm",
              "feat: 加行\n\nVibe-Rejected: 曾想用方案X,放弃因Y"], self.d)
        self.f.write_text("l1\nl2\nl3\nCHANGED4\n")      # 改第 4 行(未提交)
        diff = subprocess.run(["git", "-C", self.d, "diff", "HEAD"],
                              capture_output=True, text=True).stdout
        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.db):
            out, err = review(self.d, diff)
        self.assertIsNone(err)
        self.assertIn("否决备选", out)
        self.assertIn("曾想用方案X,放弃因Y", out)

    def test_review_top_interception_checklist(self):
        # 改动触及带 Vibe-Rejected 的块 → 顶部「⚠ 拦截检查」清单(人判防重引入),在正文块之前
        self.f.write_text("l1\nl2\nl3\nl4\n")
        _git(["commit", "-aqm",
              "feat: 加行\n\nVibe-Rejected: 曾想用方案X,放弃因Y"], self.d)
        self.f.write_text("l1\nl2\nl3\nCHANGED4\n")
        diff = subprocess.run(["git", "-C", self.d, "diff", "HEAD"],
                              capture_output=True, text=True).stdout
        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.db):
            out, err = review(self.d, diff)
        self.assertIsNone(err)
        self.assertIn("拦截检查", out)                         # 顶部拦截清单
        self.assertIn("曾想用方案X,放弃因Y", out)
        self.assertLess(out.index("拦截检查"), out.index("溯源精度:"))  # 在正文块(精度标注带冒号)之前
        self.assertIn("interceptions.md", out)                 # 指向里程碑的家

    def test_review_no_interception_section_when_clean(self):
        # 改动块只有 Vibe-Decision(无 Rejected)→ 不出拦截清单(不污染常规 review)
        self.f.write_text("l1\nCHANGED\nl3\n")
        diff = subprocess.run(["git", "-C", self.d, "diff", "HEAD"],
                              capture_output=True, text=True).stdout
        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.db):
            out, err = review(self.d, diff)
        self.assertIsNone(err)
        self.assertNotIn("拦截检查", out)

    def test_review_marks_uncovered_block_as_no_evidence(self):
        # 全新文件的行无 git 历史 → 该块显式标「无据」+ 统一三档徽标「[无逐字溯源]」而非编造
        diff = ("--- /dev/null\n+++ b/brand_new.py\n@@ -0,0 +1,2 @@\n+x\n+y\n")
        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.db):
            out, err = review(self.d, diff)
        self.assertIsNone(err)
        self.assertIn("无据", out)
        self.assertIn("[无逐字溯源]", out)              # A1:无据档的一眼可读徽标

    def test_review_caps_hunks_on_large_diff(self):
        # 大仓大 diff:逐块 blame O(hunks) → 上限 MAX_REVIEW_HUNKS,超出截断 + 提示(防卡死/过慢)
        from codetalk.review import MAX_REVIEW_HUNKS
        n = MAX_REVIEW_HUNKS + 5
        diff = "--- a/a.py\n+++ b/a.py\n" + "".join(
            f"@@ -{i},1 +{i},1 @@\n-x\n+y\n" for i in range(1, n + 1))
        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.db):
            out, err = review(self.d, diff)
        self.assertIsNone(err)
        self.assertIn(str(n), out)                       # 回显总块数
        self.assertIn(str(MAX_REVIEW_HUNKS), out)        # 回显上限
        self.assertIn("codetalk blame", out)            # 指引单点查余下
        # 只处理前 cap 块:输出里的块标记数不超过 cap
        self.assertLessEqual(out.count("溯源精度:"), MAX_REVIEW_HUNKS)

    def test_review_empty_diff_friendly(self):
        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.db):
            out, err = review(self.d, "")
        self.assertIsNone(err)
        self.assertIn("没有可分析的改动块", out)

    def test_review_default_uses_git_diff_head(self):
        self.f.write_text("l1\nCHANGED2\nl3\n")          # diff_text=None → 内部工作树 diff
        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.db):
            out, err = review(self.d)                     # 不传 diff
        self.assertIsNone(err)
        self.assertIn("a.py", out)

    def test_review_default_includes_untracked_text_file(self):
        (Path(self.d) / "brand_new.py").write_text("print('new')", encoding="utf-8")
        (Path(self.d) / "second_new.py").write_text("print('second')", encoding="utf-8")
        with mock.patch.object(review_mod, "CACHE_DB_PATH", self.db):
            cards, err, _ = review_mod.build_review_cards(self.d)
        self.assertIsNone(err)
        files = {card["change"]["file"] for card in cards}
        self.assertEqual(files, {"brand_new.py", "second_new.py"})
        self.assertTrue(all(card["kind"] == "no_evidence" for card in cards))


class TestGroundingBadge(unittest.TestCase):
    """A1:接地强度三档徽标(行级/文件级/无逐字溯源)一眼可读;只描述 provenance 轴,
    绝不打语义对错(R6:零-LLM 不判 grounded/inferred/unsupported)。"""
    def test_three_tier_badge_glanceable(self):
        from codetalk.review import _precision_label
        seg = [{"why": "x"}]
        self.assertIn("[行级溯源]", _precision_label("line", seg))
        self.assertIn("[文件级溯源]", _precision_label("file", seg))
        self.assertIn("[无逐字溯源]", _precision_label("none", []))
        # 现有「溯源精度:…」细节仍在(徽标是前置概览,不替换细节)
        self.assertIn("溯源精度:", _precision_label("line", seg))

    def test_badge_is_provenance_not_semantic(self):
        from codetalk.review import _BADGE
        for v in _BADGE.values():
            for banned in ("推测", "inferred", "unsupported", "grounded",
                           "对不对", "可信", "可靠", "正确"):
                self.assertNotIn(banned, v)


class TestSegmentHasWhy(unittest.TestCase):
    def test_why_decisions_evidence_count(self):
        self.assertTrue(segment_has_why({"why": "x"}))
        self.assertTrue(segment_has_why({"decisions": ["d"]}))
        self.assertTrue(segment_has_why({"evidence": [{"source": "c"}]}))
        self.assertTrue(segment_has_why({"rejected": ["曾想用 X"]}))  # 否决备选也是 authored why

    def test_risks_only_and_empty_false(self):
        # Vibe-Watch(risks)是前瞻预测、非『为什么这么写』,不计
        self.assertFalse(segment_has_why(
            {"why": "", "decisions": [], "evidence": [], "risks": ["r"]}))
        self.assertFalse(segment_has_why({}))


class TestCollectGraded(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)
        _git(["init", "-q"], self.d)
        _git(["config", "user.email", "t@t"], self.d)
        _git(["config", "user.name", "t"], self.d)
        (Path(self.d) / "a.py").write_text("l1\nl2\nl3\n")
        _git(["add", "."], self.d)
        _git(["commit", "-q", "-m", "feat: 初版\n\nVibe-Decision: 选三行布局"], self.d)
        self.cache = Cache(str(Path(self.d) / "cache.db"))
        self.addCleanup(self.cache.close)

    def test_line_precision_with_range(self):
        segs, precision = collect_graded(self.cache, self.d, "a.py", 2, 2)
        self.assertEqual(precision, "line")
        self.assertTrue(segs)

    def test_file_precision_without_range(self):
        # 无行范围 → 文件级历史 → precision "file"
        _, precision = collect_graded(self.cache, self.d, "a.py", None, None)
        self.assertEqual(precision, "file")

    def test_none_precision_unknown_file(self):
        segs, precision = collect_graded(self.cache, self.d, "ghost.py", 1, 1)
        self.assertEqual(segs, [])
        self.assertEqual(precision, "none")


if __name__ == "__main__":
    unittest.main()
