"""Public release claims that should not drift away from runtime behavior."""
import unittest
from pathlib import Path

from codetalk.cli import _build_parser


ROOT = Path(__file__).resolve().parent.parent


class TestDockerPrivacyBoundary(unittest.TestCase):
    def test_image_copies_only_runtime_inputs(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertNotIn("COPY . /app", dockerfile)
        self.assertIn("COPY pyproject.toml README.md LICENSE /app/", dockerfile)
        self.assertIn("COPY codetalk /app/codetalk", dockerfile)

    def test_build_context_is_deny_by_default(self):
        dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        self.assertEqual(dockerignore.splitlines()[0], "**")
        self.assertIn("!pyproject.toml", dockerignore)
        self.assertIn("!codetalk/**", dockerignore)


class TestPublicRepositoryBoundary(unittest.TestCase):
    def test_private_workspace_is_ignored_without_revealing_topics(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("/.private/", ignore)
        self.assertNotIn("commercialization-options", ignore)
        self.assertNotIn("keep-first-commercial", ignore)

    def test_public_context_contains_product_language_only(self):
        context = (ROOT / "CONTEXT.md").read_text(encoding="utf-8")
        for marker in (
                "**Design partner**", "**Pilot team**", "**Buying trigger**",
                "**Commercial service**", "**Pilot success**",
                "**Target maintainer**", "**Activation**",
                "**Decision drift**", "**Rationale hallucination**",
                "**Verification claim gap**", "commercial buyer",
                "paid continuation"):
            self.assertNotIn(marker, context)
        for marker in (
                "**Action drift**", "**Deterministic mode**",
                "**Inspectable enrichment**", "**Decision review card**"):
            self.assertIn(marker, context)

    def test_public_product_docs_omit_internal_commercial_notes(self):
        paths = (
            "Dockerfile", "README.md", "README.zh-CN.md", "demo.html",
            "docs/adr/0003-local-review-outcomes-with-explicit-export.md",
            "docs/discovery/interceptions.md",
            "docs/engineering/dogfood-findings.md",
            "docs/release-readiness-review.md",
            "docs/specs/product-polish-release.md",
        )
        text = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in paths)
        for marker in (
                "Self-host for customers", "给客户自托管", "pilot follow-up",
                "carefully scoped pilot use", "five external design partners",
                "Design-partner recruitment", "target maintainer", "外部 pilot",
                "付费墙", "竞品差异/定位/变现等策略内容"):
            self.assertNotIn(marker, text)


class TestPublicCapabilityCopy(unittest.TestCase):
    def test_cli_help_matches_current_surface(self):
        help_text = _build_parser().format_help()
        self.assertIn("六视图", help_text)
        self.assertIn("7 个 codetalk_* 工具", help_text)
        self.assertIn("多 agent 配置文件", help_text)

    def test_readme_defines_all_decision_note_types_without_stale_counts(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Vibe-Rejected", readme)
        self.assertNotIn("114/194", readme)
        self.assertNotIn("101/183", readme)
        self.assertIn("file tree", readme.lower())
        self.assertIn("prompt replay", readme.lower())
        self.assertIn("The core is zero-LLM, local-first", readme)

    def test_agent_seed_side_effects_are_disclosed(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(".cursor/rules/codetalk.mdc", readme)
        self.assertIn(".github/copilot-instructions.md", readme)

    def test_formal_docs_use_real_commands_and_decision_note_terms(self):
        spec = (ROOT / "docs" / "spec-kit-integration.md").read_text(
            encoding="utf-8")
        mcp = (ROOT / "docs" / "mcp-install.md").read_text(encoding="utf-8")
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        self.assertIn('"-m", "codetalk"', spec)
        self.assertNotIn("All three answers are **zero-LLM", spec)
        self.assertIn("只有显式启用 LLM", mcp)
        self.assertNotIn("全程 **stdio 同机直连、数据不出本机**", mcp)
        self.assertNotIn("rm -rf /tmp/vt", mcp)
        self.assertIn("mktemp -d", mcp)
        self.assertIn("Vibe-Rejected", contributing)
        self.assertIn("## Decision Notes", contributing)

    def test_formal_ui_copy_calls_vibe_lines_decision_notes(self):
        console = (ROOT / "codetalk" / "console.html").read_text(encoding="utf-8")
        graph = (ROOT / "codetalk" / "graph.html").read_text(encoding="utf-8")
        web = (ROOT / "codetalk" / "web.py").read_text(encoding="utf-8")
        web_chat = (ROOT / "codetalk" / "web_chat.html").read_text(
            encoding="utf-8")
        self.assertIn('tile_coverage: "Decision-note coverage"', console)
        self.assertIn('tile_coverage: "决策记录覆盖"', console)
        self.assertIn("solid = decision note", graph)
        self.assertIn("实线=决策记录", graph)
        self.assertIn("model calls follow config", web_chat)
        self.assertIn("模型调用按配置", web_chat)
        self.assertNotIn("data stays local", web_chat)
        self.assertNotIn("接地对话 · 数据不出本机", console)
        self.assertIn("本地优先,模型调用按配置", web)
        self.assertNotIn("接地对话 POST /api/chat;数据不出本机", web)

    def test_security_policy_points_to_private_reporting(self):
        security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        self.assertIn(
            "https://github.com/HUKAIR/CodeTalk/security/advisories", security)
        self.assertNotIn("If GitHub private vulnerability reporting", security)


class TestReleaseAutomation(unittest.TestCase):
    def test_ci_covers_current_runtimes_and_builds_installable_artifacts(self):
        workflow = (ROOT / ".github" / "workflows" / "test.yml").read_text(
            encoding="utf-8")
        self.assertIn('"3.14"', workflow)
        self.assertIn('node-version: "24"', workflow)
        self.assertIn("python -m scripts.scan_secrets --history", workflow)
        self.assertIn("codetalk/trust_ab.html", workflow)
        self.assertIn("python -m scripts.build_mcpb", workflow)
        self.assertIn("python -m build", workflow)
        self.assertIn("python -P -m codetalk --version", workflow)
        self.assertIn("npm run package", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertEqual(workflow.count("persist-credentials: false"), 3)
        self.assertIn(
            "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7.0.0",
            workflow)
        self.assertIn(
            "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6.3.0",
            workflow)
        self.assertIn(
            "actions/setup-node@48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e # v6.4.0",
            workflow)
        self.assertIn(
            "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1",
            workflow)
        self.assertNotRegex(workflow, r"uses: actions/[^@\s]+@v\d")

    def test_extension_packager_is_pinned(self):
        package = (ROOT / "vscode-codetalk" / "package.json").read_text(
            encoding="utf-8")
        lock = (ROOT / "vscode-codetalk" / "package-lock.json").read_text(
            encoding="utf-8")
        self.assertIn('"@vscode/vsce": "3.9.2"', package)
        self.assertIn('"node_modules/@vscode/vsce"', lock)
        self.assertIn('"package": "vsce package --no-dependencies"', package)

    def test_python_package_metadata_matches_ci_support(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "test.yml").read_text(
            encoding="utf-8")
        for minor in ("3.11", "3.12", "3.13", "3.14"):
            self.assertIn(f"Programming Language :: Python :: {minor}", pyproject)
        self.assertIn('license = "AGPL-3.0-or-later"', pyproject)
        self.assertIn('test = ["httpx2>=2.0.0"]', pyproject)
        self.assertIn('pip install -e ".[web,test]"', workflow)
        self.assertNotIn("License :: OSI Approved", pyproject)


if __name__ == "__main__":
    unittest.main()
