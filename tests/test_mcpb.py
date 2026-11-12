"""MCP Bundle(.mcpb)打包:manifest schema 合规 + 构建产物是含纯 stdlib server 源的合法 zip。

.mcpb = zip(manifest.json + server/<纯 stdlib 源>)。一键装覆盖所有 MCP 客户端;
靠用户已装 python3 运行、不打包解释器(codetalk 零三方依赖,见 pyproject dependencies=[])。
"""
import json
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestManifest(unittest.TestCase):
    def _manifest(self):
        return json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))

    def test_required_fields(self):
        m = self._manifest()
        self.assertEqual(m["manifest_version"], "0.3")
        for k in ("name", "version", "description"):
            self.assertTrue(m.get(k))
        self.assertEqual(m["license"], "AGPL-3.0-or-later")
        self.assertIn("代码决策溯源", m["description"])
        self.assertTrue(m["author"]["name"])
        srv = m["server"]
        self.assertEqual(srv["type"], "python")
        self.assertEqual(srv["mcp_config"]["command"], "python3")
        # 经 __main__ → cli 分发起 mcp-serve;PYTHONPATH 指向 bundle 内 server
        self.assertIn("mcp-serve", srv["mcp_config"]["args"])
        self.assertIn("${__dirname}/server", srv["mcp_config"]["env"]["PYTHONPATH"])
        # project 经 user_config 注入(不写死路径)
        self.assertIn("${user_config.project}", srv["mcp_config"]["args"])
        self.assertEqual(m["user_config"]["project"]["type"], "directory")

    def test_lists_seven_tools(self):
        names = {t["name"] for t in self._manifest().get("tools", [])}
        self.assertEqual(names, {"codetalk_ask", "codetalk_blame",
                                 "codetalk_graph", "codetalk_search",
                                 "codetalk_drift", "codetalk_prompts",
                                 "codetalk_adr"})

    def test_manifest_tools_match_runtime_source(self):
        # 单一真源:manifest 工具集必须 == 运行时真正 serve 的 mcp_tools.TOOLS。
        # 防 manifest/docs 陈旧事故复发(本会话发生两次:加工具忘同步 manifest)。
        from codetalk.mcp_tools import TOOLS
        manifest_names = {t["name"] for t in self._manifest().get("tools", [])}
        runtime_names = {t["name"] for t in TOOLS}
        self.assertEqual(manifest_names, runtime_names)


class TestReleaseMetadata(unittest.TestCase):
    def test_pyproject_has_public_release_metadata(self):
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        project = data["project"]
        self.assertEqual(project["name"], "hukair-codetalk")
        self.assertEqual(project["license"], "AGPL-3.0-or-later")
        self.assertEqual(project["scripts"]["codetalk"], "codetalk.cli:main")
        self.assertIn("Repository", project["urls"])
        self.assertIn("code-provenance", project["keywords"])


class TestBuild(unittest.TestCase):
    def test_build_produces_valid_bundle(self):
        from scripts.build_mcpb import build
        with tempfile.TemporaryDirectory() as d:
            out = build(Path(d) / "codetalk.mcpb")
            self.assertTrue(out.exists())
            with zipfile.ZipFile(out) as z:
                names = z.namelist()
                self.assertIn("manifest.json", names)
                self.assertIn("LICENSE", names)
                self.assertIn("GNU AFFERO GENERAL PUBLIC LICENSE",
                              z.read("LICENSE").decode("utf-8"))
                self.assertIn("server/codetalk/mcp_server.py", names)
                self.assertIn("server/codetalk/__main__.py", names)
                self.assertIn("server/codetalk/__init__.py", names)
                # 纯净:不带缓存/字节码/测试
                self.assertFalse(any("__pycache__" in n or n.endswith(".pyc")
                                     or n.startswith("server/tests") for n in names))
                json.loads(z.read("manifest.json"))   # bundle 内 manifest 可解析


if __name__ == "__main__":
    unittest.main()
