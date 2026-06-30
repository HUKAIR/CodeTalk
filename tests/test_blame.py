"""blame:零-LLM 行级决策溯源(真 git 临时仓)。
确定性罗列触达指定行的 commit → 缓存叙事 + Vibe-Decision 面包屑;无 key 也能用。"""
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from vibetrace import blame
from vibetrace.cache import Cache


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


class _Repo:
    def __init__(self):
        self.dir = tempfile.mkdtemp()
        _git(["init", "-q"], self.dir)
        _git(["config", "user.email", "t@t"], self.dir)
        _git(["config", "user.name", "t"], self.dir)
        f = Path(self.dir) / "f.py"
        f.write_text("a\nb\nc\n")
        _git(["add", "f.py"], self.dir)
        _git(["commit", "-q", "-m",
              "c1 初版\n\nVibe-Decision: 用 urllib 不引依赖"], self.dir)
        f.write_text("a\nB2\nc\n")  # 改第 2 行
        _git(["add", "f.py"], self.dir)
        _git(["commit", "-q", "-m", "c2 改第二行\n\nVibe-Watch: 并发待验证"],
             self.dir)

    def sha(self, n):  # n=1 最旧
        out = subprocess.run(["git", "log", "--reverse", "--format=%H"],
                             cwd=self.dir, capture_output=True, text=True)
        return out.stdout.splitlines()[n - 1]

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class TestBlameTarget(unittest.TestCase):
    def test_parse_reuses_ask_format(self):
        self.assertEqual(blame._parse_target("f.py:2-4"), ("f.py", 2, 4))
        self.assertEqual(blame._parse_target("f.py:5"), ("f.py", 5, 5))
        self.assertEqual(blame._parse_target("f.py"), ("f.py", None, None))


class TestBlameSegments(unittest.TestCase):
    def setUp(self):
        self.repo = _Repo()
        self.cache = Cache(":memory:")

    def tearDown(self):
        self.cache.close()
        self.repo.close()

    def test_segments_oldest_first_with_breadcrumbs(self):
        segs = blame.collect_segments(self.cache, self.repo.dir, "f.py", 2, 2)
        self.assertEqual(len(segs), 2)                  # 两次 commit 都动过第 2 行
        self.assertEqual([s["subject"] for s in segs],  # 旧→新
                         ["c1 初版", "c2 改第二行"])
        self.assertEqual(segs[0]["sha"], self.repo.sha(1))
        self.assertIn("用 urllib 不引依赖", segs[0]["decisions"])
        self.assertTrue(segs[0]["date"])               # ISO 日期非空

    def test_cached_narrative_decisions_merge_in(self):
        self.cache.put_narrative(
            self.repo.sha(1), "P", "m",
            {"why": "", "decisions": ["缓存里的决策"], "risks": [],
             "open_loops": []})
        segs = blame.collect_segments(self.cache, self.repo.dir, "f.py", 2, 2)
        self.assertIn("缓存里的决策", segs[0]["decisions"])
        self.assertIn("用 urllib 不引依赖", segs[0]["decisions"])  # 面包屑也在

    def test_no_duplicate_when_cache_already_folded_breadcrumb(self):
        self.cache.put_narrative(
            self.repo.sha(1), "P", "m",
            {"why": "", "decisions": ["用 urllib 不引依赖"], "risks": [],
             "open_loops": []})
        segs = blame.collect_segments(self.cache, self.repo.dir, "f.py", 2, 2)
        self.assertEqual(
            segs[0]["decisions"].count("用 urllib 不引依赖"), 1)

    def test_line_log_failure_falls_back_to_file_log(self):
        # 坏行范围 → 行级失败 → 文件级降级(仍拿到该文件全部 commit)
        segs = blame.collect_segments(self.cache, self.repo.dir, "f.py",
                                      999, 999)
        self.assertEqual(len(segs), 2)


class TestBlameEvidence(unittest.TestCase):
    """blame 在每段决策史后附 evidence 原话(确定性,零 LLM);仅 low 加警示。"""

    def setUp(self):
        self.repo = _Repo()
        self.cache = Cache(":memory:")

    def tearDown(self):
        self.cache.close()
        self.repo.close()

    def _ev(self, sid, source, confidence, prompts, excerpts):
        return {"session_id": sid, "source": source,
                "ts": "2026-06-17T10:00:00+00:00", "confidence": confidence,
                "prompts": prompts, "excerpts": excerpts}

    def test_segment_carries_evidence_from_narrative(self):
        self.cache.put_narrative(
            self.repo.sha(1), "P", "m",
            {"why": "", "decisions": [], "risks": [], "open_loops": [],
             "evidence": [self._ev("highsess1", "claude", "high",
                                   ["原话锚点A"], ["陈述B"])]})
        segs = blame.collect_segments(self.cache, self.repo.dir, "f.py", 2, 2)
        self.assertEqual(segs[0]["evidence"][0]["session_id"], "highsess1")
        self.assertEqual(segs[1].get("evidence"), [])     # 无缓存段为空

    def test_format_lists_evidence_prompts_high(self):
        self.cache.put_narrative(
            self.repo.sha(1), "P", "m",
            {"why": "", "decisions": [], "risks": [], "open_loops": [],
             "evidence": [self._ev("highsess1", "claude", "high",
                                   ["原话锚点A"], ["陈述B"])]})
        segs = blame.collect_segments(self.cache, self.repo.dir, "f.py", 2, 2)
        out = blame._format("f.py", 2, 2, segs)
        self.assertIn("原话佐证", out)
        self.assertIn("原话锚点A", out)
        self.assertIn("陈述B", out)
        self.assertIn("highses", out)             # 短 id
        self.assertNotIn("置信较低", out)          # high → 无警示

    def test_format_low_evidence_warns(self):
        self.cache.put_narrative(
            self.repo.sha(1), "P", "m",
            {"why": "", "decisions": [], "risks": [], "open_loops": [],
             "evidence": [self._ev("lowsess99", "cursor", "low",
                                   ["顺手一问"], [])]})
        segs = blame.collect_segments(self.cache, self.repo.dir, "f.py", 2, 2)
        out = blame._format("f.py", 2, 2, segs)
        self.assertIn("顺手一问", out)
        self.assertIn("置信较低", out)

    def test_old_cache_without_evidence_compatible(self):
        self.cache.put_narrative(
            self.repo.sha(1), "P", "m",
            {"why": "", "decisions": [], "risks": [], "open_loops": []})
        segs = blame.collect_segments(self.cache, self.repo.dir, "f.py", 2, 2)
        self.assertEqual(segs[0]["evidence"], [])     # .get 兼容
        out = blame._format("f.py", 2, 2, segs)
        self.assertNotIn("原话佐证", out)             # 无 evidence 不输出块


class TestBlameRun(unittest.TestCase):
    def setUp(self):
        self.repo = _Repo()

    def tearDown(self):
        self.repo.close()

    def _run(self, target):
        buf = io.StringIO()
        with mock.patch.object(blame, "Cache",
                               lambda _p: Cache(":memory:")), \
             redirect_stdout(buf):
            code = blame.blame(self.repo.dir, target)
        return code, buf.getvalue()

    def test_prints_each_segment_deterministically(self):
        code, out = self._run("f.py:2-2")
        self.assertEqual(code, 0)
        self.assertIn("c1 初版", out)
        self.assertIn("c2 改第二行", out)
        self.assertIn("用 urllib 不引依赖", out)         # 决策面包屑
        self.assertIn(self.repo.sha(1)[:7], out)         # 短 SHA
        # 零 LLM:确定性 → 同输入两次输出完全一致
        _, out2 = self._run("f.py:2-2")
        self.assertEqual(out, out2)

    def test_output_redacts_secret_in_subject(self):
        # subject 来自 git 原始元数据,经 _format → print 出 stdout,须在出口脱敏
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        _git(["init", "-q"], d)
        _git(["config", "user.email", "t@t"], d)
        _git(["config", "user.name", "t"], d)
        (Path(d) / "g.py").write_text("x\n")
        _git(["add", "g.py"], d)
        _git(["commit", "-q", "-m", "leak sk-ABCDEF0123456789ABCD"], d)
        buf = io.StringIO()
        with mock.patch.object(blame, "Cache", lambda _p: Cache(":memory:")), \
             redirect_stdout(buf):
            code = blame.blame(d, "g.py")
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertNotIn("sk-ABCDEF0123456789ABCD", out)
        self.assertIn("[REDACTED]", out)

    def test_json_redacts_quote_delimited_secret(self):
        # 回归守门:JSON 路径必须在 dumps 前脱敏。dumps 转义引号 → 若先 dumps 后
        # redact,key="value" 形式 secret 会因 =\" 漏过定界模式(config.py:102 记录的坑)。
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        _git(["init", "-q"], d)
        _git(["config", "user.email", "t@t"], d)
        _git(["config", "user.name", "t"], d)
        (Path(d) / "h.py").write_text("x\n")
        _git(["add", "h.py"], d)
        _git(["commit", "-q", "-m",
              'init\n\nVibe-Decision: set password="hunter2abcXYZ" in config'], d)
        buf = io.StringIO()
        with mock.patch.object(blame, "Cache", lambda _p: Cache(":memory:")), \
             redirect_stdout(buf):
            code = blame.blame(d, "h.py", json_output=True)
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertNotIn("hunter2abcXYZ", out)             # 原始 secret 不得出现
        self.assertIn("[REDACTED]", out)
        import json as _json
        _json.loads(out)                                   # 仍是合法 JSON

    def test_no_history_returns_error_code(self):
        code, out = self._run("nope.py")
        self.assertEqual(code, 2)

    def test_whole_file_when_no_range(self):
        code, out = self._run("f.py")
        self.assertEqual(code, 0)
        self.assertIn("c1 初版", out)

    def test_json_output_is_valid_json(self):
        buf = io.StringIO()
        with mock.patch.object(blame, "Cache",
                               lambda _p: Cache(":memory:")), \
             redirect_stdout(buf):
            code = blame.blame(self.repo.dir, "f.py:2-2", json_output=True)
        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 1)
        seg = data[0]
        for key in ("sha", "date", "subject", "why", "decisions", "risks"):
            self.assertIn(key, seg, f"missing key: {key}")
        self.assertIsInstance(seg["decisions"], list)


if __name__ == "__main__":
    unittest.main()
