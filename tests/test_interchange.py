import gzip
import json
from fractions import Fraction
from xml.etree import ElementTree as ET

import pytest
from rushes.interchange import fcp7_xml, fcpxml, frame_selection, validate_entries
from rushes.timing import seconds, timecode, timecode_frame


@pytest.mark.parametrize(
    "rate,drop",
    [(Fraction(24), False), (Fraction(30000, 1001), True), (Fraction(60000, 1001), True)],
)
def test_timecode_round_trip(rate, drop):
    for frame in [0, 1, 1798, 17982, round(rate * 3600), round(rate * 36000)]:
        assert timecode_frame(timecode(frame, rate, drop), rate) == frame
    assert seconds(-500_000) == "-0.500000"


def test_interchange_uses_source_ordinals_and_rational_time(tmp_path):
    mapping = tmp_path / "frames.gz"
    with gzip.open(mapping, "wt") as file:
        for i in range(60):
            file.write(json.dumps({"ordinal": i, "pts": i * 1001}) + "\n")
    entry = {
        "source_name": "A & B.mov",
        "source_root": str(tmp_path),
        "relative_path": "A & B.mov",
        "start_us": 500500,
        "end_us": 1001000,
        "timeline": {
            "average_rate": "30000/1001",
            "time_base": "1/30000",
            "first_pts": 0,
            "frame_count": 60,
            "frame_map": str(mapping),
            "constant_frame_rate": True,
            "rotation": 0,
            "width": 640,
            "height": 360,
            "has_audio": True,
            "source_timecode": "01:00:00;00",
            "drop_frame": True,
        },
    }
    assert frame_selection(entry) == (15, 30)
    seven = ET.fromstring(fcp7_xml([entry], "Synthetic selects"))
    clip = seven.find(".//video/track/clipitem")
    assert clip.findtext("in") == "15" and clip.findtext("out") == "30"
    assert seven.findtext(".//file/timecode/frame") == "107892"
    x = ET.fromstring(fcpxml([entry], "Synthetic selects"))
    assert x.find(".//format").get("frameDuration") == "1001/30000s"
    assert x.find(".//asset-clip").get("duration") == "1001/2000s"
    assert "%20" in x.find(".//media-rep").get("src")
    with pytest.raises(ValueError):
        validate_entries(
            [{**entry, "timeline": {**entry["timeline"], "constant_frame_rate": False}}]
        )
