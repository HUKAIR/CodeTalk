"""The unpublished 0.2.0 release candidate stays internally consistent."""
import gzip
import io
import json
import tarfile
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
VERSION = "0.2.0"


class TestVersionContract(unittest.TestCase):
    def test_python_mcp_and_editor_versions_match(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(
            encoding="utf-8"))["project"]
        manifest = json.loads((ROOT / "manifest.json").read_text(
            encoding="utf-8"))
        extension = json.loads((ROOT / "vscode-codetalk" / "package.json").read_text(
            encoding="utf-8"))
        lock = json.loads((ROOT / "vscode-codetalk" / "package-lock.json").read_text(
            encoding="utf-8"))
        self.assertEqual(project["version"], VERSION)
        self.assertEqual(manifest["version"], VERSION)
        self.assertEqual(extension["version"], VERSION)
        self.assertEqual(lock["version"], VERSION)
        self.assertEqual(lock["packages"][""]["version"], VERSION)
        self.assertEqual(project["dependencies"], [])
        self.assertIn(f'__version__ = "{VERSION}"',
                      (ROOT / "codetalk" / "__init__.py").read_text(
                          encoding="utf-8"))

    def test_release_notes_name_version_and_honest_limitations(self):
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        notes = (ROOT / "docs" / "releases" / "v0.2.0.md").read_text(
            encoding="utf-8")
        self.assertIn("## 0.2.0 - Unreleased", changelog)
        self.assertIn("# CodeTalk 0.2.0 Release Candidate", notes)
        for phrase in (
                "cold-start evidence gaps", "human semantic judgment",
                "provider retention", "unofficial local session formats"):
            self.assertIn(phrase, notes)
        self.assertIn("not been published", notes)

    def test_user_facing_bundle_examples_are_versioned(self):
        for name in ("README.md", "README.zh-CN.md", "docs/mcp-install.md",
                     "RELEASE_CHECKLIST.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("codetalk-0.2.0.mcpb", text, name)

    def test_ci_assembles_and_validates_the_complete_candidate(self):
        workflow = (ROOT / ".github" / "workflows" / "test.yml").read_text(
            encoding="utf-8")
        for phrase in (
                "SOURCE_DATE_EPOCH", "npm ci", "npm run package",
                "dist/vscode-codetalk-0.2.0.vsix",
                "python -m scripts.release_artifacts dist",
                "sha256sum -c SHA256SUMS"):
            self.assertIn(phrase, workflow)


class TestReleaseMetadata(unittest.TestCase):
    def test_sdist_uses_root_pkg_info_when_egg_info_copy_also_exists(self):
        from scripts.release_artifacts import root_sdist_metadata
        names = {
            "codetalk-0.2.0/PKG-INFO",
            "codetalk-0.2.0/codetalk.egg-info/PKG-INFO",
        }
        self.assertEqual(root_sdist_metadata(names, VERSION),
                         "codetalk-0.2.0/PKG-INFO")

    def test_expected_primary_artifacts_are_explicit(self):
        from scripts.release_artifacts import expected_artifact_names
        self.assertEqual(expected_artifact_names(VERSION), (
            "codetalk-0.2.0-py3-none-any.whl",
            "codetalk-0.2.0.tar.gz",
            "codetalk-0.2.0.mcpb",
            "vscode-codetalk-0.2.0.vsix",
        ))

    def test_sbom_is_cyclonedx_and_covers_every_primary_artifact(self):
        from scripts.release_artifacts import render_sbom
        records = [
            {"name": name, "sha256": str(index) * 64, "size": index}
            for index, name in enumerate((
                "codetalk-0.2.0-py3-none-any.whl",
                "codetalk-0.2.0.tar.gz",
                "codetalk-0.2.0.mcpb",
                "vscode-codetalk-0.2.0.vsix",
            ), start=1)
        ]
        sbom = render_sbom(VERSION, records)
        self.assertEqual(sbom["bomFormat"], "CycloneDX")
        self.assertEqual(sbom["specVersion"], "1.6")
        self.assertEqual(sbom["metadata"]["component"]["version"], VERSION)
        self.assertEqual({item["name"] for item in sbom["components"]},
                         {item["name"] for item in records})
        self.assertTrue(all(item["hashes"][0]["alg"] == "SHA-256"
                            for item in sbom["components"]))

    def test_sdist_normalization_removes_build_time_drift(self):
        from scripts.release_artifacts import normalized_sdist_bytes

        def sample(timestamp):
            output = io.BytesIO()
            with gzip.GzipFile(fileobj=output, mode="wb", mtime=timestamp) as gz:
                with tarfile.open(fileobj=gz, mode="w") as archive:
                    payload = b"same source"
                    member = tarfile.TarInfo("codetalk-0.2.0/example.txt")
                    member.size = len(payload)
                    member.mtime = timestamp
                    archive.addfile(member, io.BytesIO(payload))
            return output.getvalue()

        first = normalized_sdist_bytes(sample(100), 42)
        second = normalized_sdist_bytes(sample(200), 42)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
