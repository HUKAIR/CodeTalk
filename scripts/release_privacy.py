"""Fail-closed privacy checks for release archives and the Pages payload."""
import re
import stat
import struct
import tarfile
import zipfile
import zlib
from pathlib import Path, PurePosixPath

from scripts.scan_secrets import scan_text


MAX_MEMBER_BYTES = 10_000_000
MAX_ARCHIVE_BYTES = 100_000_000
PRIVATE_PATH_MARKERS = (
    "/Users/",
    "/home/runner/work/",
    "/private/var/folders/",
    "C:\\Users\\",
    "file:///Users/",
)
PRIVATE_PNG_CHUNKS = (b"eXIf", b"iTXt", b"tEXt", b"zTXt", b"tIME")
PUBLIC_PNG_CHUNKS = {
    b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS",
    b"sRGB", b"gAMA", b"cHRM", b"pHYs", b"bKGD", b"sBIT",
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_DATED_NAME = re.compile(r"(?:^|/)20\d{2}-\d{2}-\d{2}[^/]*")
_DATED_DOC_REFERENCE = re.compile(
    r"(?:docs|\.agents|\.codex)/[^\s\"'<>]*20\d{2}-\d{2}-\d{2}[^\s\"'<>]*")


def _safe_member_name(name):
    try:
        name.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(f"archive has a prohibited public filename: {name}") from exc
    path = PurePosixPath(name)
    invalid = (not name or name.startswith("/") or "\\" in name or "\0" in name
               or ".." in path.parts or _DATED_NAME.search(name))
    if invalid:
        raise ValueError(f"archive has a prohibited public filename: {name}")


def _logical_path(name):
    parts = PurePosixPath(name).parts
    if parts and re.fullmatch(r"codetalk-\d+\.\d+\.\d+", parts[0]):
        parts = parts[1:]
    return "/".join(parts)


def _scan_payload(payload, archive_name, member_name):
    if len(payload) > MAX_MEMBER_BYTES:
        raise ValueError(f"archive member is too large to inspect: {member_name}")
    logical = _logical_path(member_name)
    views = [payload.decode("utf-8", "replace")]
    if b"\0" in payload:
        for encoding in ("utf-16-le", "utf-16-be"):
            try:
                views.append(payload.decode(encoding))
            except UnicodeDecodeError:
                pass
    for text in views:
        findings = scan_text(text, f"artifact:{archive_name}", logical,
                             ignore_fixtures=False)
        if findings:
            kinds = ", ".join(sorted({item["kind"] for item in findings}))
            raise ValueError(
                f"secret-shaped content in {archive_name}:{logical} ({kinds})")
        if any(marker in text for marker in PRIVATE_PATH_MARKERS):
            raise ValueError(f"private path in {archive_name}:{logical}")
        if _DATED_DOC_REFERENCE.search(text):
            raise ValueError(
                f"dated internal document reference in {archive_name}:{logical}")


def _validate_zip(path):
    total = 0
    seen = set()
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            _safe_member_name(member.filename)
            if member.filename in seen:
                raise ValueError(f"archive member is duplicated: {member.filename}")
            seen.add(member.filename)
            mode = member.external_attr >> 16
            member_type = stat.S_IFMT(mode)
            if member.is_dir():
                if member_type and not stat.S_ISDIR(mode):
                    raise ValueError(
                        f"archive member must be regular or a directory: "
                        f"{member.filename}")
                continue
            if member_type and not stat.S_ISREG(mode):
                raise ValueError(f"archive member must be regular: {member.filename}")
            total += member.file_size
            if total > MAX_ARCHIVE_BYTES:
                raise ValueError("archive is too large to inspect")
            _scan_payload(archive.read(member), path.name, member.filename)


def _validate_tar(path):
    total = 0
    seen = set()
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            _safe_member_name(member.name)
            if member.name in seen:
                raise ValueError(f"archive member is duplicated: {member.name}")
            seen.add(member.name)
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError(f"archive member must be regular: {member.name}")
            total += member.size
            if total > MAX_ARCHIVE_BYTES:
                raise ValueError("archive is too large to inspect")
            handle = archive.extractfile(member)
            if handle is None:
                raise ValueError(f"archive member is unreadable: {member.name}")
            _scan_payload(handle.read(MAX_MEMBER_BYTES + 1), path.name, member.name)


def validate_archive(path):
    path = Path(path)
    try:
        if path.name.endswith(".tar.gz"):
            _validate_tar(path)
        else:
            _validate_zip(path)
    except (OSError, tarfile.TarError, zipfile.BadZipFile, RuntimeError) as exc:
        raise ValueError(f"release archive is unreadable: {path.name}: {exc}") from exc


def validate_public_text(path):
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"public text is unreadable: {path.name}: {exc}") from exc
    _scan_payload(text.encode("utf-8"), "public", path.name)


def validate_release_privacy(directory, notes_path, artifact_names):
    directory = Path(directory)
    for name in artifact_names:
        validate_archive(directory / name)
    for name in ("SHA256SUMS", "codetalk-0.2.1.sbom.cdx.json"):
        validate_public_text(directory / name)
    validate_public_text(notes_path)


def sanitize_png(payload):
    if not payload.startswith(PNG_SIGNATURE):
        raise ValueError("Pages image is not a PNG")
    output = bytearray(PNG_SIGNATURE)
    offset = len(PNG_SIGNATURE)
    seen_ihdr = seen_iend = False
    while offset < len(payload):
        if len(payload) - offset < 12:
            raise ValueError("Pages PNG is truncated")
        size = struct.unpack(">I", payload[offset:offset + 4])[0]
        end = offset + 12 + size
        if end > len(payload):
            raise ValueError("Pages PNG chunk is truncated")
        kind = payload[offset + 4:offset + 8]
        chunk_payload = payload[offset + 8:offset + 8 + size]
        if len(kind) != 4 or not all(
                ord("A") <= byte <= ord("Z") or ord("a") <= byte <= ord("z")
                for byte in kind):
            raise ValueError("Pages PNG chunk type is invalid")
        expected_crc = struct.unpack(">I", payload[end - 4:end])[0]
        if zlib.crc32(kind + chunk_payload) & 0xffffffff != expected_crc:
            raise ValueError("Pages PNG chunk checksum is invalid")
        if kind == b"IHDR":
            seen_ihdr = True
        if kind == b"IEND":
            seen_iend = True
        if kind not in PUBLIC_PNG_CHUNKS and not (kind[0] & 0x20):
            raise ValueError("Pages PNG has an unknown critical chunk")
        if kind in PUBLIC_PNG_CHUNKS:
            output.extend(payload[offset:end])
        offset = end
        if kind == b"IEND":
            break
    if not seen_ihdr or not seen_iend or offset != len(payload):
        raise ValueError("Pages PNG structure is invalid")
    return bytes(output)


def validate_staged_pages(destination, relative_files):
    destination = Path(destination)
    expected = set(relative_files)
    found = {path.relative_to(destination) for path in destination.rglob("*")
             if path.is_file() or path.is_symlink()}
    if found != expected:
        raise ValueError("Pages payload does not match the exact allowlist")
    for relative in relative_files:
        path = destination / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Pages payload must be regular: {relative}")
    validate_public_text(destination / "index.html")
    image = destination / "docs" / "images" / "codetalk-logo-banner.png"
    payload = image.read_bytes()
    if sanitize_png(payload) != payload:
        raise ValueError("Pages PNG still contains private metadata")
