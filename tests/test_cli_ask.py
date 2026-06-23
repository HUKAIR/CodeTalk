import unittest
from unittest import mock

from vibetrace import ask, cli


class TestCliAsk(unittest.TestCase):
    def test_ask_subcommand_dispatches_args(self):
        got = {}

        def fake_ask(project_path, target, question, vault=None,
                     since=None, as_json=False, no_llm=False):
            got.update(p=project_path, t=target, q=question, v=vault)
            return 0

        with mock.patch.object(ask, "ask", fake_ask):
            rc = cli.main(["ask", "f.py:1-2", "为什么", "--project", ".",
                           "--vault", "/tmp/v"])
        self.assertEqual(rc, 0)
        self.assertEqual(got, {"p": ".", "t": "f.py:1-2", "q": "为什么",
                               "v": "/tmp/v"})


if __name__ == "__main__":
    unittest.main()
