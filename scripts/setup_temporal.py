"""Install a pinned official Temporal CLI into the project, verifying its published digest."""

import hashlib
import io
import platform
import tarfile
import urllib.request
from pathlib import Path

VERSION = "1.8.3"
system = {"Darwin": "darwin", "Linux": "linux"}.get(platform.system())
arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64"}.get(platform.machine())
if not system or not arch:
    raise SystemExit("Install Temporal CLI manually for this platform.")
name = f"temporal_cli_{VERSION}_{system}_{arch}.tar.gz"
base = f"https://github.com/temporalio/cli/releases/download/v{VERSION}"
with urllib.request.urlopen(f"{base}/checksums.txt", timeout=60) as response:
    checksums = response.read().decode()
expected = next(line.split()[0] for line in checksums.splitlines() if line.split()[-1] == name)
with urllib.request.urlopen(f"{base}/{name}", timeout=60) as response:
    data = response.read()
if hashlib.sha256(data).hexdigest() != expected:
    raise SystemExit("Temporal CLI checksum verification failed")
target = Path(".local/bin/temporal")
target.parent.mkdir(parents=True, exist_ok=True)
with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
    binary = archive.extractfile("temporal")
    if binary is None:
        raise SystemExit("Temporal binary missing from official archive")
    target.write_bytes(binary.read())
target.chmod(0o755)
print(f"Installed verified Temporal CLI {VERSION} at {target}")
