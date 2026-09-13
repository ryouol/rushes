import gzip
import json
import os
import select
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path
from typing import BinaryIO

from pydantic import BaseModel

from rushes.config import settings
from rushes.source_frames import selected_frames
from rushes.storage import require_space
from rushes.timing import Interval, pts_to_us, seconds, to_us

Progress = Callable[[str], None]
DEMUXERS = "mov,matroska,avi,mpegts,mpeg,mxf,asf,ogg"
RENDERER_VERSION = "source-pts-v4"


class MediaError(RuntimeError):
    pass


class Timeline(BaseModel):
    duration_us: int
    final_frame_duration_estimated: bool = False
    time_base: str
    first_pts: int
    last_pts: int
    frame_count: int
    average_rate: str
    nominal_rate: str
    constant_frame_rate: bool
    source_timecode: str | None
    drop_frame: bool | None
    width: int
    height: int
    rotation: int
    has_audio: bool
    codec: str
    frame_map: str


def source_args(file: BinaryIO) -> list[str]:
    file.seek(0)
    return [
        "-protocol_whitelist",
        "file,pipe",
        "-threads",
        str(settings().media_threads),
        "-format_whitelist",
        DEMUXERS,
        "-i",
        f"/dev/fd/{file.fileno()}",
    ]


def run_media(
    args: list[str],
    *,
    source: BinaryIO | None = None,
    progress: Progress | None = None,
    timeout: int = 7200,
) -> str:
    """Bound diagnostics and heartbeat while FFmpeg runs; never invoke a shell."""
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=errors,
            pass_fds=(source.fileno(),) if source else (),
        )
        started = time.monotonic()
        try:
            while process.poll() is None:
                if Path(args[-1]).is_absolute():
                    require_space(Path(args[-1]).parent, 0, settings().min_free_bytes)
                if (
                    os.fstat(errors.fileno()).st_size > 4 * 1024 * 1024
                    or os.fstat(output.fileno()).st_size > 4 * 1024 * 1024
                ):
                    raise MediaError("Source produced excessive decoder errors")
                if time.monotonic() - started > timeout:
                    raise MediaError("Media operation exceeded its time limit")
                if progress:
                    progress("processing")
                time.sleep(0.25)
            if process.returncode:
                errors.seek(0, os.SEEK_END)
                errors.seek(max(0, errors.tell() - 1500))
                detail = errors.read().decode(errors="replace")
                raise MediaError(f"Media operation failed: {detail}")
            output.seek(0)
            return output.read(4 * 1024 * 1024).decode()
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()


def probe(file: BinaryIO) -> dict:
    return json.loads(
        run_media(
            [
                "ffprobe",
                "-v",
                "error",
                *source_args(file),
                "-show_streams",
                "-show_format",
                "-of",
                "json",
            ],
            source=file,
            timeout=120,
        )
    )


def probe_lines(process, errors, progress):
    """Poll bytes, avoiding buffered readline stalls on corrupt inputs while retaining bounded memory."""
    started = time.monotonic()
    pending = b""
    while True:
        if time.monotonic() - started > 7200:
            raise MediaError("Frame inspection exceeded its time limit")
        if os.fstat(errors.fileno()).st_size > 4 * 1024 * 1024:
            raise MediaError("Source produced excessive decoder errors")
        if progress:
            progress("Inspecting presentation timestamps")
        if not select.select([process.stdout], [], [], 0.25)[0]:
            continue
        chunk = os.read(process.stdout.fileno(), 65536)
        if not chunk:
            if pending:
                yield pending.decode()
            return
        pending += chunk
        if len(pending) > 1024 * 1024:
            raise MediaError("Frame metadata exceeds its resource limit")
        lines = pending.split(b"\n")
        pending = lines.pop()
        for line in lines:
            yield line.decode()


def inspect(
    file: BinaryIO, frame_map: Path, *, progress: Progress | None = None, max_seconds: int = 86400
) -> Timeline:
    metadata = probe(file)
    video = next((s for s in metadata["streams"] if s["codec_type"] == "video"), None)
    if video is None:
        raise MediaError("File contains no supported video stream")
    if video.get("width", 0) * video.get("height", 0) > 8192 * 4320:
        raise MediaError("Source exceeds the local release's 8K decoding limit")
    declared_duration = video.get("duration", metadata["format"].get("duration"))
    if declared_duration and Fraction(declared_duration) > max_seconds:
        raise MediaError("Source exceeds the configured duration limit")
    time_base = video["time_base"]
    frame_map.parent.mkdir(parents=True, exist_ok=True)
    temporary = frame_map.with_name(f".{frame_map.stem}.{uuid.uuid4().hex}.partial.gz")
    command = [
        "ffprobe",
        "-v",
        "error",
        *source_args(file),
        "-select_streams",
        "v:0",
        "-show_frames",
        "-show_entries",
        "frame=best_effort_timestamp,duration,pkt_duration",
        "-of",
        "compact=p=0:nk=0",
    ]
    first = last = None
    count = 0
    min_delta = max_delta = None
    final_duration = 0
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=errors, pass_fds=(file.fileno(),)
        )
        try:
            with gzip.open(temporary, "wt") as output:
                assert process.stdout is not None
                for line in probe_lines(process, errors, progress):
                    values = dict(
                        item.split("=", 1) for item in line.strip().split("|") if "=" in item
                    )
                    raw = values.get("best_effort_timestamp")
                    if raw is None:
                        continue
                    if raw == "N/A":
                        raise MediaError("Video has no usable presentation timestamps")
                    pts = int(raw)
                    duration = values.get("duration", values.get("pkt_duration", "0"))
                    final_duration = int(duration) if duration != "N/A" else 0
                    if first is None:
                        first = pts
                    if last is not None:
                        delta = pts - last
                        if delta <= 0:
                            raise MediaError("Video has non-increasing presentation timestamps")
                        min_delta = delta if min_delta is None else min(min_delta, delta)
                        max_delta = delta if max_delta is None else max(max_delta, delta)
                    last = pts
                    if pts_to_us(pts, time_base, first) > max_seconds * 1_000_000:
                        raise MediaError("Source exceeds the configured duration limit")
                    output.write(
                        json.dumps({"ordinal": count, "pts": pts, "duration": final_duration})
                        + "\n"
                    )
                    count += 1
                    if progress and count % 300 == 0:
                        progress(f"inspected {count} frames")
            if process.wait(timeout=30):
                raise MediaError("Unable to decode the source frame timeline")
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            if process.stdout:
                process.stdout.close()
    if first is None or last is None:
        temporary.unlink(missing_ok=True)
        raise MediaError("Video contains no decodable frames")
    duration_estimated = final_duration <= 0
    if duration_estimated:
        # A missing last-frame duration is an explicit estimate, recorded with the source rate.
        rate = Fraction(video.get("avg_frame_rate", "0/1"))
        final_duration = max_delta or (round(1 / rate / Fraction(time_base)) if rate else 1)
    duration_us = pts_to_us(last + final_duration, time_base, first)
    tags = {**metadata["format"].get("tags", {}), **video.get("tags", {})}
    source_tc = tags.get("timecode")
    rotation = next(
        (int(s["rotation"]) for s in video.get("side_data_list", []) if "rotation" in s),
        int(tags.get("rotate", 0)),
    )
    os.replace(temporary, frame_map)
    return Timeline(
        duration_us=duration_us,
        final_frame_duration_estimated=duration_estimated,
        time_base=time_base,
        first_pts=first,
        last_pts=last,
        frame_count=count,
        average_rate=video.get("avg_frame_rate", "0/1"),
        nominal_rate=video.get("r_frame_rate", "0/1"),
        constant_frame_rate=min_delta is not None and max_delta == min_delta,
        source_timecode=source_tc,
        drop_frame=(";" in source_tc) if source_tc else None,
        width=video["width"],
        height=video["height"],
        rotation=rotation,
        has_audio=any(s["codec_type"] == "audio" for s in metadata["streams"]),
        codec=video["codec_name"],
        frame_map=str(frame_map),
    )


def make_proxy(
    file: BinaryIO,
    output: Path,
    timeline: Timeline,
    *,
    threads: int = 2,
    progress: Progress | None = None,
) -> dict:
    temporary = output.with_name(f".{output.stem}.{uuid.uuid4().hex}.partial.mp4")
    origin = seconds(to_us(timeline.first_pts * Fraction(timeline.time_base)))
    run_media(
        [
            "ffmpeg",
            "-filter_threads",
            str(settings().media_threads),
            "-v",
            "error",
            "-nostdin",
            "-y",
            "-copyts",
            *source_args(file),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-vf",
            f"setpts=PTS-{timeline.first_pts},scale=w='min(960,iw)':h='min(540,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",
            "-af",
            f"asetpts=PTS-{origin}/TB,aresample=async=1:first_pts=0",
            "-fps_mode",
            "passthrough",
            "-enc_time_base:v",
            timeline.time_base,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "27",
            "-pix_fmt",
            "yuv420p",
            "-threads",
            str(threads),
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-movflags",
            "+faststart",
            str(temporary),
        ],
        source=file,
        progress=progress,
    )
    with temporary.open("rb") as proxy:
        result = probe(proxy)
    os.replace(temporary, output)
    return result


def proxy_mapping(source: Timeline, proxy: Timeline) -> dict:
    """Pair decoded ordinals only after verifying one-to-one frame preservation."""
    if source.frame_count != proxy.frame_count:
        raise MediaError("Proxy changed frame count; a verified timing map is required")
    maximum_error_us = 0
    with (
        gzip.open(source.frame_map, "rt") as originals,
        gzip.open(proxy.frame_map, "rt") as previews,
    ):
        for raw_original, raw_preview in zip(originals, previews, strict=True):
            original, preview = json.loads(raw_original), json.loads(raw_preview)
            source_us = pts_to_us(original["pts"], source.time_base, source.first_pts)
            proxy_us = pts_to_us(preview["pts"], proxy.time_base, proxy.first_pts)
            maximum_error_us = max(maximum_error_us, abs(source_us - proxy_us))
    if maximum_error_us > 2000:
        raise MediaError("Proxy timing drift exceeds the 2 ms mapping tolerance")
    return {
        "version": "pts-map-v1",
        "method": "verified-frame-ordinal-pairs",
        "source_frame_map": source.frame_map,
        "proxy_frame_map": proxy.frame_map,
        "source_origin_pts": source.first_pts,
        "source_time_base": source.time_base,
        "proxy_origin_pts": proxy.first_pts,
        "proxy_time_base": proxy.time_base,
        "maximum_error_us": maximum_error_us,
        "source_duration_us": source.duration_us,
        "proxy_duration_us": proxy.duration_us,
        "tail_difference_us": source.duration_us - proxy.duration_us,
    }


def detect_shots(proxy: Path, duration_us: int, progress=None) -> list[Interval]:
    response = run_media(
        [sys.executable, "-m", "rushes.scene_detect", str(proxy), str(duration_us)],
        progress=progress,
    )
    return [Interval.model_validate(row) for row in json.loads(response)]


def thumbnail(proxy: Path, output: Path, at_us: int = 0):
    run_media(
        [
            "ffmpeg",
            "-filter_threads",
            str(settings().media_threads),
            "-v",
            "error",
            "-nostdin",
            "-y",
            "-ss",
            seconds(at_us),
            "-i",
            str(proxy),
            "-frames:v",
            "1",
            "-vf",
            "scale=480:-2",
            str(output),
        ],
        timeout=60,
    )


def render_clip(
    file: BinaryIO,
    timeline: Timeline,
    interval: Interval,
    output: Path,
    *,
    threads: int = 2,
    progress: Progress | None = None,
) -> dict:
    interval.within(timeline.duration_us)
    temporary = output.with_name(f".{output.stem}.{uuid.uuid4().hex}.partial.mp4")
    first, last = selected_frames(
        timeline.frame_map, timeline.time_base, timeline.first_pts, interval
    )
    # trim uses the source time base, so rounded browser seconds never choose the render frames.
    end_pts = last["pts"] + 1
    filters = f"trim=start_pts={first['pts']}:end_pts={end_pts},setpts=PTS-STARTPTS"
    args = [
        "ffmpeg",
        "-filter_threads",
        str(settings().media_threads),
        "-v",
        "error",
        "-nostdin",
        "-y",
        "-copyts",
        "-noaccurate_seek",
        "-seek_timestamp",
        "1",
        "-ss",
        seconds(
            max(
                to_us(timeline.first_pts * Fraction(timeline.time_base)),
                to_us(first["pts"] * Fraction(timeline.time_base)) - 2_000_000,
            )
        ),
        *source_args(file),
        "-map",
        "0:v:0",
        "-vf",
        filters,
        "-fps_mode",
        "passthrough",
        "-enc_time_base:v",
        timeline.time_base,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        # Full-resolution lookahead can evict the shared web process on small hosts.
        # Set buffering explicitly: zerolatency's force-CFR option would change VFR timing.
        "-x264-params",
        "rc-lookahead=0:sync-lookahead=0:bframes=0:ref=1",
        "-pix_fmt",
        "yuv420p",
        "-threads",
        str(threads),
    ]
    if timeline.has_audio:
        # Source audio and video share the original PTS clock; retain their relative alignment.
        start = to_us(first["pts"] * Fraction(timeline.time_base))
        end = to_us(timeline.first_pts * Fraction(timeline.time_base)) + interval.end_us
        args += [
            "-map",
            "0:a:0",
            "-af",
            f"atrim=start={seconds(start)}:end={seconds(end)},asetpts=PTS-{seconds(start)}/TB",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
        ]
    args += ["-movflags", "+faststart", str(temporary)]
    run_media(args, source=file, progress=progress)
    with temporary.open("rb") as exported:
        result = probe(exported)
    if not result.get("streams") or not result.get("format", {}).get("duration"):
        temporary.unlink(missing_ok=True)
        raise MediaError("Rendered interval is empty; no completed output was recorded")
    os.replace(temporary, output)
    return {
        "requested": interval.model_dump(),
        "first_source_pts": first["pts"],
        "last_source_pts": last["pts"],
        "first_source_elapsed_us": pts_to_us(first["pts"], timeline.time_base, timeline.first_pts),
        "time_base": timeline.time_base,
        "selection": "frame presentation starts within half-open interval",
        "render": "accurate re-encode",
        "output_duration_seconds": result["format"]["duration"],
    }


def extract_audio(
    file: BinaryIO, timeline: Timeline, interval: Interval, output: Path, progress=None
):
    interval.within(timeline.duration_us)
    origin = to_us(timeline.first_pts * Fraction(timeline.time_base))
    start, end = seconds(origin + interval.start_us), seconds(origin + interval.end_us)
    run_media(
        [
            "ffmpeg",
            "-filter_threads",
            str(settings().media_threads),
            "-v",
            "error",
            "-nostdin",
            "-y",
            "-copyts",
            "-noaccurate_seek",
            "-seek_timestamp",
            "1",
            "-ss",
            seconds(origin + max(0, interval.start_us - 2_000_000)),
            *source_args(file),
            "-vn",
            "-map",
            "0:a:0",
            "-af",
            f"atrim=start={start}:end={end},asetpts=PTS-{start}/TB,aresample=async=1:first_pts=0",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(output),
        ],
        source=file,
        progress=progress,
    )
