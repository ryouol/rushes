"""Conservative straight-cut interchange. Target-editor round trips remain separate evidence."""

from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree as ET

from rushes.source_frames import selected_frames
from rushes.timing import Interval, timecode_frame


def sub(parent, tag, value=None, **attributes):
    node = ET.SubElement(parent, tag, {key: str(value) for key, value in attributes.items()})
    if value is not None:
        node.text = str(value)
    return node


def rate_element(parent, rate: Fraction):
    node = sub(parent, "rate")
    sub(node, "timebase", round(rate))
    sub(node, "ntsc", "TRUE" if rate.denominator == 1001 else "FALSE")


def frame_selection(entry: dict) -> tuple[int, int]:
    timeline = entry["timeline"]
    first, last = selected_frames(
        timeline["frame_map"],
        timeline["time_base"],
        timeline["first_pts"],
        Interval(start_us=entry["start_us"], end_us=entry["end_us"]),
    )
    return first["ordinal"], last["ordinal"] + 1


def validate_entries(entries: list[dict]) -> Fraction:
    if not entries:
        raise ValueError("Select footage for interchange")
    rates = {Fraction(entry["timeline"]["average_rate"]) for entry in entries}
    if len(rates) != 1:
        raise ValueError(
            "Interchange currently requires one shared source frame rate. Export rendered clips for mixed-rate projects."
        )
    rate = rates.pop()
    if rate not in {
        Fraction(24),
        Fraction(25),
        Fraction(30),
        Fraction(50),
        Fraction(60),
        Fraction(24000, 1001),
        Fraction(30000, 1001),
        Fraction(60000, 1001),
    }:
        raise ValueError(
            "This source frame rate is not supported by the initial interchange writer"
        )
    if any(
        not entry["timeline"]["constant_frame_rate"] or entry["timeline"]["rotation"]
        for entry in entries
    ):
        raise ValueError(
            "Interchange currently requires constant-rate, unrotated sources. Use rendered clips for this selection."
        )
    return rate


def fcp7_xml(entries: list[dict], title: str) -> bytes:
    rate = validate_entries(entries)
    root = ET.Element("xmeml", version="5")
    sequence = sub(root, "sequence", id="rushes-sequence")
    sub(sequence, "name", title)
    selections = [frame_selection(entry) for entry in entries]
    sub(sequence, "duration", sum(end - start for start, end in selections))
    rate_element(sequence, rate)
    media = sub(sequence, "media")
    video = sub(media, "video")
    sample = sub(sub(video, "format"), "samplecharacteristics")
    rate_element(sample, rate)
    sub(sample, "width", entries[0]["timeline"]["width"])
    sub(sample, "height", entries[0]["timeline"]["height"])
    track = sub(video, "track")
    audio_track = sub(sub(media, "audio"), "track")
    cursor = 0
    for index, (entry, (start, end)) in enumerate(zip(entries, selections, strict=True)):
        timeline = entry["timeline"]
        file_id = f"file-{index}"
        clip = sub(track, "clipitem", id=f"video-{index}")
        sub(clip, "name", entry["source_name"])
        sub(clip, "duration", timeline["frame_count"])
        rate_element(clip, rate)
        for tag, value in [
            ("start", cursor),
            ("end", cursor + end - start),
            ("in", start),
            ("out", end),
        ]:
            sub(clip, tag, value)
        file = sub(clip, "file", id=file_id)
        sub(file, "name", entry["source_name"])
        sub(file, "pathurl", (Path(entry["source_root"]) / entry["relative_path"]).as_uri())
        rate_element(file, rate)
        sub(file, "duration", timeline["frame_count"])
        if timeline.get("source_timecode"):
            tc = sub(file, "timecode")
            rate_element(tc, rate)
            sub(tc, "string", timeline["source_timecode"])
            sub(tc, "frame", timecode_frame(timeline["source_timecode"], rate))
            sub(tc, "displayformat", "DF" if timeline["drop_frame"] else "NDF")
        characteristics = sub(sub(sub(file, "media"), "video"), "samplecharacteristics")
        sub(characteristics, "width", timeline["width"])
        sub(characteristics, "height", timeline["height"])
        if timeline["has_audio"]:
            audio = sub(audio_track, "clipitem", id=f"audio-{index}")
            sub(audio, "name", entry["source_name"])
            sub(audio, "duration", timeline["frame_count"])
            rate_element(audio, rate)
            for tag, value in [
                ("start", cursor),
                ("end", cursor + end - start),
                ("in", start),
                ("out", end),
            ]:
                sub(audio, tag, value)
            sub(audio, "file", id=file_id)
            source_track = sub(audio, "sourcetrack")
            sub(source_track, "mediatype", "audio")
            sub(source_track, "trackindex", 1)
        cursor += end - start
    ET.indent(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def fcpxml(entries: list[dict], title: str) -> bytes:
    rate = validate_entries(entries)
    root = ET.Element("fcpxml", version="1.10")
    resources = sub(root, "resources")
    selections = [frame_selection(entry) for entry in entries]

    def seconds(frames):
        value = Fraction(frames, 1) / rate
        return f"{value.numerator}/{value.denominator}s"

    for index, entry in enumerate(entries):
        timeline = entry["timeline"]
        sub(
            resources,
            "format",
            id=f"format-{index}",
            frameDuration=seconds(1),
            width=timeline["width"],
            height=timeline["height"],
        )
        tc = (
            timecode_frame(timeline["source_timecode"], rate)
            if timeline.get("source_timecode")
            else 0
        )
        asset = sub(
            resources,
            "asset",
            id=f"asset-{index}",
            name=entry["source_name"],
            start=seconds(tc),
            duration=seconds(timeline["frame_count"]),
            hasVideo="1",
            hasAudio="1" if timeline["has_audio"] else "0",
            format=f"format-{index}",
        )
        sub(
            asset,
            "media-rep",
            kind="original-media",
            src=(Path(entry["source_root"]) / entry["relative_path"]).as_uri(),
        )
    event = sub(sub(root, "library"), "event", name="RUSHES selects")
    project = sub(event, "project", name=title)
    sequence = sub(
        project,
        "sequence",
        format="format-0",
        duration=seconds(sum(end - start for start, end in selections)),
        tcStart="0s",
        tcFormat="NDF",
    )
    spine = sub(sequence, "spine")
    cursor = 0
    for index, (entry, (start, end)) in enumerate(zip(entries, selections, strict=True)):
        tc = (
            timecode_frame(entry["timeline"]["source_timecode"], rate)
            if entry["timeline"].get("source_timecode")
            else 0
        )
        sub(
            spine,
            "asset-clip",
            name=entry["source_name"],
            ref=f"asset-{index}",
            offset=seconds(cursor),
            start=seconds(tc + start),
            duration=seconds(end - start),
        )
        cursor += end - start
    ET.indent(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
