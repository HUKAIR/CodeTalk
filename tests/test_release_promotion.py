"""Safety contracts for preparing and promoting release artifacts."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


VERSION = "0.2.0"
PRIMARY = (
    "codetalk-0.2.0-py3-none-any.whl",
    "codetalk-0.2.0.tar.gz",
    "codetalk-0.2.0.mcpb",
    "vscode-codetalk-0.2.0.vsix",
)
SBOM = "codetalk-0.2.0.sbom.cdx.json"


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PromotionCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.dist = self.root / "dist"
        self.dist.mkdir()
        self.notes = self.root / "notes.md"
        self.notes.write_text("# CodeTalk 0.2.0\n\nKnown limitations.\n",
                              encoding="utf-8")
        self.privacy_patch = mock.patch(
            "scripts.release_promotion.validate_release_privacy")
        self.privacy = self.privacy_patch.start()
        self.addCleanup(self.privacy_patch.stop)

    def tearDown(self):
        self.temp.cleanup()

    def make_candidate(self):
        for name in PRIMARY:
            (self.dist / name).write_bytes(f"artifact:{name}".encode())
        components = [{
            "type": "file",
            "name": name,
            "hashes": [{"alg": "SHA-256",
                        "content": _sha256(self.dist / name)}],
        } for name in PRIMARY]
        (self.dist / SBOM).write_text(json.dumps({
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "metadata": {"component": {
                "type": "application", "name": "codetalk",
                "version": VERSION,
            }},
            "components": components,
        }) + "\n", encoding="utf-8")
        checksummed = (*PRIMARY, SBOM)
        (self.dist / "SHA256SUMS").write_text("".join(
            f"{_sha256(self.dist / name)}  {name}\n" for name in checksummed),
            encoding="ascii")

    @mock.patch("scripts.release_promotion.validate_artifacts")
    def test_valid_candidate_has_exact_files_hashes_and_sbom(self, validate):
        from scripts.release_promotion import validate_candidate
        self.make_candidate()
        validate_candidate(self.dist, self.notes)
        validate.assert_called_once_with(self.dist)
        self.privacy.assert_called_once_with(self.dist, self.notes, PRIMARY)

    @mock.patch("scripts.release_promotion.validate_artifacts")
    def test_candidate_rejects_unexpected_files(self, validate):
        from scripts.release_promotion import validate_candidate
        self.make_candidate()
        (self.dist / "private.txt").write_text("no", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unexpected release files"):
            validate_candidate(self.dist, self.notes)

    @mock.patch("scripts.release_promotion.validate_artifacts")
    def test_candidate_rejects_missing_files(self, validate):
        from scripts.release_promotion import validate_candidate
        self.make_candidate()
        missing = self.dist / PRIMARY[0]
        missing.rename(self.root / PRIMARY[0])
        with self.assertRaisesRegex(ValueError, "unexpected release files"):
            validate_candidate(self.dist, self.notes)

    @mock.patch("scripts.release_promotion.validate_artifacts")
    def test_candidate_rejects_bad_checksum_manifest(self, validate):
        from scripts.release_promotion import validate_candidate
        self.make_candidate()
        sums = self.dist / "SHA256SUMS"
        sums.write_text(sums.read_text(encoding="ascii").replace(
            _sha256(self.dist / PRIMARY[0]), "0" * 64, 1), encoding="ascii")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            validate_candidate(self.dist, self.notes)

    @mock.patch("scripts.release_promotion.validate_artifacts")
    def test_candidate_rejects_nested_or_duplicate_checksum_names(self, validate):
        from scripts.release_promotion import validate_candidate
        self.make_candidate()
        sums = self.dist / "SHA256SUMS"
        line = sums.read_text(encoding="ascii").splitlines()[0]
        sums.write_text(line + "\n" + line + "\n", encoding="ascii")
        with self.assertRaisesRegex(ValueError, "checksum manifest"):
            validate_candidate(self.dist, self.notes)

    @mock.patch("scripts.release_promotion.validate_artifacts")
    def test_candidate_rejects_sbom_drift(self, validate):
        from scripts.release_promotion import validate_candidate
        self.make_candidate()
        payload = json.loads((self.dist / SBOM).read_text(encoding="utf-8"))
        payload["components"][0]["hashes"][0]["content"] = "f" * 64
        (self.dist / SBOM).write_text(json.dumps(payload) + "\n",
                                     encoding="utf-8")
        sums = self.dist / "SHA256SUMS"
        lines = [line for line in sums.read_text(encoding="ascii").splitlines()
                 if not line.endswith("  " + SBOM)]
        lines.append(f"{_sha256(self.dist / SBOM)}  {SBOM}")
        sums.write_text("\n".join(lines) + "\n", encoding="ascii")
        with self.assertRaisesRegex(ValueError, "SBOM"):
            validate_candidate(self.dist, self.notes)

    @mock.patch("scripts.release_promotion.validate_artifacts")
    def test_candidate_rejects_non_object_sbom(self, validate):
        from scripts.release_promotion import validate_candidate
        self.make_candidate()
        (self.dist / SBOM).write_text("[]\n", encoding="utf-8")
        sums = self.dist / "SHA256SUMS"
        lines = [line for line in sums.read_text(encoding="ascii").splitlines()
                 if not line.endswith("  " + SBOM)]
        lines.append(f"{_sha256(self.dist / SBOM)}  {SBOM}")
        sums.write_text("\n".join(lines) + "\n", encoding="ascii")
        with self.assertRaisesRegex(ValueError, "SBOM"):
            validate_candidate(self.dist, self.notes)

    @mock.patch("scripts.release_promotion.validate_artifacts")
    def test_candidate_rejects_prepublication_notes(self, validate):
        from scripts.release_promotion import validate_candidate
        self.make_candidate()
        for phrase in ("Release Candidate", "not been published", "Unreleased"):
            with self.subTest(phrase=phrase):
                self.notes.write_text(f"# CodeTalk 0.2.0 {phrase}\n",
                                      encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "release notes"):
                    validate_candidate(self.dist, self.notes)

    def test_pages_staging_uses_only_regular_allowlisted_files(self):
        from scripts.release_promotion import PAGES_FILES, stage_pages
        image = self.root / "docs" / "images"
        image.mkdir(parents=True)
        (self.root / "index.html").write_text("<h1>CodeTalk</h1>",
                                              encoding="utf-8")
        logo = (Path(__file__).resolve().parent.parent / "docs" / "images" /
                "codetalk-logo-banner.png")
        (image / "codetalk-logo-banner.png").write_bytes(logo.read_bytes())
        (self.root / "private.txt").write_text("private", encoding="utf-8")
        staged = stage_pages(self.root, self.root / "pages")
        self.assertEqual(tuple(path.relative_to(self.root / "pages")
                               for path in staged), PAGES_FILES)
        found = {path.relative_to(self.root / "pages")
                 for path in (self.root / "pages").rglob("*") if path.is_file()}
        self.assertEqual(found, set(PAGES_FILES))

    def test_pages_staging_rejects_symlink(self):
        from scripts.release_promotion import stage_pages
        image = self.root / "docs" / "images"
        image.mkdir(parents=True)
        target = self.root / "real.html"
        target.write_text("real", encoding="utf-8")
        (self.root / "index.html").symlink_to(target)
        (image / "codetalk-logo-banner.png").write_bytes(b"png")
        with self.assertRaisesRegex(ValueError, "regular file"):
            stage_pages(self.root, self.root / "pages")

    def test_pages_staging_rejects_nonempty_destination(self):
        from scripts.release_promotion import stage_pages
        image = self.root / "docs" / "images"
        image.mkdir(parents=True)
        (self.root / "index.html").write_text("ok", encoding="utf-8")
        (image / "codetalk-logo-banner.png").write_bytes(b"png")
        destination = self.root / "pages"
        destination.mkdir()
        (destination / "old.txt").write_text("old", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "destination"):
            stage_pages(self.root, destination)

    def test_pypi_state_requires_exact_public_hashes(self):
        from scripts.release_promotion import pypi_state
        for name in PRIMARY[:2]:
            (self.dist / name).write_bytes(f"artifact:{name}".encode())
        payload = {"urls": [{
            "filename": name,
            "digests": {"sha256": _sha256(self.dist / name)},
        } for name in PRIMARY[:2]]}
        self.assertEqual(pypi_state(self.dist, None), "publish")
        self.assertEqual(pypi_state(self.dist, payload), "verified")
        payload["urls"][0]["digests"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "PyPI"):
            pypi_state(self.dist, payload)

    def test_pypi_state_rejects_partial_or_extra_release(self):
        from scripts.release_promotion import pypi_state
        for name in PRIMARY[:2]:
            (self.dist / name).write_bytes(name.encode())
        expected = [{"filename": name,
                     "digests": {"sha256": _sha256(self.dist / name)}}
                    for name in PRIMARY[:2]]
        for urls in (expected[:1], expected + [{
                "filename": "extra.whl", "digests": {"sha256": "0" * 64}}]):
            with self.subTest(urls=urls):
                with self.assertRaisesRegex(ValueError, "PyPI"):
                    pypi_state(self.dist, {"urls": urls})

    def test_pypi_state_rejects_malformed_digest_object(self):
        from scripts.release_promotion import pypi_state
        for name in PRIMARY[:2]:
            (self.dist / name).write_bytes(name.encode())
        payload = {"urls": [
            {"filename": PRIMARY[0], "digests": None},
            {"filename": PRIMARY[1], "digests": {}},
        ]}
        with self.assertRaisesRegex(ValueError, "PyPI"):
            pypi_state(self.dist, payload)


if __name__ == "__main__":
    unittest.main()
