import unittest
from unittest import mock

from vibetrace import ask, gitlog
from vibetrace.cache import Cache


class TestRetrieve(unittest.TestCase):
    def test_assembles_cached_narrative_and_breadcrumbs(self):
        cache = Cache(":memory:")
        cache.put_narrative("sha1aaaabbbb", "P", "m",
                            {"why": "因为要省依赖", "decisions": ["LLM决定"],
                             "risks": [], "open_loops": []})
        with mock.patch.object(ask, "line_log",
                               lambda *a, **k: (["sha1aaaabbbb"], None)), \
             mock.patch.object(gitlog, "commit_body",
                               lambda p, s: "Vibe-Watch: 并发待验证"):
            ctx, shas, state, evidence, test_refs, pr_refs = ask._retrieve(".", "f.py", 1, 5, cache)
        self.assertIn("sha1aaa", ctx)        # 短 sha
        self.assertIn("因为要省依赖", ctx)     # 缓存叙事 why
        self.assertIn("LLM决定", ctx)         # 缓存决策
        self.assertIn("并发待验证", ctx)       # 面包屑 watch
        self.assertEqual(state, "sha1aaaabbbb")

    def test_line_log_failure_falls_back_to_file_log(self):
        cache = Cache(":memory:")
        called = {}

        def fake_file_log(*a, **k):
            called["hit"] = True
            return ([], None)

        with mock.patch.object(ask, "line_log", lambda *a, **k: ([], "boom")), \
             mock.patch.object(ask, "file_log", fake_file_log), \
             mock.patch.object(gitlog, "commit_body", lambda p, s: ""):
            ctx, shas, state, evidence, test_refs, pr_refs = ask._retrieve(".", "f.py", 1, 5, cache)
        self.assertTrue(called.get("hit"))
        self.assertEqual(ctx, "")


    def test_no_duplicate_when_narrative_already_has_breadcrumb(self):
        # 该 SHA 已被 digest:叙事里已折入面包屑;_retrieve 不应再重复一份
        cache = Cache(":memory:")
        cache.put_narrative("sha2ccccdddd", "P", "m",
                            {"why": "", "decisions": ["用 urllib 不引依赖"],
                             "risks": [], "open_loops": []})
        with mock.patch.object(ask, "line_log",
                               lambda *a, **k: (["sha2ccccdddd"], None)), \
             mock.patch.object(gitlog, "commit_body",
                               lambda p, s: "Vibe-Decision: 用 urllib 不引依赖"):
            ctx, shas, state, evidence, test_refs, pr_refs = ask._retrieve(".", "f.py", 1, 5, cache)
        self.assertEqual(ctx.count("用 urllib 不引依赖"), 1)

    def test_collects_evidence_from_narratives(self):
        # _retrieve 汇总命中 SHA narrative 的 evidence;旧缓存无键 .get 兼容不崩
        cache = Cache(":memory:")
        cache.put_narrative(
            "shaaaa11", "P", "m",
            {"why": "", "decisions": [], "risks": [], "open_loops": [],
             "evidence": [{"session_id": "s1", "source": "claude",
                           "ts": "t", "confidence": "high",
                           "prompts": ["原话X"], "excerpts": []}]})
        cache.put_narrative(    # 旧缓存:无 evidence 键
            "shabbb22", "P", "m",
            {"why": "", "decisions": [], "risks": [], "open_loops": []})
        with mock.patch.object(ask, "line_log",
                               lambda *a, **k: (["shaaaa11", "shabbb22"], None)), \
             mock.patch.object(gitlog, "commit_body", lambda p, s: ""):
            ctx, shas, state, evidence, test_refs, pr_refs = ask._retrieve(".", "f.py", 1, 5, cache)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["session_id"], "s1")

    def test_context_redacts_quote_delimited_secret_at_source(self):
        """关键隐私守门:context 由原始面包屑拼成,须在 _retrieve 源头脱敏。
        否则 MCP JSON(dumps 后 redact 漏 key="value")、CLI 降级 stdout、送外部 LLM
        三个出口都泄露 commit body 里的 secret 形 Vibe-Decision。"""
        cache = Cache(":memory:")
        with mock.patch.object(ask, "line_log",
                               lambda *a, **k: (["sha1aaaabbbb"], None)), \
             mock.patch.object(gitlog, "commit_body",
                               lambda p, s: 'Vibe-Decision: set password="hunter2leakXY" in cfg'):
            ctx, *_ = ask._retrieve(".", "f.py", 1, 5, cache)
        self.assertNotIn("hunter2leakXY", ctx)        # 源头已脱敏
        self.assertIn("[REDACTED]", ctx)

    def test_json_text_redacts_context_for_mcp(self):
        """MCP/agent 出口:_json_text 须出脱敏 JSON(degraded 模式 context 入 JSON)。"""
        import json as _json
        out = ask._json_text("degraded", "f.py", "why", ["sha1"],
                             context='决策:token="leakJSON88XY" rotate')
        self.assertNotIn("leakJSON88XY", out)
        self.assertIn("[REDACTED]", out)
        _json.loads(out)                              # 仍合法 JSON

    def test_same_evidence_anchor_deduped_across_shas(self):
        # 同一会话锚点(session_id+ts)跨多命中 SHA → 只汇总一次
        cache = Cache(":memory:")
        ev = {"session_id": "s1", "source": "claude", "ts": "t",
              "confidence": "high", "prompts": ["原话X"], "excerpts": []}
        cache.put_narrative("shaaaa11", "P", "m",
                            {"why": "", "decisions": [], "risks": [],
                             "open_loops": [], "evidence": [ev]})
        cache.put_narrative("shabbb22", "P", "m",
                            {"why": "", "decisions": [], "risks": [],
                             "open_loops": [], "evidence": [dict(ev)]})
        with mock.patch.object(ask, "line_log",
                               lambda *a, **k: (["shaaaa11", "shabbb22"], None)), \
             mock.patch.object(gitlog, "commit_body", lambda p, s: ""):
            ctx, shas, state, evidence, test_refs, pr_refs = ask._retrieve(
                ".", "f.py", 1, 5, cache)
        self.assertEqual(len(evidence), 1)       # 跨 SHA 同锚点只一份


if __name__ == "__main__":
    unittest.main()
