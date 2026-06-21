import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vibetrace.gitlog import collect_commit_files


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


class TestCollectCommitFilesBody(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)
        _git(["init", "-q"], self.d)
        _git(["config", "user.email", "t@t"], self.d)
        _git(["config", "user.name", "t"], self.d)

    def _commit(self, fname, content, msg):
        p = Path(self.d) / fname
        p.write_text(content)
        _git(["add", "."], self.d)
        _git(["commit", "-q", "-m", msg], self.d)

    def test_body_returned_in_batch(self):
        self._commit("a.py", "v1\n",
                     "subjectA\n\nVibe-Decision: 选了方案X\n多行正文")
        commits, err = collect_commit_files(self.d)
        self.assertIsNone(err)
        self.assertEqual(len(commits), 1)
        self.assertIn("Vibe-Decision: 选了方案X", commits[0]["body"])
        self.assertIn("多行正文", commits[0]["body"])

    def test_empty_body_is_empty_string(self):
        self._commit("a.py", "v1\n", "no body subject")
        commits, _ = collect_commit_files(self.d)
        self.assertEqual(commits[0]["body"], "")

    def test_files_still_parsed_with_body(self):
        self._commit("a.py", "v1\n", "s\n\nbody line")
        self._commit("b.py", "v1\n", "s2\n\nbody2")
        commits, _ = collect_commit_files(self.d)
        self.assertEqual(commits[0]["files"], ["a.py"])
        self.assertEqual(commits[1]["files"], ["b.py"])
        self.assertEqual(commits[1]["body"], "body2")


class TestBriefGraphUseBatchBody(unittest.TestCase):
    """迁移后:brief/graph 不再逐 commit 跑 git show(commit_body),改用批量 body。"""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)
        _git(["init", "-q"], self.d)
        _git(["config", "user.email", "t@t"], self.d)
        _git(["config", "user.name", "t"], self.d)
        p = Path(self.d) / "a.py"
        p.write_text("v1\n")
        _git(["add", "."], self.d)
        _git(["commit", "-q", "-m", "s\n\nVibe-Decision: D1"], self.d)

    def _second_commit(self):
        p = Path(self.d) / "b.py"
        p.write_text("v1\n")
        _git(["add", "."], self.d)
        _git(["commit", "-q", "-m", "s2\n\nVibe-Decision: D2"], self.d)

    def test_brief_coverage_single_batch_git_call(self):
        # 迁移后:覆盖率只跑一次批量 git log,不再为每个 commit 额外 git show
        self._second_commit()
        from vibetrace import brief, gitlog
        calls = []
        real_git = gitlog._git

        def counting_git(args, cwd):
            calls.append(args)
            return real_git(args, cwd)

        with mock.patch.object(gitlog, "_git", counting_git):
            got = brief._breadcrumb_coverage(self.d)
        self.assertEqual(got, (2, 2))
        self.assertEqual(len(calls), 1, f"应只一次批量 git log,实跑 {calls}")

    def test_graph_assemble_no_git_subprocess(self):
        # 迁移后:_assemble 用批量 commits 的 body,完全不再起 git 子进程
        self._second_commit()
        from vibetrace import gitlog, graph
        from vibetrace.cache import Cache
        from vibetrace.gitlog import collect_commit_files
        commits, _ = collect_commit_files(self.d)
        cache = Cache(":memory:")
        with mock.patch.object(gitlog, "_git",
                               side_effect=AssertionError("_assemble 起了 git 子进程,未迁移")):
            out = graph._assemble(commits, self.d, "proj", cache)
        self.assertIn("nodes", out)


if __name__ == "__main__":
    unittest.main()
