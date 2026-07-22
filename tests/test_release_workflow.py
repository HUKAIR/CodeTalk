"""Static safety contract for the manual 0.3.1 promotion workflow."""
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
TEST_WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
VERSION = "0.3.1"
TAG = "v0.3.1"
ARTIFACTS = (
    "hukair_codetalk-0.3.1-py3-none-any.whl",
    "hukair_codetalk-0.3.1.tar.gz",
    "codetalk-0.3.1.mcpb",
    "vscode-codetalk-0.3.1.vsix",
    "codetalk-0.3.1.sbom.cdx.json",
    "SHA256SUMS",
)
ACTION_PINS = {
    "actions/checkout": "9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0",
    "actions/setup-python": "ece7cb06caefa5fff74198d8649806c4678c61a1",
    "actions/download-artifact": "3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
    "actions/upload-pages-artifact": "fc324d3547104276b827a68afc52ff2a11cc49c9",
    "actions/deploy-pages": "cd2ce8fcbc39b97be8ca5fce6e763baed58fa128",
    "pypa/gh-action-pypi-publish": "ba38be9e461d3875417946c167d0b5f3d385a247",
}


class TestReleaseWorkflow(unittest.TestCase):
    def release_text(self):
        return RELEASE_WORKFLOW.read_text(encoding="utf-8")

    def test_release_is_manual_and_defaults_to_no_publication(self):
        text = self.release_text()
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("\n  push:", text)
        self.assertNotIn("\n  pull_request:", text)
        self.assertRegex(text, r"publish:\s*\n(?:.*\n){0,6}\s+default: false")
        self.assertIn("if: ${{ inputs.publish }}", text)
        self.assertIn("cancel-in-progress: false", text)

    def test_existing_candidate_builder_is_reused_once(self):
        release = self.release_text()
        test = TEST_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_call:", test)
        self.assertIn("codetalk-release-candidate-${{ github.sha }}", test)
        self.assertIn("retention-days: 7", test)
        self.assertIn("uses: ./.github/workflows/test.yml", release)
        self.assertIn("codetalk-release-candidate-${{ github.sha }}", release)
        self.assertNotIn("python -m build", release)
        self.assertNotIn("npm ci", release)

    def test_candidate_is_validated_before_it_leaves_the_builder(self):
        text = TEST_WORKFLOW.read_text(encoding="utf-8")
        validate = text.index("scripts.release_promotion validate-candidate")
        upload = text.index("name: codetalk-release-candidate-${{ github.sha }}")
        self.assertLess(validate, upload)

    def test_public_jobs_use_protected_environments_and_short_lived_identity(self):
        text = self.release_text()
        for environment in ("release", "pypi", "github-pages"):
            self.assertIn(f"name: {environment}", text)
        self.assertIn("id-token: write", text)
        self.assertIn("pages: write", text)
        self.assertIn("contents: write", text)
        self.assertIn("contents: read", text)
        self.assertNotIn("secrets.", text)
        self.assertNotIn("password:", text)
        self.assertNotIn("skip-existing", text)

    def test_preflight_uses_only_github_token_readable_settings(self):
        text = self.release_text()
        preflight = text.split("  preflight:\n", 1)[1].split(
            "\n  draft-release:\n", 1)[0]
        for phrase in (
                TAG, "refs/tags/v0.3.1", "verification.verified",
                "object.type", "github.sha", "build_type", "workflow"):
            self.assertIn(phrase, preflight)
        self.assertNotIn("immutable-releases", preflight)
        self.assertIn('releases/tags/$TAG', text)
        self.assertIn('test "$immutable" = "true"', text)
        self.assertIn("python -m scripts.release_promotion validate-candidate",
                      text)
        self.assertIn("python -m scripts.scan_secrets", text)
        self.assertIn("python -m unittest tests.test_product_proof", text)

    def test_tag_is_revalidated_at_every_irreversible_boundary(self):
        text = self.release_text()
        self.assertGreaterEqual(text.count('git/ref/tags/$TAG'), 4)
        self.assertGreaterEqual(text.count("verification.verified"), 4)
        self.assertGreaterEqual(text.count('= "$GITHUB_SHA"'), 4)

    def test_release_lookup_is_fail_closed_and_public_release_is_recoverable(self):
        text = self.release_text()
        self.assertIn("release-status", text)
        self.assertGreaterEqual(text.count("--paginate --slurp"), 2)
        self.assertGreaterEqual(text.count("select(.tag_name == $tag)"), 2)
        self.assertIn('test "$release_count" = "0" -o "$release_count" = "1"',
                      text)
        self.assertIn('release_state="public"', text)
        self.assertIn('release_state="draft"', text)
        self.assertIn('release_state="missing"', text)
        self.assertIn('test "$immutable" = "true"', text)
        self.assertNotIn("curl --silent", text)
        self.assertNotIn("release view \"$TAG\" --json isDraft,body,assets 2>/dev/null",
                         text)

    def test_release_uses_exact_assets_and_verifies_public_surfaces(self):
        text = self.release_text()
        for name in ARTIFACTS:
            self.assertIn(name, text)
        for phrase in (
                "gh release verify", "gh release verify-asset",
                "pypi-state", "deploy-pages", "verify-public",
                "hukair-codetalk==0.3.1", "doctor", "review --json"):
            self.assertIn(phrase, text)
        self.assertNotIn("gh issue close", text)
        self.assertNotIn("gh repo edit", text)
        self.assertIn("Revalidate Release body and exact assets before publication",
                      text)
        self.assertGreaterEqual(text.count('cmp "dist/$name"'), 2)

    def test_all_external_actions_are_pinned_to_reviewed_commits(self):
        text = self.release_text()
        uses = [line.split("uses:", 1)[1].split("#", 1)[0].strip()
                for line in text.splitlines() if "uses:" in line]
        external = [value for value in uses if not value.startswith("./")]
        self.assertTrue(external)
        self.assertEqual({value.split("@", 1)[0] for value in external},
                         set(ACTION_PINS))
        for value in external:
            with self.subTest(action=value):
                self.assertRegex(value, r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}$")
        for action, sha in ACTION_PINS.items():
            self.assertIn(f"{action}@{sha}", text)

    def test_release_identity_is_not_configurable(self):
        text = self.release_text()
        self.assertIn(f"VERSION: \"{VERSION}\"", text)
        self.assertIn(f"TAG: \"{TAG}\"", text)
        self.assertNotRegex(text, r"inputs:\s*\n(?:.*\n){0,8}\s+(version|tag):")


if __name__ == "__main__":
    unittest.main()
