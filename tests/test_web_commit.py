"""web /api/commit/<sha>:点 SHA 看真实 commit(零 LLM 本地 git show)。
SHA 严格校验防 git 参数注入;出口脱敏;缺失→404。"""
import unittest
import warnings
from unittest import mock

from fastapi.testclient import TestClient

from codetalk import web


def _client():
    return TestClient(web.app, base_url="http://127.0.0.1")


def _get(path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return _client().get(path)


class TestApiCommit(unittest.TestCase):
    def test_valid_sha_returns_commit(self):
        with mock.patch.object(web.gitlog, "commit_meta",
                               return_value=("2026-07-02T10:00:00", "feat: x")), \
             mock.patch.object(web.gitlog, "commit_body", return_value="Vibe-Decision: y"), \
             mock.patch.object(web.gitlog, "commit_diff", return_value="+code"):
            r = _get("/api/commit/a1b2c3d")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["subject"], "feat: x")
        self.assertIn("Vibe-Decision", d["body"])
        self.assertIn("+code", d["diff"])

    def test_bad_sha_rejected(self):
        # 非 hex / 过短 / leading-dash(git 参数注入)一律 400,不触 git
        # (含 '/' 的输入不会命中 {sha} 单段路由,属另一层,不在此断言)
        for bad in ["-x", "--help", "xyz", "abc", "a1b2c3d;rm", "g1b2c3d"]:
            r = _get("/api/commit/" + bad)
            self.assertEqual(r.status_code, 400, bad)

    def test_dash_flag_never_reaches_git(self):
        called = {"n": 0}

        def spy(*a, **k):
            called["n"] += 1
            return ("", "")

        with mock.patch.object(web.gitlog, "commit_meta", side_effect=spy):
            r = _get("/api/commit/--output=x")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(called["n"], 0)    # 校验先行,git 从不被调用

    def test_missing_commit_404(self):
        with mock.patch.object(web.gitlog, "commit_meta", return_value=("", "")), \
             mock.patch.object(web.gitlog, "commit_body", return_value=""), \
             mock.patch.object(web.gitlog, "commit_diff", return_value=""):
            r = _get("/api/commit/deadbee")
        self.assertEqual(r.status_code, 404)

    def test_output_redacted(self):
        with mock.patch.object(web.gitlog, "commit_meta", return_value=("d", "s")), \
             mock.patch.object(web.gitlog, "commit_body",
                               return_value="key sk-abcdef0123456789ABCDEF here"), \
             mock.patch.object(web.gitlog, "commit_diff", return_value="clean"):
            r = _get("/api/commit/a1b2c3d")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("sk-abcdef0123456789ABCDEF", r.text)
        self.assertIn("[REDACTED]", r.text)


if __name__ == "__main__":
    unittest.main()
