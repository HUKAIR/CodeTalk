"""topic_search 测试:主题级零-LLM 确定性接地召回。

命中 → 返回含对应 why/决策/原话锚点;无命中 → 友好提示。绝不调 LLM。
"""
import unittest

from codetalk.cache import Cache
from codetalk.search import topic_search


class TestTopicSearch(unittest.TestCase):
    def test_hit_returns_why_and_decisions(self):
        c = Cache(":memory:")
        c.put_narrative(
            "abc1234deadbeef", "/tmp/proj", "m",
            {"why": "用乐观锁避免超时",
             "decisions": ["放弃悲观锁,改用版本号 CAS"]})
        out = topic_search(c, "/tmp/proj", "乐观锁")
        self.assertIn("abc1234", out)            # sha 短码
        self.assertIn("用乐观锁避免超时", out)     # why
        self.assertIn("版本号 CAS", out)          # 决策

    def test_hit_renders_evidence_anchor(self):
        c = Cache(":memory:")
        c.put_narrative(
            "sha_ev0001", "/tmp/proj", "m",
            {"why": "用幂等去重保证一致",
             "evidence": [{"source": "claude", "session_id": "s12345678",
                           "ts": "2026-06-01", "confidence": "high",
                           "prompts": ["怎么防止重复扣款"]}]})
        out = topic_search(c, "/tmp/proj", "幂等去重")
        self.assertIn("怎么防止重复扣款", out)     # 原话锚点

    def test_no_hit_friendly_message(self):
        c = Cache(":memory:")
        c.put_narrative("sha_x0001", "/tmp/proj", "m", {"why": "无关内容"})
        out = topic_search(c, "/tmp/proj", "完全不沾边的关键词xyz")
        self.assertNotIn("sha_x0001", out)
        self.assertTrue(out.strip())             # 有友好提示文本

    def test_empty_query_friendly_message(self):
        c = Cache(":memory:")
        c.put_narrative("sha_y0001", "/tmp/proj", "m", {"why": "用乐观锁"})
        out = topic_search(c, "/tmp/proj", "")    # 无有效 term
        self.assertTrue(out.strip())

    def test_does_not_call_llm(self):
        # search 模块不应 import 或调用任何 LLM——以无网络/无 key 也能跑为证
        import codetalk.search as s
        with open(s.__file__, encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotIn("LLMClient", src)
        self.assertNotIn("llm.narrate", src)

    def test_redaction_inherited_no_plaintext_secret(self):
        c = Cache(":memory:")
        c.put_narrative(
            "sha_sec001", "/tmp/proj", "m",
            {"why": "鉴权用 sk-abcdefghijklmnop1234 这个 key 做幂等去重"})
        out = topic_search(c, "/tmp/proj", "幂等去重")
        self.assertNotIn("sk-abcdefghijklmnop1234", out)

    def test_question_with_secret_redacted_in_header(self):
        # 出口脱敏:question 回显进 header,含 secret 须脱敏(CLI 与 MCP 同口径)
        c = Cache(":memory:")
        c.put_narrative("sha_q00001", "/tmp/proj", "m", {"why": "用乐观锁避免超时"})
        out = topic_search(c, "/tmp/proj", "乐观锁 sk-secretkeyABCDEFGH123456")
        self.assertNotIn("sk-secretkeyABCDEFGH123456", out)
        self.assertIn("[REDACTED]", out)


def _git(args, cwd):
    import subprocess
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


class TestBreadcrumbSearch(unittest.TestCase):
    """零-LLM 逐字面包屑检索:不依赖 LLM 富集缓存,扫 commit message 的 Vibe-* 行。"""

    def setUp(self):
        import shutil
        import tempfile
        from pathlib import Path
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        _git(["init", "-q"], self.d)
        _git(["config", "user.email", "t@t"], self.d)
        _git(["config", "user.name", "t"], self.d)
        f = Path(self.d) / "f.py"
        f.write_text("a\n")
        _git(["add", "f.py"], self.d)
        _git(["commit", "-q", "-m",
              "c1 网络层\n\nVibe-Decision: 用 urllib 不引第三方——M0 禁三方依赖"],
             self.d)
        f.write_text("a\nb\n")
        _git(["add", "f.py"], self.d)
        _git(["commit", "-q", "-m", "c2 风险\n\nVibe-Watch: 胶囊到期待验证"],
             self.d)
        f.write_text("a\nb\nc\n")
        _git(["add", "f.py"], self.d)
        _git(["commit", "-q", "-m",
              "c3 provider 入口\n\n全部复用标准库 urllib 的 HTTP 路径,零新依赖。\n\n"
              "Vibe-Decision: 不引官方 SDK,走统一兼容协议"], self.d)

    def test_verbatim_breadcrumb_hit_no_cache_needed(self):
        c = Cache(":memory:")
        self.addCleanup(c.close)
        out = topic_search(c, self.d, "urllib")
        self.assertIn("[面包屑·逐字]", out)
        self.assertIn("urllib 不引第三方", out)
        self.assertIn("Vibe-Decision", out)
        self.assertRegex(out, r"\[[0-9a-f]{7}\]")        # 带 SHA 短码
        self.assertRegex(out, r"\d{4}-\d{2}-\d{2}")      # 带日期

    def test_keyword_match_case_insensitive(self):
        c = Cache(":memory:")
        self.addCleanup(c.close)
        out = topic_search(c, self.d, "URLLIB")
        self.assertIn("[面包屑·逐字]", out)

    def test_cjk_two_char_keyword_allowed(self):
        c = Cache(":memory:")
        self.addCleanup(c.close)
        out = topic_search(c, self.d, "胶囊")
        self.assertIn("[面包屑·逐字]", out)
        self.assertIn("胶囊到期待验证", out)

    def test_ascii_two_char_keyword_rejected(self):
        c = Cache(":memory:")
        self.addCleanup(c.close)
        out = topic_search(c, self.d, "ur")           # 纯 ASCII 维持 ≥3
        self.assertNotIn("[面包屑·逐字]", out)

    def test_merged_output_labels_narrative_source(self):
        c = Cache(":memory:")
        self.addCleanup(c.close)
        c.put_narrative("sha_nrr001", str(self.d), "m",
                        {"why": "urllib 分层是为了重试统一"})
        out = topic_search(c, self.d, "urllib")
        self.assertIn("[面包屑·逐字]", out)           # 逐字源
        self.assertIn("[叙事·LLM生成]", out)          # 富集源分开标注
        self.assertIn("重试统一", out)

    def test_commit_text_hit_labeled_with_excerpt(self):
        # 关键词只在 subject/body 散文(c3):[提交原文·逐字] + 摘录命中行
        c = Cache(":memory:")
        self.addCleanup(c.close)
        out = topic_search(c, self.d, "urllib")
        self.assertIn("[提交原文·逐字]", out)
        self.assertIn("全部复用标准库 urllib 的 HTTP 路径,零新依赖。", out)

    def test_three_tier_order_fixed(self):
        # 固定排序:面包屑逐字 → 提交原文逐字 → 叙事(即使正文命中的 c3 更新)
        c = Cache(":memory:")
        self.addCleanup(c.close)
        c.put_narrative("sha_nrr002", str(self.d), "m",
                        {"why": "urllib 分层是为了重试统一"})
        out = topic_search(c, self.d, "urllib")
        self.assertLess(out.index("[面包屑·逐字]"), out.index("[提交原文·逐字]"))
        self.assertLess(out.index("[提交原文·逐字]"), out.index("[叙事·LLM生成]"))

    def test_same_commit_listed_once_at_highest_tier(self):
        # c1 的 Vibe 行含 urllib;即使正文也命中,只按最高级列一次
        import subprocess
        c = Cache(":memory:")
        self.addCleanup(c.close)
        sha1 = subprocess.run(["git", "log", "--reverse", "--format=%H"],
                              cwd=self.d, capture_output=True,
                              text=True).stdout.splitlines()[0]
        out = topic_search(c, self.d, "urllib")
        self.assertEqual(out.count(sha1[:7]), 1)
        # c1 的短码出现在面包屑段而非提交原文段
        self.assertLess(out.index(sha1[:7]), out.index("[提交原文·逐字]"))

    def test_empty_state_with_records_suggests_new_keyword(self):
        c = Cache(":memory:")
        self.addCleanup(c.close)
        out = topic_search(c, self.d, "完全不沾边词xyzq")
        self.assertIn("换个关键词", out)
        self.assertNotIn("install-agent-seed", out)

    def test_empty_state_without_records_points_to_seed_and_demo(self):
        import shutil
        import tempfile
        from pathlib import Path
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        _git(["init", "-q"], d)
        _git(["config", "user.email", "t@t"], d)
        _git(["config", "user.name", "t"], d)
        (Path(d) / "g.py").write_text("x\n")
        _git(["add", "g.py"], d)
        _git(["commit", "-q", "-m", "光秃提交,无决策记录"], d)
        c = Cache(":memory:")
        self.addCleanup(c.close)
        out = topic_search(c, d, "urllib")
        self.assertIn("install-agent-seed", out)
        self.assertIn("codetalk demo", out)


if __name__ == "__main__":
    unittest.main()
