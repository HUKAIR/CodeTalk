"""cli search 子命令 dispatch 测试:vibetrace search <question> [--project] → topic_search。"""
import unittest
from unittest import mock

from vibetrace import cli, commands


class TestCliSearch(unittest.TestCase):
    def test_search_subcommand_dispatches_args(self):
        got = {}

        def fake_topic_search(cache, project_path, question):
            got.update(p=str(project_path), q=question)
            return "结果"

        with mock.patch.object(commands, "topic_search", fake_topic_search):
            rc = cli.main(["search", "乐观锁", "--project", "."])
        self.assertEqual(rc, 0)
        self.assertEqual(got["q"], "乐观锁")
        self.assertTrue(got["p"].startswith("/"))   # --project 解析为绝对路径

    def test_search_default_project(self):
        with mock.patch.object(commands, "topic_search",
                               lambda c, p, q: "结果"):
            rc = cli.main(["search", "幂等去重"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
