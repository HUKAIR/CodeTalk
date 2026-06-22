"""O5(本地测试用例接地源):把仓内相关测试作为 why 的本地接地源 test_refs,
ask/blame 展示「相关测试(从测试场景反推设计)」。对位用户1 问卷一 Q3。纯本地。"""
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from vibetrace import ask, blame, enrich
from vibetrace.cache import Cache


def _proj_with_test():
    d = tempfile.mkdtemp()
    (Path(d) / "vibetrace").mkdir()
    (Path(d) / "tests").mkdir()
    (Path(d) / "vibetrace" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    (Path(d) / "tests" / "test_mod.py").write_text(
        "def test_alpha():\n    assert True\n\ndef test_beta():\n    assert True\n",
        encoding="utf-8")
    return d


class TestTestRefsHelper(unittest.TestCase):
    def test_maps_source_to_test(self):
        d = _proj_with_test()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        refs = enrich._test_refs(d, {"files": ["vibetrace/mod.py"]})
        self.assertEqual(refs, [{"path": "tests/test_mod.py",
                                 "names": ["test_alpha", "test_beta"]}])

    def test_changed_test_file_itself(self):
        d = _proj_with_test()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        refs = enrich._test_refs(d, {"files": ["tests/test_mod.py"]})
        self.assertEqual(refs, [{"path": "tests/test_mod.py",
                                 "names": ["test_alpha", "test_beta"]}])

    def test_none_when_no_matching_test(self):
        d = _proj_with_test()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        self.assertEqual(enrich._test_refs(d, {"files": ["vibetrace/other.py"]}), [])

    def test_empty_files(self):
        self.assertEqual(enrich._test_refs("/nonexistent", {}), [])


class TestAskDisplay(unittest.TestCase):
    REF = [{"path": "tests/test_mod.py", "names": ["test_alpha", "test_beta"]}]

    def test_format_test_refs(self):
        block = ask.format_test_refs(self.REF)
        self.assertIn("相关测试", block)
        self.assertIn("tests/test_mod.py", block)
        self.assertIn("test_alpha", block)

    def test_format_test_refs_empty(self):
        self.assertEqual(ask.format_test_refs([]), "")

    def test_with_evidence_appends_test_refs(self):
        out = ask._with_evidence("答案", [], self.REF)
        self.assertIn("答案", out)
        self.assertIn("相关测试", out)
        self.assertIn("tests/test_mod.py", out)


class TestBlameDisplay(unittest.TestCase):
    def test_emit_test_refs(self):
        lines = []
        blame._emit_test_refs(lines, [{"path": "tests/test_z.py", "names": ["test_w"]}])
        joined = "\n".join(lines)
        self.assertIn("相关测试", joined)
        self.assertIn("tests/test_z.py", joined)
        self.assertIn("test_w", joined)

    def test_emit_test_refs_empty_noop(self):
        lines = []
        blame._emit_test_refs(lines, [])
        self.assertEqual(lines, [])


class _FakeLLM:
    model = "fake"
    stats = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cache_hit_tokens": 0}

    def narrate(self, prompt, **kw):
        return {"what": "改了 mod", "why": "因为测试场景要求 X",
                "decisions": [], "risks": [], "open_loops": []}


class TestEndToEndDogfood(unittest.TestCase):
    """端到端:改动文件 → enrich 写 test_refs → ask/blame 读回并展示(链路成立)。"""

    def test_capture_to_display(self):
        d = _proj_with_test()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        commit = {"sha": "a" * 40, "subject": "feat: mod", "body": "",
                  "author": "t", "date": datetime(2026, 6, 21, tzinfo=timezone.utc),
                  "stat": "", "diff_excerpt": "", "files": ["vibetrace/mod.py"],
                  "matches": []}
        cache = Cache(":memory:")
        enrich.enrich_commits([commit], _FakeLLM(), cache, d)
        refs = commit["narrative"]["test_refs"]
        self.assertEqual(refs, [{"path": "tests/test_mod.py",
                                 "names": ["test_alpha", "test_beta"]}])
        # 读回并展示
        self.assertIn("tests/test_mod.py", ask.format_test_refs(refs))
        lines = []
        blame._emit_test_refs(lines, refs)
        self.assertIn("test_alpha", "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
