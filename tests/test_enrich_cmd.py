"""enrich 子命令:富集补全全史中尚无叙事的 commit(跳过已缓存),闭合召回覆盖缺口。
富集需 LLM;用 fake LLM 测,不耗真 key/网络。"""
import contextlib
import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vibetrace import cli
from vibetrace.cache import Cache


def _git(a, c):
    subprocess.run(["git", *a], cwd=c, check=True, capture_output=True, text=True)


def _sha(c, rev="HEAD"):
    return subprocess.run(["git", "rev-parse", rev], cwd=c, check=True,
                          capture_output=True, text=True).stdout.strip()


class _FakeLLM:
    model = "fake"

    def __init__(self):
        self.calls = 0

    def narrate(self, prompt, cache_prefix=""):
        self.calls += 1
        return {"what": "补全的改动", "why": "补全的原因",
                "decisions": [], "risks": [], "open_loops": []}


class TestEnrichCmd(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)
        _git(["init", "-q"], self.d)
        _git(["config", "user.email", "t@t"], self.d)
        _git(["config", "user.name", "t"], self.d)
        f = Path(self.d) / "a.py"
        f.write_text("1\n"); _git(["add", "."], self.d)
        _git(["commit", "-q", "-m", "c1"], self.d)
        self.sha1 = _sha(self.d)
        f.write_text("2\n"); _git(["add", "."], self.d)
        _git(["commit", "-q", "-m", "c2"], self.d)
        self.sha2 = _sha(self.d)
        self.db = str(Path(self.d) / "cache.db")
        self.pkey = str(Path(self.d).resolve())

    def _run(self):
        fake = _FakeLLM()
        with mock.patch.object(cli, "CACHE_DB_PATH", self.db), \
             mock.patch("vibetrace.llm.LLMClient", return_value=fake), \
             contextlib.redirect_stdout(io.StringIO()):
            rc = cli.main(["enrich", "--project", self.d])
        return rc, fake

    def test_backfills_only_uncached(self):
        c = Cache(self.db)                       # 预置 sha1 叙事 → 只 sha2 该被补
        c.put_narrative(self.sha1, self.pkey, "m", {"why": "已有", "decisions": []})
        c.close()
        rc, fake = self._run()
        self.assertEqual(rc, 0)
        self.assertEqual(fake.calls, 1)          # 只补 1 个(sha2),跳过已缓存的 sha1
        c = Cache(self.db)
        self.assertIsNotNone(c.get_narrative(self.sha2))         # sha2 现已有叙事
        self.assertEqual(c.get_narrative(self.sha1)["why"], "已有")  # sha1 未被覆写
        c.close()

    def test_noop_when_all_cached(self):
        c = Cache(self.db)
        for s in (self.sha1, self.sha2):
            c.put_narrative(s, self.pkey, "m", {"why": "有"})
        c.close()
        rc, fake = self._run()
        self.assertEqual(rc, 0)
        self.assertEqual(fake.calls, 0)          # 全有 → 一次 LLM 都不调

    def test_set_narrative_evidence_adds_redacted_keeps_narrative(self):
        import json
        c = Cache(self.db)
        c.put_narrative(self.sha1, self.pkey, "m", {"why": "用乐观锁", "decisions": ["选 CAS"]})
        c.set_narrative_evidence(self.sha1, [{"source": "claude", "session_id": "s1",
            "prompts": ["key sk-abcdefghijklmnop1234"], "excerpts": []}])
        n = c.get_narrative(self.sha1); c.close()
        self.assertEqual(n["why"], "用乐观锁")              # LLM 叙事不动(immutable)
        self.assertEqual(n["decisions"], ["选 CAS"])
        blob = json.dumps(n, ensure_ascii=False)
        self.assertIn("[REDACTED]", blob)                  # evidence 落库脱敏
        self.assertNotIn("sk-abcdefghijklmnop1234", blob)

    def test_backfill_evidence_from_aligned_sessions(self):
        from datetime import datetime
        from vibetrace import enrich
        c = Cache(self.db)
        c.put_narrative(self.sha1, self.pkey, "m", {"why": "w", "decisions": []})  # 无 evidence
        commit = {"sha": self.sha1, "matches": [{"confidence": "high", "overlap": [],
            "session": {"session_id": "s1", "source": "claude",
                        "end": datetime(2026, 6, 1), "prompts": ["当初为什么这么写"],
                        "excerpts": []}}]}
        done = enrich.backfill_evidence([commit], c, self.pkey)
        n = c.get_narrative(self.sha1); c.close()
        self.assertEqual(done, 1)                          # 补了 1 条
        self.assertEqual(n["evidence"][0]["prompts"], ["当初为什么这么写"])  # 收割到原话锚点

    def test_backfill_evidence_skips_when_already_present(self):
        from vibetrace import enrich
        c = Cache(self.db)
        c.put_narrative(self.sha1, self.pkey, "m",
                        {"why": "w", "evidence": [{"source": "x"}]})   # 已有 evidence
        commit = {"sha": self.sha1, "matches": [{"confidence": "high", "overlap": [],
            "session": {"session_id": "s2", "source": "claude", "end": None,
                        "prompts": ["不该覆盖"], "excerpts": []}}]}
        self.assertEqual(enrich.backfill_evidence([commit], c, self.pkey), 0)  # 不覆盖既有
        c.close()

    def test_no_llm_exits_without_calling(self):
        with mock.patch.object(cli, "CACHE_DB_PATH", self.db), \
             contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()):
            rc = cli.main(["enrich", "--project", self.d, "--no-llm"])
        self.assertEqual(rc, 2)                   # 富集需 LLM:no_llm → 干净退出(非崩)


if __name__ == "__main__":
    unittest.main()
