import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vibetrace import cli, config


def _run(argv):
    with contextlib.redirect_stdout(io.StringIO()):
        return cli.main(argv)


class TestInit(unittest.TestCase):
    def test_init_writes_template(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sub" / "config.json"  # 父目录不存在,init 应自建
            with mock.patch.object(config, "CONFIG_PATH", p):
                rc = _run(["init"])
            self.assertEqual(rc, 0)
            self.assertTrue(p.exists())
            cfg = json.loads(p.read_text(encoding="utf-8"))
            self.assertIn("provider", cfg)
            self.assertIn("providers", cfg)

    def test_init_no_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            p.write_text('{"keep": 1}', encoding="utf-8")
            with mock.patch.object(config, "CONFIG_PATH", p):
                rc = _run(["init"])
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(p.read_text()), {"keep": 1})

    def test_init_force_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            p.write_text('{"keep": 1}', encoding="utf-8")
            with mock.patch.object(config, "CONFIG_PATH", p):
                _run(["init", "--force"])
            self.assertNotEqual(json.loads(p.read_text()), {"keep": 1})


if __name__ == "__main__":
    unittest.main()
