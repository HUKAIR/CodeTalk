"""Validate an unpublished release candidate and write hashes plus an SBOM."""
import argparse
import copy
import gzip
import hashlib
import io
import json
import os
import tarfile
import uuid
import zipfile
from email.parser import BytesParser
from pathlib import Path


VERSION = "0.2.1"
SBOM_NAME = f"codetalk-{VERSION}.sbom.cdx.json"


def expected_artifact_names(version=VERSION):
    return (
        f"codetalk-{version}-py3-none-any.whl",
        f"codetalk-{version}.tar.gz",
        f"codetalk-{version}.mcpb",
        f"vscode-codetalk-{version}.vsix",
    )


def python_artifact_names(version=VERSION):
    wheel, sdist, _, _ = expected_artifact_names(version)
    return wheel, sdist


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_records(directory, version=VERSION):
    directory = Path(directory)
    paths = [directory / name for name in expected_artifact_names(version)]
    missing = [path.name for path in paths if not path.is_file()]
    if missing:
        raise ValueError("missing release artifacts: " + ", ".join(missing))
    return [{"name": path.name, "sha256": _sha256(path),
             "size": path.stat().st_size} for path in paths]


def normalized_sdist_bytes(payload, epoch):
    """Return a byte-stable gzip/tar stream with canonical archive metadata."""
    source_buffer = io.BytesIO(payload)
    output = io.BytesIO()
    with tarfile.open(fileobj=source_buffer, mode="r:gz") as source:
        with gzip.GzipFile(filename="", fileobj=output, mode="wb",
                           mtime=int(epoch)) as compressed:
            with tarfile.open(fileobj=compressed, mode="w",
                              format=tarfile.PAX_FORMAT) as target:
                for member in sorted(source.getmembers(), key=lambda item: item.name):
                    stable = copy.copy(member)
                    stable.mtime = int(epoch)
                    stable.uid = stable.gid = 0
                    stable.uname = stable.gname = ""
                    stable.pax_headers = {}
                    body = source.extractfile(member) if member.isfile() else None
                    target.addfile(stable, body)
    return output.getvalue()


def normalize_sdist(path, epoch):
    path = Path(path)
    path.write_bytes(normalized_sdist_bytes(path.read_bytes(), epoch))


def _metadata_version(payload):
    message = BytesParser().parsebytes(payload)
    return message.get("Name"), message.get("Version"), message.get_all(
        "Requires-Dist", [])


def _validate_python_metadata(payload, version):
    name, found, requirements = _metadata_version(payload)
    if name != "codetalk" or found != version:
        raise ValueError(f"Python metadata drift: {name} {found}")
    unconditional = [item for item in requirements if "extra ==" not in item]
    if unconditional:
        raise ValueError("core runtime dependencies found: "
                         + ", ".join(unconditional))


def _validate_wheel(path, version):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        metadata = [name for name in names if name.endswith(".dist-info/METADATA")]
        if len(metadata) != 1:
            raise ValueError("wheel must contain one METADATA file")
        _validate_python_metadata(archive.read(metadata[0]), version)
        if not any(name.endswith(".dist-info/licenses/LICENSE") for name in names):
            raise ValueError("wheel is missing LICENSE")


def root_sdist_metadata(names, version=VERSION):
    expected = f"codetalk-{version}/PKG-INFO"
    if expected not in names:
        raise ValueError("sdist root PKG-INFO is missing")
    return expected


def _validate_sdist(path, version):
    with tarfile.open(path, "r:gz") as archive:
        members = {member.name: member for member in archive.getmembers()}
        metadata = root_sdist_metadata(members, version)
        handle = archive.extractfile(members[metadata])
        if handle is None:
            raise ValueError("sdist PKG-INFO is unreadable")
        _validate_python_metadata(handle.read(), version)
        if not any(name.endswith("/LICENSE") for name in members):
            raise ValueError("sdist is missing LICENSE")


def _validate_mcpb(path, version):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("version") != version:
            raise ValueError("MCP manifest version drift")
        if "LICENSE" not in names or "server/codetalk/mcp_server.py" not in names:
            raise ValueError("MCP bundle is missing license or server source")


def _validate_vsix(path, version):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        package = json.loads(archive.read("extension/package.json"))
        if package.get("version") != version:
            raise ValueError("VSIX package version drift")
        if "extension/LICENSE.txt" not in names or "extension/dist/extension.js" not in names:
            raise ValueError("VSIX is missing license or built extension")


def validate_artifacts(directory, version=VERSION):
    directory = Path(directory)
    names = expected_artifact_names(version)
    _validate_wheel(directory / names[0], version)
    _validate_sdist(directory / names[1], version)
    _validate_mcpb(directory / names[2], version)
    _validate_vsix(directory / names[3], version)


def render_sbom(version, records):
    identity = "\n".join(
        f"{item['name']}:{item['sha256']}" for item in records)
    serial = uuid.uuid5(uuid.NAMESPACE_URL, identity)
    return {
        "bomFormat": "CycloneDX", "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{serial}", "version": 1,
        "metadata": {"component": {
            "type": "application", "name": "codetalk", "version": version,
            "purl": f"pkg:pypi/codetalk@{version}",
        }},
        "components": [{
            "type": "file", "name": item["name"], "version": version,
            "hashes": [{"alg": "SHA-256", "content": item["sha256"]}],
            "properties": [{"name": "codetalk:artifact-size",
                            "value": str(item["size"])}],
        } for item in records],
    }


def write_release_metadata(directory, version=VERSION, epoch=None):
    directory = Path(directory)
    if epoch is not None:
        normalize_sdist(directory / expected_artifact_names(version)[1], epoch)
    validate_artifacts(directory, version)
    records = artifact_records(directory, version)
    sbom_path = directory / f"codetalk-{version}.sbom.cdx.json"
    sbom_path.write_text(json.dumps(render_sbom(version, records), indent=2)
                         + "\n", encoding="utf-8")
    checksum_records = records + [{
        "name": sbom_path.name, "sha256": _sha256(sbom_path),
        "size": sbom_path.stat().st_size,
    }]
    sums = directory / "SHA256SUMS"
    sums.write_text("".join(
        f"{item['sha256']}  {item['name']}\n" for item in checksum_records),
        encoding="ascii")
    return sums, sbom_path


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate CodeTalk release artifacts and write metadata")
    parser.add_argument("directory", nargs="?", default="dist")
    args = parser.parse_args(argv)
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if not epoch or not epoch.isdigit():
        parser.error("SOURCE_DATE_EPOCH must be an integer for reproducible sdist")
    sums, sbom = write_release_metadata(args.directory, epoch=int(epoch))
    print(f"validated {len(expected_artifact_names())} artifacts")
    print(f"wrote {sums} and {sbom}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
