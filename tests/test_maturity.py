"""成熟化大改动集的回归测试(发布级阻断 + 红线 + 健壮性)。"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vibetrace import course
from vibetrace.cache import Cache
from vibetrace.llm import LLMError


def _git(a, c):
    subprocess.run(["git", *a], cwd=c, check=True, capture_output=True, text=True)


def _repo(*subjects):
    d = tempfile.mkdtemp()
    _git(["init", "-q"], d)
    _git(["config", "user.email", "t@t"], d)
    _git(["config", "user.name", "t"], d)
    for i, s in enumerate(subjects or ["c1"]):
        (Path(d) / "a.py").write_text(f"{i}\n")
        _git(["add", "."], d)
        _git(["commit", "-q", "-m", s], d)
    return d


class TestCapsuleIdExposed(unittest.TestCase):
    """console 概览胶囊回答需真 capsule_id,否则多风险胶囊静默丢答(§2 高)。"""

    def test_pending_capsules_returns_capsule_id(self):
        c = Cache(":memory:")
        pkey = "/proj"
        c.seal_capsule(pkey, "abc1234", 0, "风险0", "2026-01-01", "2026-01-01")
        c.seal_capsule(pkey, "abc1234", 1, "风险1", "2026-01-01", "2026-01-01")
        c.open_due_capsules(pkey, "2026-02-01")
        pend = c.pending_capsules(pkey)
        self.assertEqual(len(pend), 2)
        ids = sorted(p["capsule_id"] for p in pend)
        self.assertEqual(ids, ["abc1234:0", "abc1234:1"])  # 两枚各自可寻址


class TestPutNarrativeRedacts(unittest.TestCase):
    """落盘前脱敏对缓存存储这一面失守(§3.2 红线):put_narrative 入口统一脱敏。"""

    def test_narrative_secret_redacted_at_entry(self):
        c = Cache(":memory:")
        c.put_narrative("sha1", "/proj", "m",
                        {"what": "key sk_live_0123456789abcdefghijABCD 别泄漏",
                         "why": "y", "decisions": [], "risks": [], "open_loops": []})
        got = c.get_narrative("sha1")
        self.assertNotIn("sk_live_0123456789abcdefghijABCD", got["what"])
        self.assertIn("[REDACTED]", got["what"])


class TestCacheWAL(unittest.TestCase):
    """并发(webserve 回写 vs digest 写库)消除 database is locked(§3.4)。"""

    def test_wal_enabled_on_file_db(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        c = Cache(str(Path(d) / "cache.db"))
        mode = c.conn.execute("PRAGMA journal_mode").fetchone()[0]
        c.close()
        self.assertEqual(mode.lower(), "wal")


class TestNoExternalResources(unittest.TestCase):
    """数据不出本机(§3.2 红线):模板 HTML 不得加载任何外部资源(CDN 字体/脚本)。"""

    def test_html_templates_self_contained(self):
        import re
        d = Path(course.__file__).parent
        bad = []
        for f in sorted(d.glob("*.html")):
            t = f.read_text(encoding="utf-8")
            bad += [f"{f.name}: {m}" for m in
                    re.findall(r'(?:href|src)\s*=\s*["\']https?://[^"\']+', t)]
        self.assertEqual(bad, [], "外部资源引用违反本地优先红线")


class TestCourseSmoke(unittest.TestCase):
    """course 在任意非空仓曾无条件 TypeError 崩溃(§3.2 发布级阻断)。"""

    def test_build_course_degrades_without_crash(self):
        d = _repo("feat: 一", "fix: 二")
        vault = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        self.addCleanup(shutil.rmtree, vault, ignore_errors=True)
        dbfile = str(Path(d) / "cache.db")
        cfg = {"vault_path": vault}
        with mock.patch.object(course, "CACHE_DB_PATH", dbfile), \
             mock.patch.object(course, "load_config", lambda: cfg), \
             mock.patch.object(course, "LLMClient",
                               side_effect=LLMError("no key")):
            out, err = course.build_course(d)
        self.assertIsNone(err)               # 不再崩溃 / 不再逃逸异常
        self.assertTrue(out.exists())        # 降级也产出课程
        self.assertIn("course", out.name)


if __name__ == "__main__":
    unittest.main()
