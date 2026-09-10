from fractions import Fraction

import pytest
from pydantic import ValidationError
from rushes.timing import Interval, bounded_windows, pts_to_us, timecode


@pytest.mark.parametrize("start,end", [(-1, 5), (5, 5), (7, 4)])
def test_reject_invalid_intervals(start, end):
    with pytest.raises(ValidationError):
        Interval(start_us=start, end_us=end)


def test_duration_boundary():
    assert Interval(start_us=0, end_us=10).within(10).end_us == 10
    with pytest.raises(ValueError):
        Interval(start_us=0, end_us=11).within(10)


def test_rational_long_duration():
    assert pts_to_us(30000 * 60 * 60 * 10, "1/30000") == 36_000_000_000
    assert pts_to_us(1001, "1/30000") == 33367
    assert pts_to_us(91001, "1/30000", 90000) == 33367


@pytest.mark.parametrize(
    "frame,expected",
    [
        (0, "00:00:00;00"),
        (1799, "00:00:59;29"),
        (1800, "00:01:00;02"),
        (17982, "00:10:00;00"),
        (107892, "01:00:00;00"),
        (2589408, "00:00:00;00"),
    ],
)
def test_drop_frame(frame, expected):
    assert timecode(frame, Fraction(30000, 1001), True) == expected


def test_60fps_drop_frame_and_non_drop():
    assert timecode(3600, Fraction(60000, 1001), True) == "00:01:00;04"
    assert timecode(24 * 3661 + 7, Fraction(24)) == "01:01:01:07"
    with pytest.raises(ValueError):
        timecode(0, Fraction(24), True)


def test_windows_cover_long_uncut_source_without_exceeding_limit():
    duration = 10 * 3600 * 1_000_000
    windows = bounded_windows(duration, [], 60_000_000)
    assert windows[0].start_us == 0
    assert windows[-1].end_us == duration
    assert all(w.end_us - w.start_us <= 60_000_000 for w in windows)
    assert all(a.end_us > b.start_us for a, b in zip(windows, windows[1:], strict=False))


def test_window_cut_aware_but_bounded():
    windows = bounded_windows(100_000_000, [40_000_000], 60_000_000)
    assert windows[0].end_us == 40_000_000
    assert windows[1].start_us == 39_000_000
