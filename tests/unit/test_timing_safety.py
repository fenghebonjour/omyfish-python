"""safety_ranges — groups flagged forecast hours into the warning ranges
shown on the Timing tab (e.g. "7:00 PM–8:00 PM: Heavy precipitation …")."""
from datetime import datetime, timedelta

from apps.omyfish_web.timing import safety_ranges

STORM = "Storm conditions reported — score suppressed; do not fish through lightning."
PRECIP = "Heavy precipitation — fishing not recommended this hour."


def _hours(*flags, start="2026-07-18T17:00:00"):
    t0 = datetime.fromisoformat(start)
    return [
        {"timestamp": (t0 + timedelta(hours=i)).isoformat(), "safety_flag": flag}
        for i, flag in enumerate(flags)
    ]


def test_single_flagged_hour_becomes_one_hour_range():
    ranges = safety_ranges(_hours(None, None, PRECIP, None))
    assert len(ranges) == 1
    r = ranges[0]
    assert r["message"] == PRECIP
    assert r["start"] == datetime(2026, 7, 18, 19, 0)
    assert r["end"] == datetime(2026, 7, 18, 20, 0)


def test_consecutive_same_flag_hours_merge():
    ranges = safety_ranges(_hours(PRECIP, PRECIP, PRECIP))
    assert len(ranges) == 1
    assert ranges[0]["start"] == datetime(2026, 7, 18, 17, 0)
    assert ranges[0]["end"] == datetime(2026, 7, 18, 20, 0)


def test_gap_splits_ranges():
    ranges = safety_ranges(_hours(PRECIP, None, PRECIP))
    assert len(ranges) == 2
    assert ranges[0]["end"] == datetime(2026, 7, 18, 18, 0)
    assert ranges[1]["start"] == datetime(2026, 7, 18, 19, 0)


def test_adjacent_different_flags_stay_separate():
    ranges = safety_ranges(_hours(PRECIP, STORM))
    assert [r["message"] for r in ranges] == [PRECIP, STORM]
    assert ranges[0]["end"] == ranges[1]["start"]


def test_no_flags_no_ranges():
    assert safety_ranges(_hours(None, None, None)) == []


def test_flag_running_to_end_of_day_is_closed():
    ranges = safety_ranges(_hours(None, STORM, STORM))
    assert len(ranges) == 1
    assert ranges[0]["end"] == datetime(2026, 7, 18, 20, 0)
