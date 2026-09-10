"""One deterministic frame-selection rule shared by rendering and interchange."""

import gzip
import json

from rushes.timing import Interval, pts_to_us


def selected_frames(frame_map: str, time_base: str, origin_pts: int, interval: Interval):
    first = last = None
    with gzip.open(frame_map, "rt") as source:
        for line in source:
            frame = json.loads(line)
            elapsed = pts_to_us(frame["pts"], time_base, origin_pts)
            if elapsed >= interval.end_us:
                break
            if elapsed >= interval.start_us:
                first = frame if first is None else first
                last = frame
    if first is None:
        raise ValueError("Selected interval contains no source presentation frames")
    return first, last
