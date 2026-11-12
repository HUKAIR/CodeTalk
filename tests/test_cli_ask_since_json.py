import unittest
from unittest import mock

from codetalk import ask, cli


class TestCliAskSinceJson(unittest.TestCase):
    def test_since_and_json_flags_forwarded(self):
        got = {}

        def fake_ask(project_path, target, question, vault=None,
                     since=None, as_json=False, no_llm=False):
            got.update(p=project_path, t=target, q=question, v=vault,
                       since=since, json=as_json)
            return 0

        with mock.patch.object(ask, "ask", fake_ask):
            rc = cli.main(["ask", "f.py:1-2", "为什么", "--project", ".",
                           "--since", "3 days ago", "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(got["since"], "3 days ago")
        self.assertTrue(got["json"])

    def test_defaults_when_flags_absent(self):
        got = {}

        def fake_ask(project_path, target, question, vault=None,
                     since=None, as_json=False, no_llm=False):
            got.update(since=since, json=as_json)
            return 0

        with mock.patch.object(ask, "ask", fake_ask):
            cli.main(["ask", "f.py", "为什么"])
        self.assertIsNone(got["since"])
        self.assertFalse(got["json"])


if __name__ == "__main__":
    unittest.main()
