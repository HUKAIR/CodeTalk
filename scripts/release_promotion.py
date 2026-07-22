"""Fail-closed checks used by the manual release promotion workflow."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.release_artifacts import (
    PYPI_DISTRIBUTION,
    SBOM_NAME,
    VERSION,
    expected_artifact_names,
    python_artifact_names,
    validate_artifacts,
)
from scripts.release_privacy import (sanitize_png, validate_release_privacy,
                                     validate_staged_pages)


TAG = f"v{VERSION}"
CHECKSUMS = "SHA256SUMS"
PAGES_FILES = (
    Path("index.html"),
    Path("docs/images/codetalk-logo-banner.png"),
)
PYPI_JSON_URL = f"https://pypi.org/pypi/{PYPI_DISTRIBUTION}/{VERSION}/json"


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_release_files():
    return expected_artifact_names() + (SBOM_NAME, CHECKSUMS)


def _exact_regular_files(directory, expected):
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError(f"release directory is missing: {directory}")
    entries = tuple(sorted(path.name for path in directory.iterdir()))
    if entries != tuple(sorted(expected)):
        raise ValueError("unexpected release files: " + ", ".join(entries))
    if any(path.is_symlink() or not path.is_file()
           for path in directory.iterdir()):
        raise ValueError("release entries must be regular files")


def _checksum_records(directory):
    directory = Path(directory)
    expected = set(expected_release_files()) - {CHECKSUMS}
    records = {}
    try:
        lines = (directory / CHECKSUMS).read_text(
            encoding="ascii").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"checksum manifest is unreadable: {exc}") from exc
    for line in lines:
        digest, separator, name = line.partition("  ")
        flat_name = Path(name).name == name and "/" not in name and "\\" not in name
        valid = (separator == "  " and len(digest) == 64
                 and all(char in "0123456789abcdef" for char in digest)
                 and flat_name and name not in records)
        if not valid:
            raise ValueError("checksum manifest is malformed or duplicated")
        records[name] = digest
    if set(records) != expected:
        raise ValueError("checksum manifest does not cover the exact release set")
    for name, digest in records.items():
        if _sha256(directory / name) != digest:
            raise ValueError(f"checksum mismatch: {name}")
    return records


def _validate_sbom(directory, records):
    path = Path(directory) / SBOM_NAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"SBOM is unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("SBOM must be a JSON object")
    metadata = payload.get("metadata")
    component = metadata.get("component") if isinstance(metadata, dict) else None
    if (payload.get("bomFormat") != "CycloneDX"
            or payload.get("specVersion") != "1.6"
            or not isinstance(component, dict)
            or component.get("name") != PYPI_DISTRIBUTION
            or component.get("version") != VERSION):
        raise ValueError("SBOM identity does not match the release")
    components = payload.get("components")
    if not isinstance(components, list):
        raise ValueError("SBOM components are missing")
    found = {}
    for component in components:
        if not isinstance(component, dict):
            raise ValueError("SBOM component is malformed")
        name = component.get("name")
        hashes = component.get("hashes")
        if name in found or not isinstance(hashes, list):
            raise ValueError("SBOM components are malformed or duplicated")
        sha256 = [item.get("content") for item in hashes
                  if isinstance(item, dict) and item.get("alg") == "SHA-256"]
        if len(sha256) != 1:
            raise ValueError(f"SBOM SHA-256 is missing or duplicated: {name}")
        found[name] = sha256[0]
    expected = set(expected_artifact_names())
    if set(found) != expected:
        raise ValueError("SBOM does not cover the exact primary artifacts")
    for name, digest in found.items():
        if records.get(name) != digest:
            raise ValueError(f"SBOM checksum mismatch: {name}")


def _validate_release_notes(path):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"release notes are unreadable: {exc}") from exc
    rejected = ("Release Candidate", "not been published", "Unreleased")
    if not text.startswith(f"# CodeTalk {VERSION}\n") or any(
            phrase in text for phrase in rejected):
        raise ValueError("release notes still contain prepublication status")


def validate_candidate(directory, notes_path):
    directory = Path(directory)
    _exact_regular_files(directory, expected_release_files())
    validate_artifacts(directory)
    records = _checksum_records(directory)
    _validate_sbom(directory, records)
    _validate_release_notes(notes_path)
    validate_release_privacy(
        directory, notes_path, expected_artifact_names(), SBOM_NAME)


def _regular_source(repository, relative):
    current = repository
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Pages source must be a regular file: {relative}")
    if not current.is_file():
        raise ValueError(f"Pages source must be a regular file: {relative}")
    return current


def stage_pages(repository, destination):
    repository = Path(repository)
    destination = Path(destination)
    if destination.exists() and (not destination.is_dir()
                                 or any(destination.iterdir())):
        raise ValueError("Pages destination must be absent or empty")
    destination.mkdir(parents=True, exist_ok=True)
    staged = []
    for relative in PAGES_FILES:
        source = _regular_source(repository, relative)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() == ".png":
            target.write_bytes(sanitize_png(source.read_bytes()))
        else:
            shutil.copyfile(source, target)
        staged.append(target)
    validate_staged_pages(destination, PAGES_FILES)
    return tuple(staged)


def pypi_state(directory, payload):
    directory = Path(directory)
    names = python_artifact_names()
    for name in names:
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"PyPI source file is missing: {name}")
    if payload is None:
        return "publish"
    urls = payload.get("urls") if isinstance(payload, dict) else None
    if not isinstance(urls, list):
        raise ValueError("PyPI response has no release files")
    records = {}
    for item in urls:
        if not isinstance(item, dict):
            raise ValueError("PyPI release file is malformed")
        name = item.get("filename")
        digests = item.get("digests")
        digest = digests.get("sha256") if isinstance(digests, dict) else None
        if name in records or not isinstance(name, str) or not isinstance(digest, str):
            raise ValueError("PyPI release files are malformed or duplicated")
        records[name] = digest
    if set(records) != set(names):
        raise ValueError("PyPI release does not contain the exact Python artifacts")
    for name, digest in records.items():
        if _sha256(directory / name) != digest:
            raise ValueError(f"PyPI checksum mismatch: {name}")
    return "verified"


def _fetch_pypi_payload():
    request = Request(PYPI_JSON_URL, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise ValueError(f"PyPI returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"PyPI response could not be verified: {exc}") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-candidate")
    validate.add_argument("directory")
    validate.add_argument("notes")
    pages = subparsers.add_parser("stage-pages")
    pages.add_argument("repository")
    pages.add_argument("destination")
    pypi = subparsers.add_parser("pypi-state")
    pypi.add_argument("directory")
    args = parser.parse_args(argv)
    try:
        if args.command == "validate-candidate":
            validate_candidate(args.directory, args.notes)
            print("release candidate verified")
        elif args.command == "stage-pages":
            for path in stage_pages(args.repository, args.destination):
                print(path)
        else:
            print(pypi_state(args.directory, _fetch_pypi_payload()))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
