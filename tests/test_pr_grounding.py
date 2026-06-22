"""PR 讨论作 why 接地源(用户1 最强 why 源,问卷一 Q3「看 PR 描述找需求背景」)。
gh 是 CLI 子进程(像 git),不引 Python 依赖;默认关(opt-in);容错降级绝不崩;
落盘前 redact;v1 只取 PR 标题+描述。全程 mock,不依赖真实网络/gh。"""
import argparse
import json
import subprocess
import unittest
from datetime import datetime, timezone
from unittest import mock

from vibetrace import ask, blame, digest, enrich, gitlog
from vibetrace.cache import Cache


# ----- (a) pr_discussion 解析 + (b) 容错降级 ------------------------------

_PR_JSON = json.dumps([{
    "number": 42, "html_url": "https://github.com/o/r/pull/42",
    "title": "加 PR 接地", "body": "需求背景:用户1 想看 PR 描述找设计动机。"}])


class TestPrDiscussion(unittest.TestCase):
    def test_parses_first_pr(self):
        ok = subprocess.CompletedProcess([], 0, stdout=_PR_JSON, stderr="")
        with mock.patch.object(subprocess, "run", return_value=ok):
            pr = gitlog.pr_discussion("/proj", "deadbeef")
        self.assertEqual(pr["number"], 42)
        self.assertEqual(pr["url"], "https://github.com/o/r/pull/42")
        self.assertEqual(pr["title"], "加 PR 接地")
        self.assertIn("需求背景", pr["body"])

    def test_gh_missing_returns_none(self):
        with mock.patch.object(subprocess, "run",
                               side_effect=FileNotFoundError()):
            self.assertIsNone(gitlog.pr_discussion("/proj", "x"))

    def test_nonzero_exit_returns_none(self):
        bad = subprocess.CompletedProcess([], 1, stdout="", stderr="boom")
        with mock.patch.object(subprocess, "run", return_value=bad):
            self.assertIsNone(gitlog.pr_discussion("/proj", "x"))

    def test_timeout_returns_none(self):
        with mock.patch.object(
                subprocess, "run",
                side_effect=subprocess.TimeoutExpired("gh", 15)):
            self.assertIsNone(gitlog.pr_discussion("/proj", "x"))

    def test_empty_list_returns_none(self):
        ok = subprocess.CompletedProcess([], 0, stdout="[]", stderr="")
        with mock.patch.object(subprocess, "run", return_value=ok):
            self.assertIsNone(gitlog.pr_discussion("/proj", "x"))

    def test_bad_json_returns_none(self):
        ok = subprocess.CompletedProcess([], 0, stdout="not json", stderr="")
        with mock.patch.object(subprocess, "run", return_value=ok):
            self.assertIsNone(gitlog.pr_discussion("/proj", "x"))


# ----- (c) enrich_commits(with_pr=...) 接线 -------------------------------

class _FakeLLM:
    model = "fake"

    def narrate(self, prompt, *a, **k):
        return {"what": "w", "why": "y", "decisions": [],
                "risks": [], "open_loops": []}


def _commit():
    return {"sha": "c" * 40, "author": "x", "subject": "s", "body": "",
            "date": datetime(2026, 6, 21, tzinfo=timezone.utc),
            "stat": "", "diff_excerpt": "", "files": [], "matches": []}


class TestPrRefsHelper(unittest.TestCase):
    def test_pr_refs_builds_and_redacts(self):
        pr = {"number": 7, "url": "u", "title": "标题 token=sk-abcdefghijklmnop1234",
              "body": "正文 sk-abcdefghijklmnop1234 " + "x" * 500}
        with mock.patch.object(enrich, "pr_discussion", lambda p, s: pr):
            refs = enrich._pr_refs({"sha": "z"}, "/proj")
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["number"], 7)
        self.assertNotIn("sk-abcdefghijklmnop1234", refs[0]["title"])
        self.assertNotIn("sk-abcdefghijklmnop1234", refs[0]["snippet"])
        self.assertLessEqual(len(refs[0]["snippet"]), 400)

    def test_pr_refs_none_returns_empty(self):
        with mock.patch.object(enrich, "pr_discussion", lambda p, s: None):
            self.assertEqual(enrich._pr_refs({"sha": "z"}, "/proj"), [])


class TestEnrichWithPr(unittest.TestCase):
    def test_with_pr_true_populates_pr_refs(self):
        pr = {"number": 9, "url": "u", "title": "t", "body": "b"}
        cache = Cache(":memory:")
        with mock.patch.object(enrich, "pr_discussion", lambda p, s: pr):
            enrich.enrich_commits([_commit()], _FakeLLM(), cache, "P",
                                  with_pr=True)
        narr = cache.get_narrative("c" * 40)
        self.assertEqual(narr["pr_refs"][0]["number"], 9)

    def test_with_pr_false_no_pr_refs(self):
        cache = Cache(":memory:")
        called = {"n": 0}

        def spy(p, s):
            called["n"] += 1
            return {"number": 1, "url": "u", "title": "t", "body": "b"}

        with mock.patch.object(enrich, "pr_discussion", spy):
            enrich.enrich_commits([_commit()], _FakeLLM(), cache, "P")
        narr = cache.get_narrative("c" * 40)
        self.assertEqual(narr.get("pr_refs") or [], [])
        self.assertEqual(called["n"], 0)            # with_pr=False → 不查


# ----- (d) ask/blame 展示 --------------------------------------------------

class TestAskPrDisplay(unittest.TestCase):
    REF = [{"number": 42, "url": "u", "title": "加 PR 接地",
            "snippet": "需求背景:找设计动机"}]

    def test_format_pr_refs(self):
        block = ask.format_pr_refs(self.REF)
        self.assertIn("PR 讨论", block)
        self.assertIn("#42", block)
        self.assertIn("加 PR 接地", block)
        self.assertIn("需求背景", block)

    def test_format_pr_refs_empty(self):
        self.assertEqual(ask.format_pr_refs([]), "")

    def test_with_evidence_appends_pr_refs(self):
        out = ask._with_evidence("答案", [], (), self.REF)
        self.assertIn("答案", out)
        self.assertIn("#42", out)


class TestBlamePrDisplay(unittest.TestCase):
    def test_emit_pr_refs(self):
        lines = []
        blame._emit_pr_refs(lines, [{"number": 5, "url": "u", "title": "标题",
                                     "snippet": "片段"}])
        joined = "\n".join(lines)
        self.assertIn("PR 讨论", joined)
        self.assertIn("#5", joined)
        self.assertIn("标题", joined)

    def test_emit_pr_refs_empty_noop(self):
        lines = []
        blame._emit_pr_refs(lines, [])
        self.assertEqual(lines, [])


# ----- _retrieve 6 元组契约(汇总 + 去重) ---------------------------------

class TestRetrievePrRefs(unittest.TestCase):
    def test_collects_and_dedupes_by_number(self):
        cache = Cache(":memory:")
        cache.put_narrative("shaaaa11", "P", "m",
                            {"why": "", "decisions": [], "risks": [],
                             "open_loops": [],
                             "pr_refs": [{"number": 3, "url": "u", "title": "T",
                                          "snippet": "s"}]})
        cache.put_narrative("shabbb22", "P", "m",
                            {"why": "", "decisions": [], "risks": [],
                             "open_loops": [],
                             "pr_refs": [{"number": 3, "url": "u", "title": "T",
                                          "snippet": "s"}]})
        with mock.patch.object(ask, "line_log",
                               lambda *a, **k: (["shaaaa11", "shabbb22"], None)), \
             mock.patch.object(ask, "commit_body", lambda p, s: ""):
            res = ask._retrieve(".", "f.py", 1, 5, cache)
        self.assertEqual(len(res), 6)            # 契约扩到 6 元组
        pr_refs = res[5]
        self.assertEqual(len(pr_refs), 1)        # 按 number 去重
        self.assertEqual(pr_refs[0]["number"], 3)


# ----- (e) digest with_pr 解析(args 或 config sources 含 pr) -------------

class TestDigestWithPrResolve(unittest.TestCase):
    def _with_pr(self, cfg, args):
        return bool(getattr(args, "with_pr", False)) or (
            "pr" in (cfg.get("sources") or []))

    def test_off_by_default(self):
        args = argparse.Namespace(with_pr=False)
        self.assertFalse(self._with_pr({"sources": ["claude"]}, args))

    def test_cli_flag_enables(self):
        args = argparse.Namespace(with_pr=True)
        self.assertTrue(self._with_pr({"sources": ["claude"]}, args))

    def test_config_sources_pr_enables(self):
        args = argparse.Namespace(with_pr=False)
        self.assertTrue(self._with_pr({"sources": ["claude", "pr"]}, args))


if __name__ == "__main__":
    unittest.main()
