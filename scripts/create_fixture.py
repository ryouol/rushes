"""Create explicitly synthetic red/blue footage with locally synthesized speech for QA."""

import subprocess
from pathlib import Path

root = Path(".local/fixtures")
root.mkdir(parents=True, exist_ok=True)
speech = root / "synthetic-speech.aiff"
subprocess.run(
    [
        "say",
        "-o",
        str(speech),
        "This is a synthetic timing fixture. The first shot is red. The second shot is blue.",
    ],
    check=True,
)
subprocess.run(
    [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=red:size=640x360:rate=24:duration=6",
        "-f",
        "lavfi",
        "-i",
        "color=c=blue:size=640x360:rate=24:duration=6",
        "-i",
        str(speech),
        "-filter_complex",
        "[0:v][1:v]concat=n=2:v=1:a=0[v];[2:a]apad[a]",
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-t",
        "12",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-pix_fmt",
        "yuv420p",
        "-timecode",
        "01:00:00:00",
        str(root / "SYNTHETIC-red-blue-speech.mp4"),
    ],
    check=True,
)
print("Created .local/fixtures/SYNTHETIC-red-blue-speech.mp4 (12 seconds; cut at 6 seconds).")
