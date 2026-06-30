import unittest
from datetime import datetime, timezone

from codetalk import enrich
from codetalk.cache import Cache


class _CountingLLM:
    model = "fake"

    def __init__(self):
        self.calls = 0

    def narrate(self, *args, **kwargs):
        self.calls += 1
        return {"what": "w", "why": "y", "decisions": [],
                "risks": [], "open_loops": []}


def _commit(files):
    return {"sha": "c" + str(len(files)) + files[0] if files else "cempty",
            "author": "x", "subject": "chore: bump deps", "body": "",
            "date": datetime(2026, 6, 20, tzinfo=timezone.utc),
            "stat": "", "diff_excerpt": "", "files": files, "matches": []}


class TestIsTrivial(unittest.TestCase):
    def test_truth_table(self):
        T = enrich._is_trivial
        self.assertTrue(T({"files": ["poetry.lock"]}))
        self.assertTrue(T({"files": ["package-lock.json", "yarn.lock"]}))
        self.assertTrue(T({"files": ["dist/app.min.js"]}))   # basename 命中 *.min.js
        self.assertFalse(T({"files": ["a.py"]}))
        self.assertFalse(T({"files": ["poetry.lock", "a.py"]}))  # 混合 → 不跳
        self.assertFalse(T({"files": []}))                   # 空 files → 不跳


class TestEnrichSkipsTrivial(unittest.TestCase):
    def test_trivial_commit_skips_llm_and_caches_stub(self):
        cache = Cache(":memory:")
        llm = _CountingLLM()
        commit = _commit(["poetry.lock"])
        stats = enrich.enrich_commits([commit], llm, cache, "P")
        self.assertEqual(llm.calls, 0)               # 机械提交不调 LLM
        self.assertEqual(stats["trivial"], 1)
        narr = cache.get_narrative(commit["sha"])    # stub 已缓存
        self.assertIn("机械改动", narr["why"])
        self.assertEqual(narr["risks"], [])
        self.assertEqual(narr["open_loops"], [])

    def test_real_commit_still_narrated(self):
        cache = Cache(":memory:")
        llm = _CountingLLM()
        enrich.enrich_commits([_commit(["a.py"])], llm, cache, "P")
        self.assertEqual(llm.calls, 1)               # 真实提交照常叙事


if __name__ == "__main__":
    unittest.main()
