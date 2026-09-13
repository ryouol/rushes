import gzip
import json
import subprocess

import pytest
from rushes.media import detect_shots, inspect, make_proxy, probe, proxy_mapping, render_clip
from rushes.storage import fingerprint, open_source
from rushes.timing import Interval, pts_to_us


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", *args], check=True)


@pytest.fixture
def fixture_video(tmp_path):
    path = tmp_path / "synthetic-rational.mp4"
    ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=160x90:rate=30000/1001:duration=2",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-timecode",
        "01:00:00;00",
        str(path),
    )
    return path


@pytest.mark.media
def test_probe_proxy_export_rational_and_source_preservation(fixture_video, tmp_path):
    with open_source(tmp_path, fixture_video.name) as source:
        original_hash = fingerprint(source)
        timeline = inspect(source, tmp_path / "frames.jsonl.gz")
        assert timeline.average_rate == "30000/1001"
        assert timeline.constant_frame_rate
        assert timeline.frame_count == 60
        assert timeline.source_timecode == "01:00:00;00"
        assert timeline.drop_frame
        assert not timeline.has_audio
        proxy = tmp_path / "proxy.mp4"
        make_proxy(source, proxy, timeline)
        with proxy.open("rb") as preview:
            preview_timeline = inspect(preview, tmp_path / "proxy-frames.jsonl.gz")
        mapping = proxy_mapping(timeline, preview_timeline)
        assert mapping["maximum_error_us"] <= 2000
        assert detect_shots(proxy, timeline.duration_us)
        interval = Interval(start_us=500_500, end_us=1_001_000)
        plan = render_clip(source, timeline, interval, tmp_path / "clip.mp4")
        assert plan["first_source_pts"] == 15015
        assert plan["last_source_pts"] == 29029
        with (tmp_path / "clip.mp4").open("rb") as clip:
            exported = inspect(clip, tmp_path / "export-frames.jsonl.gz")
        assert exported.frame_count == 15
        assert abs(exported.duration_us - 500_500) <= 1000
        assert fingerprint(source) == original_hash


@pytest.mark.media
def test_vfr_mapping_and_half_open_export(tmp_path):
    path = tmp_path / "synthetic-vfr.mp4"
    ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=160x90:rate=30:duration=1",
        "-vf",
        "setpts='if(lt(N,15),N/(30*TB),(0.5+(N-15)/10)/TB)'",
        "-fps_mode",
        "vfr",
        "-c:v",
        "libx264",
        str(path),
    )
    with open_source(tmp_path, path.name) as source:
        timeline = inspect(source, tmp_path / "vfr-frames.jsonl.gz")
        assert not timeline.constant_frame_rate
        with gzip.open(timeline.frame_map, "rt") as file:
            frames = [json.loads(line) for line in file]
        start = pts_to_us(frames[16]["pts"], timeline.time_base, timeline.first_pts)
        end = pts_to_us(frames[20]["pts"], timeline.time_base, timeline.first_pts)
        render_clip(source, timeline, Interval(start_us=start, end_us=end), tmp_path / "clip.mp4")
        with (tmp_path / "clip.mp4").open("rb") as clip:
            exported = inspect(clip, tmp_path / "clip-frames.jsonl.gz")
        assert exported.frame_count == 4
        make_proxy(source, tmp_path / "proxy.mp4", timeline)
        with (tmp_path / "proxy.mp4").open("rb") as preview:
            mapped = inspect(preview, tmp_path / "preview-frames.jsonl.gz")
        assert proxy_mapping(timeline, mapped)["maximum_error_us"] <= 2000


@pytest.mark.media
def test_proxy_preserves_subframe_mov_timestamps(tmp_path):
    path = tmp_path / "synthetic-camera.mov"
    ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=160x90:rate=30:duration=2",
        "-vf",
        "settb=1/600,setpts='20*N+mod(N,3)*3'",
        "-fps_mode",
        "passthrough",
        "-enc_time_base:v",
        "1/600",
        "-video_track_timescale",
        "600",
        "-c:v",
        "libx264",
        str(path),
    )
    with open_source(tmp_path, path.name) as source:
        digest = fingerprint(source)
        timeline = inspect(source, tmp_path / "source.jsonl.gz")
        assert timeline.time_base == "1/600"
        assert not timeline.constant_frame_rate
        make_proxy(source, tmp_path / "proxy.mp4", timeline)
        with (tmp_path / "proxy.mp4").open("rb") as preview:
            mapped = inspect(preview, tmp_path / "proxy.jsonl.gz")
        assert mapped.frame_count == timeline.frame_count == 60
        assert proxy_mapping(timeline, mapped)["maximum_error_us"] == 0
        render_clip(
            source,
            timeline,
            Interval(start_us=0, end_us=timeline.duration_us),
            tmp_path / "clip.mp4",
        )
        with (tmp_path / "clip.mp4").open("rb") as clip:
            rendered = inspect(clip, tmp_path / "clip.jsonl.gz")
        assert proxy_mapping(timeline, rendered)["maximum_error_us"] == 0
        assert fingerprint(source) == digest


@pytest.mark.media
def test_rotation_and_audio(tmp_path):
    base, rotated = tmp_path / "base.mp4", tmp_path / "rotated.mp4"
    ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=160x90:rate=24:duration=1",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=1",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        str(base),
    )
    ffmpeg("-display_rotation", "90", "-i", str(base), "-c", "copy", str(rotated))
    with open_source(tmp_path, rotated.name) as source:
        timeline = inspect(source, tmp_path / "frames.jsonl.gz")
        assert timeline.has_audio
        assert abs(timeline.rotation) == 90
        make_proxy(source, tmp_path / "proxy.mp4", timeline)
        with (tmp_path / "proxy.mp4").open("rb") as preview:
            mapped = inspect(preview, tmp_path / "preview-frames.jsonl.gz")
        assert mapped.height > mapped.width
        assert mapped.rotation == 0
        render_clip(
            source, timeline, Interval(start_us=0, end_us=timeline.duration_us), tmp_path / "clip.mp4"
        )
        with (tmp_path / "clip.mp4").open("rb") as clip:
            rendered = inspect(clip, tmp_path / "rendered-frames.jsonl.gz")
        assert (rendered.width, rendered.height) == (timeline.height, timeline.width)
        assert rendered.rotation == 0 and rendered.has_audio
        assert proxy_mapping(timeline, rendered)["maximum_error_us"] == 0


@pytest.mark.media
def test_late_selection_preserves_nonzero_pts_and_delayed_audio(tmp_path):
    import array

    path = tmp_path / "SYNTHETIC-offset.mp4"
    ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=160x90:rate=24:duration=6",
        "-itsoffset",
        "1",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=5",
        "-c:v",
        "libx264",
        "-g",
        "48",
        "-c:a",
        "aac",
        "-output_ts_offset",
        "5",
        str(path),
    )
    with path.open("rb") as source:
        timeline = inspect(source, tmp_path / "source.gz")
        assert timeline.first_pts > 0
        proxy = tmp_path / "proxy.mp4"
        make_proxy(source, proxy, timeline)
        clip = tmp_path / "late.mp4"
        plan = render_clip(source, timeline, Interval(start_us=4_000_000, end_us=5_000_000), clip)
        assert plan["first_source_elapsed_us"] == 4_000_000
        with clip.open("rb") as result:
            rendered = inspect(result, tmp_path / "render.gz")
        assert rendered.frame_count == 24
        original_streams = {stream["codec_type"]: stream for stream in probe(source)["streams"]}
        original_offset = float(original_streams["audio"]["start_time"]) - float(
            original_streams["video"]["start_time"]
        )
        assert abs(original_offset - 1.0) < 0.03
        delayed_clip = tmp_path / "delayed.mp4"
        render_clip(source, timeline, Interval(start_us=0, end_us=2_000_000), delayed_clip)
        with delayed_clip.open("rb") as result:
            streams = {stream["codec_type"]: stream for stream in probe(result)["streams"]}
        offset = float(streams["audio"]["start_time"]) - float(streams["video"]["start_time"])
        # Re-encoding adds AAC priming; preserve the source gap within one audio frame.
        assert abs(offset - original_offset) < 0.03
    pcm = subprocess.check_output(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(proxy),
            "-map",
            "0:a:0",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-f",
            "s16le",
            "-",
        ]
    )
    values = array.array("h", pcm)
    early = sum(value * value for value in values[:8000]) / 8000
    audible = sum(value * value for value in values[32000:40000]) / 8000
    assert early < 100 and audible > 100_000
