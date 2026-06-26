import contextlib
import io
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from vibetrace import cli, console
from vibetrace.cache import Cache


def _git(a, c):
    subprocess.run(["git", *a], cwd=c, check=True, capture_output=True, text=True)


def _sha(c):
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=c, check=True,
                          capture_output=True, text=True).stdout.strip()


class TestConsoleAssemble(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)
        _git(["init", "-q"], self.d)
        _git(["config", "user.email", "t@t"], self.d)
        _git(["config", "user.name", "t"], self.d)
        f = Path(self.d) / "a.py"
        f.write_text("1\n"); _git(["add", "."], self.d)
        _git(["commit", "-q", "-m", "c1"], self.d)
        f.write_text("2\n"); _git(["add", "."], self.d)
        _git(["commit", "-q", "-m", "c2"], self.d)
        self.sha2 = _sha(self.d)
        self.pkey = str(Path(self.d).resolve())
        self.cache = Cache(":memory:")
        self.cache.put_narrative(self.sha2, self.pkey, "m",
                                 {"what": "做了 X", "why": "因为 Y",
                                  "decisions": ["选 A"], "risks": ["风险 R"],
                                  "open_loops": []})
        self.cache.put_daily(self.pkey, "2026-06-20", "今日概览", "今日决定")

    def test_assemble_includes_tree(self):
        data, err = console._assemble(self.d, self.cache)
        self.assertIsNone(err)
        self.assertEqual(set(data),
                         {"overview", "timeline", "graph", "debt", "tree"})
        self.assertIn("nodes", data["tree"])
        self.assertIn("grounding", data["tree"])
        self.assertEqual(data["tree"]["nodes"]["type"], "dir")

    def test_assemble_empty_repo_no_crash(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        _git(["init", "-q"], d)
        data, err = console._assemble(d, Cache(":memory:"))
        self.assertIsNone(err)
        self.assertEqual(data["timeline"], [])


class TestConsoleBuildHtml(unittest.TestCase):
    def test_renders_views_and_redacts(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        _git(["init", "-q"], d)
        _git(["config", "user.email", "t@t"], d)
        _git(["config", "user.name", "t"], d)
        (Path(d) / "a.py").write_text("1\n"); _git(["add", "."], d)
        _git(["commit", "-q", "-m", "c1"], d)
        sha = _sha(d)
        dbfile = str(Path(d) / "cache.db")
        c = Cache(dbfile)
        c.put_narrative(sha, str(Path(d).resolve()), "m",
                        {"what": "key sk-abcdef0123456789ABCDEF 别泄漏", "why": "y",
                         "decisions": [], "risks": [], "open_loops": []})
        c.close()
        with mock.patch.object(console, "CACHE_DB_PATH", dbfile):
            html, project, err = console._build_html(d, serve=False)
        self.assertIsNone(err)
        self.assertIn("控制台", html)
        self.assertIn("时光轴", html)
        self.assertNotIn("$data", html)          # 模板已替换
        self.assertIn("[REDACTED]", html)        # 脱敏生效
        self.assertNotIn("sk-abcdef0123456789ABCDEF", html)

    def test_build_html_redacts_quoted_keyvalue_in_subject(self):
        # key="value" 形式:inline_json 转义引号后,只靠整页 redact 会漏 → redact_data 须先脱敏
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        _git(["init", "-q"], d)
        _git(["config", "user.email", "t@t"], d)
        _git(["config", "user.name", "t"], d)
        (Path(d) / "a.py").write_text("1\n"); _git(["add", "."], d)
        _git(["commit", "-q", "-m", 'set token="ZxCvB12345Mn" ZZMARKER'], d)
        dbfile = str(Path(d) / "cache.db")
        with mock.patch.object(console, "CACHE_DB_PATH", dbfile):
            html, project, err = console._build_html(d, serve=False)
        self.assertIsNone(err)
        self.assertIn("ZZMARKER", html)            # subject 确已渲染
        self.assertNotIn("ZxCvB12345Mn", html)     # 引号定界 secret 不漏


class TestConsoleThemeAndMotion(unittest.TestCase):
    def setUp(self):
        self.html = (Path(console.__file__).parent / "console.html").read_text(
            encoding="utf-8")

    def test_light_theme_toggle_present(self):
        self.assertIn('data-theme="light"', self.html)   # 浅色覆盖块
        self.assertIn("themebtn", self.html)             # 切换按钮
        self.assertIn("prefers-color-scheme", self.html)  # 跟随系统默认

    def test_motion_with_reduced_motion_guard(self):
        self.assertIn("@keyframes", self.html)
        self.assertIn("prefers-reduced-motion", self.html)  # 尊重无障碍偏好

    def test_timeline_scroll_reveal_scoped(self):
        self.assertIn("@keyframes rowReveal", self.html)             # 揭示帧
        self.assertIn("animation-timeline: view()", self.html)      # 滚动驱动
        self.assertIn("#v-timeline.on .row", self.html)             # 作用域收口,非裸 .row
        self.assertIn("tlArm", self.html)                           # 懒挂载 IO 回落
        self.assertNotIn("setupTimelineReveal", self.html)          # 旧的 init 即挂已移除


class TestAccessibilityAndReanswer(unittest.TestCase):
    """任务9:键盘/读屏可达 + 改答 + tunnel res.ok 确认写回。"""

    def setUp(self):
        base = Path(console.__file__).parent
        self.console = (base / "console.html").read_text(encoding="utf-8")
        self.tunnel = (base / "tunnel.html").read_text(encoding="utf-8")

    # ---- (a) 无障碍 ----
    def test_console_clickable_rows_keyboard_accessible(self):
        # 行展开 .head:可聚焦 + 键盘语义 + aria 状态
        self.assertIn('role="button"', self.console)
        self.assertIn('tabindex="0"', self.console)
        self.assertIn('aria-expanded', self.console)
        self.assertIn('aria-controls', self.console)
        # 键盘激活:Enter/Space
        self.assertIn("keydown", self.console)

    def test_tunnel_clickable_rows_keyboard_accessible(self):
        self.assertIn('role="button"', self.tunnel)
        self.assertIn('tabindex="0"', self.tunnel)
        self.assertIn('aria-expanded', self.tunnel)
        self.assertIn('aria-controls', self.tunnel)
        self.assertIn("keydown", self.tunnel)

    def test_keydown_handles_enter_and_space(self):
        # Enter 与 Space(" ")都要激活,且阻止 Space 滚屏
        for html in (self.console, self.tunnel):
            self.assertIn('"Enter"', html)
            self.assertIn('" "', html)
            self.assertIn("preventDefault", html)

    # ---- (b) 改答 ----
    def test_console_offers_reanswer_link(self):
        self.assertIn("改答", self.console)

    def test_tunnel_offers_reanswer_link(self):
        self.assertIn("改答", self.tunnel)

    # ---- (c) tunnel res.ok 确认写回(不再乐观更新)----
    def test_tunnel_post_returns_promise_and_checks_ok(self):
        # post 不再 fire-and-forget:返回 Promise 且校验 r.ok
        self.assertIn("return r.ok", self.tunnel)
        self.assertIn("Promise.resolve", self.tunnel)
        # 旧的乐观更新注释/路径已移除
        self.assertNotIn("乐观更新", self.tunnel)

    def test_tunnel_capsule_write_handles_failure(self):
        self.assertIn("写回失败", self.tunnel)


class TestConsoleChatEmbed(unittest.TestCase):
    """P0a 去 silo:vibetrace web 服务时 console 内嵌接地对话 dock;静态/只读不挂。"""

    def _repo(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        _git(["init", "-q"], d)
        _git(["config", "user.email", "t@t"], d)
        _git(["config", "user.name", "t"], d)
        (Path(d) / "a.py").write_text("1\n"); _git(["add", "."], d)
        _git(["commit", "-q", "-m", "c1"], d)
        return str(Path(d) / "cache.db"), d

    def test_chat_off_by_default(self):
        dbfile, d = self._repo()
        with mock.patch.object(console, "CACHE_DB_PATH", dbfile):
            html, _p, err = console._build_html(d, serve=False)
        self.assertIsNone(err)
        self.assertIn("var CHAT = false", html)        # 静态/只读 → 不挂 chat、不发请求

    def test_chat_on_embeds_grounded_dock(self):
        dbfile, d = self._repo()
        with mock.patch.object(console, "CACHE_DB_PATH", dbfile):
            html, _p, err = console._build_html(d, serve=True, chat=True)
        self.assertIsNone(err)
        self.assertIn("var CHAT = true", html)         # vibetrace web → chat 启用
        self.assertIn('id="chatdock"', html)           # 内嵌 dock
        self.assertIn("/api/chat/stream", html)        # 流式接地对话端点(同源)
        self.assertIn("接地追问这段", html)            # 链 A:时光轴行内原地追问
        self.assertIn("接地追问这个决策", html)         # 链 A:决策图节点原地追问
        self.assertIn("s.title =", html)               # hover 预览真实原话(GitLens 范式)
        self.assertIn('src.type === "pr"', html)       # 引用 PR 可点击跳真源


class TestFiletreeAssemble(unittest.TestCase):
    def test_file_grounding_bounded_and_synthesizes_sources(self):
        commits = [
            {"sha": "a" * 40, "subject": "改 a", "date": datetime(2026, 6, 1),
             "files": ["a.py"]},
            {"sha": "b" * 40, "subject": "改 b", "date": datetime(2026, 6, 2),
             "files": ["b.py"]},
        ]
        narratives = {"a" * 40: {"decisions": ["选 X"]}, "b" * 40: None}
        out = console._file_grounding(["a.py"], commits, narratives)
        self.assertEqual([e["path"] for e in out], ["a.py"])     # 仅变更文件,有界
        row = out[0]["commits"][0]
        self.assertEqual(row["sha"], "a" * 7)
        self.assertEqual(row["decisions"], ["选 X"])
        self.assertEqual(row["sources"], [{"type": "commit", "sha": "a" * 7}])

    def test_assemble_tracked_files_none_no_crash(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        _git(["init", "-q"], d)
        _git(["config", "user.email", "t@t"], d)
        _git(["config", "user.name", "t"], d)
        (Path(d) / "a.py").write_text("1\n"); _git(["add", "."], d)
        _git(["commit", "-q", "-m", "c1"], d)
        with mock.patch.object(console, "tracked_files", return_value=None):
            data, err = console._assemble(d, Cache(":memory:"))
        self.assertIsNone(err)
        self.assertIn("tree", data)                              # None 守卫:不崩


class TestConsoleCLI(unittest.TestCase):
    def test_console_dispatches_render(self):
        called = {}

        def fake_render(pp):
            called["pp"] = pp
            return Path("/x/c.html"), None

        with mock.patch("vibetrace.console.render_console", fake_render), \
             contextlib.redirect_stdout(io.StringIO()):
            rc = cli.main(["console", "--project", "."])
        self.assertEqual(rc, 0)
        self.assertTrue(called)


if __name__ == "__main__":
    unittest.main()
