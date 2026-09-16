"""Linux /proc RSS and cgroup memory sampler; run inside the measured container.

FFmpeg is an independent process: Python profiling does not measure its CPU or RSS.
The sampler's own RSS is included in the container reading.
"""

import argparse
import json
import os
import time
from pathlib import Path


def sample():
    processes = []
    for folder in Path("/proc").glob("[0-9]*"):
        try:
            name = (folder / "comm").read_text().strip()
            if (
                name not in {"python", "python3", "ffmpeg", "ffprobe"}
                or int(folder.name) == os.getpid()
            ):
                continue
            rss = int((folder / "statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
            processes.append({"pid": int(folder.name), "name": name, "rss_bytes": rss})
        except (OSError, ValueError, IndexError):
            continue
    return {
        "time_ns": time.time_ns(),
        "processes": processes,
        "container_bytes": int(Path("/sys/fs/cgroup/memory.current").read_text()),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--seconds", type=int, default=3600)
    args = parser.parse_args()
    until = time.monotonic() + args.seconds
    with args.output.open("a") as file:
        while time.monotonic() < until:
            file.write(json.dumps(sample()) + "\n")
            file.flush()
            time.sleep(0.05)
