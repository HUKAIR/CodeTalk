"""指令回看(prompts_view + prompts 命令):零-LLM,按会话时间线列用户指令 + 改过的
文件;commit 关联仅作「软对齐」弱提示,绝不冒充因果。复用 sessions/align,不出网。"""
import io
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from vibetrace import align
from vibetrace.prompts_view import build_prompts_view


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _sess(**kw):
    base = {"session_id": "s1", "title": "加个回看视图", "source": "claude",
            "start": datetime(2026, 6, 23, 14, 2, tzinfo=timezone.utc),
            "end": datetime(2026, 6, 23, 15, 30, tzinfo=timezone.utc),
            "prompts": ["帮我加指令回看", "按会话分组"],
            "files_written": set()}
    base.update(kw)
    return base


class TestPromptsView(unittest.TestCase):
    def test_lists_prompts_title_and_day(self):
        out = build_prompts_view([_sess()], [], Path("/proj"))
        self.assertIn("帮我加指令回看", out)
        self.assertIn("按会话分组", out)
        self.assertIn("加个回看视图", out)
        self.assertIn("2026-06-23", out)
        self.assertIn("[claude]", out)

    def test_no_prompts_friendly_no_crash(self):
        out = build_prompts_view([_sess(prompts=[])], [], Path("/proj"))
        self.assertIn("没有抓到指令", out)

    def test_files_relativized_no_absolute_leak(self):
        s = _sess(files_written={"/proj/vibetrace/cli.py", "/home/secret/外部.py"})
        out = build_prompts_view([s], [], Path("/proj"))
        self.assertIn("vibetrace/cli.py", out)          # 仓内 → 相对路径
        self.assertNotIn("/home/secret/外部.py", out)   # 仓外 → 不泄露绝对路径
        self.assertIn("外部.py", out)                   # 仓外 → 只留文件名

    def test_commit_link_soft_labeled_never_committed(self):
        s = _sess(files_written={"/proj/a.py"})
        commit = {"sha": "abc1234def567", "subject": "feat: a",
                  "date": datetime(2026, 6, 23, 14, 30, tzinfo=timezone.utc),
                  "files": ["a.py"]}
        align.align([commit], [s], Path("/proj"))       # 真跑软对齐
        out = build_prompts_view([s], [commit], Path("/proj"))
        self.assertIn("abc1234", out)                   # 软对齐到的 commit
        self.assertIn("软对齐", out)                    # 必须诚实标注
        self.assertNotIn("已提交", out)                 # 绝不冒充因果
        self.assertNotIn("✓", out)

    def test_prompt_secret_redacted(self):
        s = _sess(prompts=["用 sk-ABCDEF0123456789ABCD 调试"])
        out = build_prompts_view([s], [], Path("/proj"))
        self.assertNotIn("sk-ABCDEF0123456789ABCD", out)
        self.assertIn("[REDACTED]", out)


class TestPromptsCmd(unittest.TestCase):
    def test_cmd_runs_zero_llm_no_crash(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        _git(["init", "-q"], d)
        _git(["config", "user.email", "t@t"], d)
        _git(["config", "user.name", "t"], d)
        (Path(d) / "a.py").write_text("x\n")
        _git(["add", "."], d)
        _git(["commit", "-q", "-m", "init"], d)
        from vibetrace import cli
        buf = io.StringIO()
        with mock.patch.object(cli, "CACHE_DB_PATH", str(Path(d) / "cache.db")), \
             redirect_stdout(buf):
            code = cli.main(["prompts", "--project", d])
        self.assertEqual(code, 0)            # 无会话 → 友好降级,不崩


if __name__ == "__main__":
    unittest.main()
