import unittest
from datetime import datetime, timezone

from codetalk import enrich
from codetalk.cache import Cache


class _FakeLLM:
    model = "fake"

    def narrate(self, prompt, *args, **kwargs):
        return {"what": "w", "why": "y", "decisions": [],
                "risks": [], "open_loops": []}


class _FailLLM:
    model = "fake"

    def narrate(self, prompt, *args, **kwargs):
        from codetalk.llm import LLMError
        raise LLMError("boom")


def _session(sid, source, confidence_hint, prompts, excerpts):
    return {"session_id": sid, "source": source, "title": "t",
            "start": datetime(2026, 6, 17, 9, 0, tzinfo=timezone.utc),
            "end": datetime(2026, 6, 17, 10, 0, tzinfo=timezone.utc),
            "prompts": prompts, "excerpts": excerpts,
            "files_written": set(), "files_read": set()}


def _commit(matches):
    return {"sha": "abc123", "author": "x", "subject": "s", "body": "",
            "date": datetime(2026, 6, 17, 9, 30, tzinfo=timezone.utc),
            "stat": "", "diff_excerpt": "", "files": [], "matches": matches}


class TestEnrichEvidence(unittest.TestCase):
    def test_writes_top_matches_high_first(self):
        high = {"session": _session("highsess1", "claude", "high",
                                    ["p1", "p2", "p3", "p4"], ["e1", "e2", "e3"]),
                "overlap": ["a.py"], "confidence": "high"}
        low = {"session": _session("lowsess99", "cursor", "low",
                                   ["q1"], ["x1"]),
               "overlap": [], "confidence": "low"}
        cache = Cache(":memory:")
        # align 已排序:high 在前;这里直接给排好序的 matches
        enrich.enrich_commits([_commit([high, low])], _FakeLLM(), cache, "P")
        narr = cache.get_narrative("abc123")
        self.assertIn("evidence", narr)
        ev = narr["evidence"]
        self.assertEqual(len(ev), 2)                      # 取前 ≤2
        first = ev[0]
        self.assertEqual(first["confidence"], "high")     # high 第一
        self.assertEqual(first["session_id"], "highsess1")
        self.assertEqual(first["source"], "claude")
        self.assertEqual(first["ts"], "2026-06-17T10:00:00+00:00")  # session end
        self.assertEqual(first["prompts"], ["p1", "p2", "p3"])      # 截断 [:3]
        self.assertEqual(first["excerpts"], ["e1", "e2"])           # 截断 [:2]
        self.assertEqual(ev[1]["source"], "cursor")

    def test_no_matches_evidence_empty(self):
        cache = Cache(":memory:")
        enrich.enrich_commits([_commit([])], _FakeLLM(), cache, "P")
        narr = cache.get_narrative("abc123")
        self.assertEqual(narr.get("evidence"), [])

    def test_missing_source_falls_back(self):
        sess = _session("nosrc1234", "claude", "high", ["p"], ["e"])
        del sess["source"]
        match = {"session": sess, "overlap": ["a.py"], "confidence": "high"}
        cache = Cache(":memory:")
        enrich.enrich_commits([_commit([match])], _FakeLLM(), cache, "P")
        narr = cache.get_narrative("abc123")
        self.assertEqual(narr["evidence"][0]["source"], "?")

    def test_evidence_redacted_on_persist(self):
        sess = _session("seccess12", "claude", "high",
                        ["我的 token=sk-abcdefghijklmnop1234 在这"], ["e"])
        match = {"session": sess, "overlap": ["a.py"], "confidence": "high"}
        cache = Cache(":memory:")
        enrich.enrich_commits([_commit([match])], _FakeLLM(), cache, "P")
        narr = cache.get_narrative("abc123")
        prompt = narr["evidence"][0]["prompts"][0]
        self.assertNotIn("sk-abcdefghijklmnop1234", prompt)
        self.assertIn("[REDACTED]", prompt)

    def test_llm_failure_degraded_writes_empty_evidence(self):
        high = {"session": _session("s1", "claude", "high", ["p"], ["e"]),
                "overlap": ["a.py"], "confidence": "high"}
        commit = _commit([high])
        cache = Cache(":memory:")
        enrich.enrich_commits([commit], _FailLLM(), cache, "P")
        # 降级路径不缓存(degraded 不入 SHA),断言挂在 commit 上
        self.assertEqual(commit["narrative"].get("evidence"), [])
        self.assertTrue(commit["narrative"].get("degraded"))


if __name__ == "__main__":
    unittest.main()
