"""Presentation-time arithmetic. All public intervals are half-open and in microseconds."""

import re
from fractions import Fraction

from pydantic import BaseModel, ConfigDict, model_validator

MICROSECONDS = 1_000_000


class Interval(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    start_us: int
    end_us: int

    @model_validator(mode="after")
    def valid(self):
        if self.start_us < 0 or self.end_us <= self.start_us:
            raise ValueError("Interval must satisfy 0 <= start < end")
        return self

    def within(self, duration_us: int) -> "Interval":
        if self.end_us > duration_us:
            raise ValueError("Interval extends beyond the media timeline")
        return self


def to_us(value: str | int | Fraction) -> int:
    return round(Fraction(value) * MICROSECONDS)


def seconds(us: int) -> str:
    sign = "-" if us < 0 else ""
    absolute = abs(us)
    return f"{sign}{absolute // MICROSECONDS}.{absolute % MICROSECONDS:06d}"


def pts_to_us(pts: int, time_base: str, origin_pts: int = 0) -> int:
    return to_us((pts - origin_pts) * Fraction(time_base))


def timecode(frame: int, rate: Fraction, drop_frame: bool = False) -> str:
    """Format a nonnegative index on an explicitly CFR timeline (24-hour wrap)."""
    if frame < 0 or rate <= 0:
        raise ValueError("Invalid CFR frame or rate")
    nominal = round(rate)
    if drop_frame:
        if rate not in (Fraction(30000, 1001), Fraction(60000, 1001)):
            raise ValueError("Drop-frame requires 30000/1001 or 60000/1001")
        dropped = 2 if nominal == 30 else 4
        per_minute = nominal * 60 - dropped
        per_ten = nominal * 600 - dropped * 9
        ten_minutes, remainder = divmod(frame, per_ten)
        frame += dropped * 9 * ten_minutes
        if remainder >= dropped:
            frame += dropped * ((remainder - dropped) // per_minute)
    hours, remainder = divmod(frame, nominal * 3600)
    minutes, remainder = divmod(remainder, nominal * 60)
    secs, frames = divmod(remainder, nominal)
    separator = ";" if drop_frame else ":"
    return f"{hours % 24:02d}:{minutes:02d}:{secs:02d}{separator}{frames:02d}"


def timecode_frame(value: str, rate: Fraction) -> int:
    match = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2})([:;])(\d{2})", value)
    if not match:
        raise ValueError("Source timecode format is unsupported")
    hours, minutes, secs, separator, frame = match.groups()
    h, m, s, f = int(hours), int(minutes), int(secs), int(frame)
    nominal = round(rate)
    if h >= 24 or m >= 60 or s >= 60 or f >= nominal:
        raise ValueError("Invalid source timecode")
    index = ((h * 60 + m) * 60 + s) * nominal + f
    if separator == ";":
        if rate not in (Fraction(30000, 1001), Fraction(60000, 1001)):
            raise ValueError("Drop-frame timecode requires an NTSC rate")
        dropped = 2 if nominal == 30 else 4
        if m % 10 and s == 0 and f < dropped:
            raise ValueError("Source timecode uses a dropped frame number")
        total_minutes = h * 60 + m
        index -= dropped * (total_minutes - total_minutes // 10)
    return index


def bounded_windows(
    duration_us: int, cuts_us: list[int], maximum_us: int, overlap_us: int = 1_000_000
) -> list[Interval]:
    if not 0 <= overlap_us < maximum_us:
        raise ValueError("Overlap must be smaller than the window")
    windows = []
    start = 0
    cuts = sorted(set(c for c in cuts_us if 0 < c < duration_us))
    while start < duration_us:
        ceiling = min(start + maximum_us, duration_us)
        candidates = [c for c in cuts if start + maximum_us // 2 <= c <= ceiling]
        end = candidates[-1] if candidates and ceiling < duration_us else ceiling
        windows.append(Interval(start_us=start, end_us=end))
        if end == duration_us:
            break
        start = end - overlap_us
    return windows
