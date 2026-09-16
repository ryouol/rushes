"""Fixed synthetic speech corpus; generated locally, no licensed camera footage required."""

import hashlib
import json
import subprocess
from pathlib import Path

TEXT = "The red bicycle is parked beside the blue river. A yellow train passes the green forest. The camera follows a person walking across the bridge."
FIXTURES = [
    (15, "640x360", "libx264", "h264"),
    (65, "1280x720", "libx264", "h264"),
    (125, "1920x1080", "libx265", "hevc"),
]
QUERIES = ["red bicycle", "yellow train", "walking across the bridge", "blue river", "green forest"]


def generate(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    speech = folder / "speech.aiff"
    if not speech.exists():
        subprocess.run(["say", "-v", "Samantha", "-r", "145", "-o", str(speech), TEXT], check=True)
    rows = []
    for duration, size, encoder, codec in FIXTURES:
        path = folder / f"synthetic-{duration}s-{size}-{codec}.mp4"
        if not path.exists():
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    f"testsrc2=size={size}:rate=24",
                    "-stream_loop",
                    "-1",
                    "-i",
                    str(speech),
                    "-t",
                    str(duration),
                    "-c:v",
                    encoder,
                    "-preset",
                    "ultrafast",
                    "-threads",
                    "2",
                    *(["-x265-params", "pools=2:frame-threads=2"] if codec == "hevc" else []),
                    "-c:a",
                    "aac",
                    str(path),
                ],
                check=True,
                stderr=subprocess.DEVNULL,
            )
        rows.append(
            {
                "file": path.name,
                "duration_seconds": duration,
                "resolution": size,
                "codec": codec,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    manifest = {
        "source": "FFmpeg testsrc2 plus macOS Samantha synthetic speech",
        "speech": TEXT,
        "queries": QUERIES,
        "fixtures": rows,
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    generate(Path(".local/pipeline-study/fixtures"))
