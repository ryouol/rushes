#!/usr/bin/env python3
"""Hold the first decoder invocation until its test container is interrupted."""

import os
import sys
import time
from pathlib import Path

marker = Path("/var/data/ffmpeg-held")
try:
    marker.touch(exist_ok=False)
except FileExistsError:
    pass
else:
    time.sleep(120)
os.execv("/usr/bin/ffmpeg", ["/usr/bin/ffmpeg", *sys.argv[1:]])
