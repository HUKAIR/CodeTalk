import unittest
from unittest import mock

from codetalk import cli, commands, mcp_server


class TestCliMcpServe(unittest.TestCase):
    def test_mcp_serve_dispatches_to_run(self):
        got = {}
        with mock.patch.object(mcp_server, "run",
                               lambda project=None: got.update(p=project)):
            rc = cli.main(["mcp-serve", "--project", "/tmp/proj"])
        self.assertEqual(rc, 0)
        self.assertEqual(got, {"p": "/tmp/proj"})

    def test_mcp_serve_default_project(self):
        got = {}
        with mock.patch.object(mcp_server, "run",
                               lambda project=None: got.update(p=project)):
            rc = cli.main(["mcp-serve"])
        self.assertEqual(rc, 0)
        self.assertEqual(got["p"], ".")


if __name__ == "__main__":
    unittest.main()
