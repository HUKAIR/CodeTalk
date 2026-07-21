"""Privacy checks for files that leave the release runner."""
import io
import stat
import struct
import tarfile
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_chunk(kind, payload):
    body = kind + payload
    return (struct.pack(">I", len(payload)) + body
            + struct.pack(">I", zlib.crc32(body) & 0xffffffff))


def _png(*chunks):
    return PNG_SIGNATURE + b"".join(
        _png_chunk(kind, payload) for kind, payload in chunks)


class ReleasePrivacyCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_zip_rejects_secret_and_private_build_path(self):
        from scripts.release_privacy import validate_archive
        archive = self.root / "candidate.whl"
        for payload, phrase in (
                (b'key = "sk-releaseprivacy-Fake1234567890"\n', "secret"),
                (b'\x00binary\x00sk-releaseprivacy-Fake1234567890', "secret"),
                (b'path = "/Users/private-owner/CodeTalk"\n', "private path")):
            with self.subTest(phrase=phrase):
                with zipfile.ZipFile(archive, "w") as bundle:
                    bundle.writestr("codetalk/module.py", payload)
                with self.assertRaisesRegex(ValueError, phrase):
                    validate_archive(archive)

    def test_sdist_rejects_secret_shaped_content_even_in_test_paths(self):
        from scripts.release_privacy import validate_archive
        archive = self.root / "candidate.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            payload = b'FAKE = "sk-releaseprivacy-Fake1234567890"\n'
            member = tarfile.TarInfo("codetalk-0.2.0/tests/test_fixture.py")
            member.size = len(payload)
            bundle.addfile(member, io.BytesIO(payload))
        with self.assertRaisesRegex(ValueError, "secret"):
            validate_archive(archive)

    def test_archive_scans_utf16_text_for_private_paths(self):
        from scripts.release_privacy import validate_archive
        archive = self.root / "candidate.vsix"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("extension/data.bin",
                            "/Users/private-owner/project".encode("utf-16-le"))
        with self.assertRaisesRegex(ValueError, "private path"):
            validate_archive(archive)

    def test_archive_rejects_non_ascii_or_dated_member_names(self):
        from scripts.release_privacy import validate_archive
        archive = self.root / "candidate.mcpb"
        for name in ("server/内部.md", "docs/2026-07-21-notes.md"):
            with self.subTest(name=name):
                with zipfile.ZipFile(archive, "w") as bundle:
                    bundle.writestr(name, "public")
                with self.assertRaisesRegex(ValueError, "public filename"):
                    validate_archive(archive)

    def test_zip_rejects_non_regular_unix_members(self):
        from scripts.release_privacy import validate_archive
        archive = self.root / "candidate.whl"
        member = zipfile.ZipInfo("codetalk/unsafe-pipe")
        member.create_system = 3
        member.external_attr = (stat.S_IFIFO | 0o600) << 16
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr(member, b"unsafe")
        with self.assertRaisesRegex(ValueError, "regular"):
            validate_archive(archive)

    def test_zip_rejects_symlink_disguised_as_directory(self):
        from scripts.release_privacy import validate_archive
        archive = self.root / "candidate.whl"
        member = zipfile.ZipInfo("codetalk/link/")
        member.create_system = 3
        member.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr(member, b"")
        with self.assertRaisesRegex(ValueError, "regular"):
            validate_archive(archive)

    def test_png_sanitizer_removes_private_metadata_without_changing_pixels(self):
        from scripts.release_privacy import sanitize_png
        payload = _png(
            (b"IHDR", b"header"),
            (b"eXIf", b"/Users/private-owner"),
            (b"iTXt", b"prompt\x00private"),
            (b"vpAg", b"generator-private-data"),
            (b"IDAT", b"pixel-bytes"),
            (b"IEND", b""),
        )
        cleaned = sanitize_png(payload)
        self.assertNotIn(b"eXIf", cleaned)
        self.assertNotIn(b"iTXt", cleaned)
        self.assertNotIn(b"vpAg", cleaned)
        self.assertIn(_png_chunk(b"IDAT", b"pixel-bytes"), cleaned)

    def test_pages_staging_writes_only_sanitized_allowlisted_files(self):
        from scripts.release_privacy import PRIVATE_PNG_CHUNKS
        from scripts.release_promotion import stage_pages
        image_dir = self.root / "docs" / "images"
        image_dir.mkdir(parents=True)
        (self.root / "index.html").write_text("<h1>CodeTalk</h1>",
                                              encoding="utf-8")
        source = _png(
            (b"IHDR", b"header"), (b"eXIf", b"metadata"),
            (b"IDAT", b"pixels"), (b"IEND", b""),
        )
        (image_dir / "codetalk-logo-banner.png").write_bytes(source)
        destination = self.root / "pages"
        stage_pages(self.root, destination)
        staged = (destination / "docs" / "images" /
                  "codetalk-logo-banner.png").read_bytes()
        self.assertNotEqual(staged, source)
        self.assertTrue(all(kind not in staged for kind in PRIVATE_PNG_CHUNKS))


if __name__ == "__main__":
    unittest.main()
