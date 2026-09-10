"""Install the pinned production server and matching PostgreSQL migrations."""

import argparse
import hashlib
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

VERSION = "1.31.2"
SOURCE_SHA256 = "b37e0096bd8609a4081180b1cb9b095c83f63de0e261875c74c2965f82204ea7"


def download(url: str, path: Path, expected: str):
    digest = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=60) as response, path.open("wb") as output:
        while chunk := response.read(1024**2):
            digest.update(chunk)
            output.write(chunk)
    if digest.hexdigest() != expected:
        raise ValueError("Temporal release checksum verification failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", choices=["amd64", "arm64"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = f"https://github.com/temporalio/temporal/releases/download/v{VERSION}"
    name = f"temporal_{VERSION}_linux_{args.arch}.tar.gz"
    with urllib.request.urlopen(f"{base}/checksums.txt", timeout=30) as response:
        checksums = response.read().decode()
    expected = next(row.split()[0] for row in checksums.splitlines() if row.split()[-1] == name)
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rushes-temporal-install-") as temporary:
        archive = Path(temporary) / "release.tar.gz"
        download(f"{base}/{name}", archive, expected)
        with tarfile.open(archive) as package:
            for binary in ("temporal-server", "temporal-sql-tool"):
                with (
                    package.extractfile(binary) as source,
                    (args.output / binary).open("wb") as target,
                ):
                    shutil.copyfileobj(source, target)
                (args.output / binary).chmod(0o755)
        download(
            f"https://github.com/temporalio/temporal/archive/refs/tags/v{VERSION}.tar.gz",
            archive,
            SOURCE_SHA256,
        )
        prefix = f"temporal-{VERSION}/schema/postgresql/v12/"
        with tarfile.open(archive) as package:
            for member in package.getmembers():
                if not member.isfile() or not member.name.startswith(prefix):
                    continue
                relative = Path(member.name.removeprefix(prefix))
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("Unexpected Temporal schema archive path")
                target = args.output / "schema" / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.extractfile(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
            with package.extractfile(f"temporal-{VERSION}/LICENSE") as source:
                (args.output / "LICENSE").write_bytes(source.read())
    (args.output / "VERSION").write_text(VERSION + "\n")
    print(f"Installed verified Temporal Server {VERSION} and matching PostgreSQL schemas")


if __name__ == "__main__":
    main()
