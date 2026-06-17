import contextlib
import io
import unittest
from unittest import mock

from vibetrace import cli, graph


class TestCliGraph(unittest.TestCase):
    def test_graph_subcommand_dispatches(self):
        got = {}

        def fake_build(project_path, vault=None):
            got.update(p=project_path, v=vault)
            return ("/tmp/x-graph.html", None)

        with mock.patch.object(graph, "build_graph", fake_build), \
                contextlib.redirect_stdout(io.StringIO()):
            rc = cli.main(["graph", "--project", ".", "--vault", "/tmp/v"])
        self.assertEqual(rc, 0)
        self.assertEqual(got, {"p": ".", "v": "/tmp/v"})


if __name__ == "__main__":
    unittest.main()
