"""Run OpenCV in its own process to avoid conflicting macOS FFmpeg dylibs in Whisper."""

import json
import os
import sys

import cv2
from scenedetect import ContentDetector, detect

from rushes.config import settings
from rushes.timing import Interval, to_us


def main():
    os.environ["OPENCV_FFMPEG_THREADS"] = str(settings().media_threads)
    cv2.setNumThreads(settings().media_threads)
    proxy, duration = sys.argv[1], int(sys.argv[2])
    scenes = detect(proxy, ContentDetector(), start_in_scene=True)
    intervals = []
    for start, end in scenes:
        left = max(0, to_us(str(start.get_seconds())))
        right = min(duration, to_us(str(end.get_seconds())))
        if right > left:
            intervals.append(Interval(start_us=left, end_us=right).model_dump())
    print(json.dumps(intervals or [{"start_us": 0, "end_us": duration}]))


if __name__ == "__main__":
    main()
