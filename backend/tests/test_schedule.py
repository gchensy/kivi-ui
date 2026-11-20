"""Monitor schedules and alert levels: pure functions, no database."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from kivi_ui.config import Settings, get_settings
from kivi_ui.monitoring.checks import DEFAULT_THRESHOLDS, KINDS, level_of
from kivi_ui.monitoring.schedule import Schedule, next_run, zone

SHANGHAI = ZoneInfo("Asia/Shanghai")
BERLIN = ZoneInfo("Europe/Berlin")


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


def local(tz: ZoneInfo, *args) -> datetime:
    return datetime(*args, tzinfo=tz).astimezone(UTC)


# ---- next_run -------------------------------------------------------------------------------------


def test_manual_schedules_have_no_next_run():
    assert next_run({"freq": "manual"}) is None
    assert next_run(Schedule(freq="manual", hour=3), utc(2026, 1, 1)) is None


def test_hourly_runs_at_the_minute_strictly_after():
    hourly = {"freq": "hourly", "minute": 5}
    after = local(SHANGHAI, 2026, 11, 20, 10, 3)
    got = next_run(hourly, after, tz=SHANGHAI)
    assert got == local(SHANGHAI, 2026, 11, 20, 10, 5) == utc(2026, 11, 20, 2, 5)
    assert got.tzinfo is UTC
    # Exactly on time, or a moment after, means the next hour.
    assert next_run(hourly, got, tz=SHANGHAI) == utc(2026, 11, 20, 3, 5)
    assert next_run(hourly, got + timedelta(microseconds=1), tz=SHANGHAI) == utc(2026, 11, 20, 3, 5)
    assert next_run(hourly, utc(2026, 11, 20, 2, 59, 59), tz=SHANGHAI) == utc(2026, 11, 20, 3, 5)
    # Across midnight and the end of a month.
    assert next_run(hourly, local(SHANGHAI, 2026, 11, 30, 23, 30), tz=SHANGHAI) == local(
        SHANGHAI, 2026, 12, 1, 0, 5
    )


def test_daily_runs_at_the_local_time():
    daily = Schedule(freq="daily", hour=6, minute=0)
    # 06:00 in Shanghai is 22:00 UTC the day before.
    assert next_run(daily, local(SHANGHAI, 2026, 11, 20, 5, 59), tz=SHANGHAI) == utc(2026, 11, 19, 22)
    assert next_run(daily, utc(2026, 11, 19, 22), tz=SHANGHAI) == utc(2026, 11, 20, 22)
    assert next_run(daily, local(SHANGHAI, 2026, 11, 20, 23, 0), tz=SHANGHAI) == utc(2026, 11, 20, 22)
    # The year boundary.
    assert next_run(daily, local(SHANGHAI, 2026, 12, 31, 7), tz=SHANGHAI) == local(SHANGHAI, 2027, 1, 1, 6)
    # An `after` in another zone is the same instant.
    after = datetime(2026, 11, 20, 0, 0, tzinfo=BERLIN)  # 07:00 in Shanghai
    assert next_run(daily, after, tz=SHANGHAI) == local(SHANGHAI, 2026, 11, 21, 6)


def test_weekly_honours_the_weekday():
    assert datetime(2026, 11, 20).weekday() == 4  # a Friday
    monday = {"freq": "weekly", "weekday": 0, "hour": 9, "minute": 30}
    got = next_run(monday, local(SHANGHAI, 2026, 11, 20, 12), tz=SHANGHAI)
    assert got == local(SHANGHAI, 2026, 11, 23, 9, 30) == utc(2026, 11, 23, 1, 30)
    assert got.astimezone(SHANGHAI).weekday() == 0
    assert next_run(monday, got - timedelta(minutes=1), tz=SHANGHAI) == got
    assert next_run(monday, got, tz=SHANGHAI) == got + timedelta(days=7)
    friday = monday | {"weekday": 4}
    assert next_run(friday, local(SHANGHAI, 2026, 11, 20, 9), tz=SHANGHAI) == local(
        SHANGHAI, 2026, 11, 20, 9, 30
    )
    assert next_run(friday, local(SHANGHAI, 2026, 11, 20, 10), tz=SHANGHAI) == local(
        SHANGHAI, 2026, 11, 27, 9, 30
    )
    # Sunday is 6; 23:59 the Saturday before is local, not UTC.
    sunday = {"freq": "weekly", "weekday": 6, "hour": 0, "minute": 0}
    assert next_run(sunday, local(SHANGHAI, 2026, 11, 21, 23, 59), tz=SHANGHAI) == local(
        SHANGHAI, 2026, 11, 22
    )


def test_next_run_defaults_to_now_and_the_configured_zone(monkeypatch):
    before = datetime.now(UTC)
    got = next_run({"freq": "hourly", "minute": 0})
    assert before < got <= before + timedelta(hours=1) and got.tzinfo is UTC
    assert zone().key == "Asia/Shanghai"
    assert next_run({"freq": "daily", "hour": 6}, utc(2026, 1, 10, 12)) == utc(2026, 1, 10, 22)

    monkeypatch.setenv("KIVI_TIMEZONE", "Europe/Berlin")
    get_settings.cache_clear()
    assert zone().key == "Europe/Berlin"
    assert next_run({"freq": "daily", "hour": 6}, utc(2026, 1, 10, 12)) == utc(2026, 1, 11, 5)
    with pytest.raises(ValidationError, match="not a known time zone"):
        Settings(timezone="Mars/Olympus_Mons")


def test_daily_and_weekly_keep_the_wall_clock_across_daylight_saving():
    daily = {"freq": "daily", "hour": 6, "minute": 0}
    # Spring forward on Sunday 29 March 2026: 06:00 is 05:00 UTC before and 04:00 UTC after.
    assert next_run(daily, utc(2026, 3, 27, 6), tz=BERLIN) == utc(2026, 3, 28, 5)
    spring = next_run(daily, utc(2026, 3, 28, 6), tz=BERLIN)
    assert spring == utc(2026, 3, 29, 4)
    assert (spring.astimezone(BERLIN).hour, spring.astimezone(BERLIN).minute) == (6, 0)
    # Fall back on Sunday 25 October 2026.
    assert next_run(daily, utc(2026, 10, 24, 5), tz=BERLIN) == utc(2026, 10, 25, 5)
    weekly = {"freq": "weekly", "weekday": 0, "hour": 6, "minute": 0}
    autumn = next_run(weekly, utc(2026, 10, 23, 12), tz=BERLIN)
    assert autumn == utc(2026, 10, 26, 5) and autumn.astimezone(BERLIN).hour == 6
    assert next_run(weekly, utc(2026, 3, 27, 12), tz=BERLIN) == utc(2026, 3, 30, 4)


def test_the_repeated_hour_when_clocks_go_back():
    # 02:00-03:00 happens twice in Berlin on 25 October 2026: 00:00-01:00 and 01:00-02:00 UTC.
    daily = {"freq": "daily", "hour": 2, "minute": 30}
    assert next_run(daily, utc(2026, 10, 24, 23), tz=BERLIN) == utc(2026, 10, 25, 0, 30)
    for after in (utc(2026, 10, 25, 0, 30), utc(2026, 10, 25, 1, 15), utc(2026, 10, 25, 1, 45)):
        got = next_run(daily, after, tz=BERLIN)
        assert got > after and got == utc(2026, 10, 26, 1, 30), after
    # Hourly runs once per real hour through both nights.
    hourly = {"freq": "hourly", "minute": 30}
    for start in (utc(2026, 10, 24, 22), utc(2026, 3, 28, 22)):
        t, runs = start, []
        for _ in range(6):
            t = next_run(hourly, t, tz=BERLIN)
            runs.append(t)
        assert [b - a for a, b in zip(runs, runs[1:], strict=False)] == [timedelta(hours=1)] * 5
        assert all(r.astimezone(BERLIN).minute == 30 for r in runs)


def test_schedules_are_validated():
    assert Schedule().model_dump() == {"freq": "daily", "hour": 6, "minute": 0, "weekday": 0}
    for bad in ({"freq": "yearly"}, {"hour": 24}, {"minute": -1}, {"weekday": 7}, {"cron": "* * * * *"}):
        with pytest.raises(ValidationError):
            next_run(bad)


# ---- level_of -------------------------------------------------------------------------------------


def test_levels_are_inclusive_at_the_thresholds():
    t = {"warn": 0.1, "alert": 0.25}
    assert [level_of("score_psi", v, t) for v in (0, 0.0999, 0.1, 0.2499, 0.25, 3.0)] == [
        "normal",
        "normal",
        "warn",
        "warn",
        "alert",
        "alert",
    ]
    assert level_of("score_psi", None, t) == level_of("approval_rate", None, t) == "normal"
    # Equal thresholds skip the warning level.
    assert level_of("indicator_psi", 0.2, {"warn": 0.2, "alert": 0.2}) == "alert"


def test_shift_checks_use_the_size_of_the_change():
    t = DEFAULT_THRESHOLDS["approval_rate"]
    assert [level_of("approval_rate", v, t) for v in (-0.2, -0.1, -0.05, -0.049, 0.049, 0.05, 0.1)] == [
        "alert",
        "alert",
        "warn",
        "normal",
        "normal",
        "warn",
        "alert",
    ]
    assert level_of("rule_hit_rate", -0.08, {"warn": 0.03, "alert": 0.08}) == "alert"
    # Other checks are one-sided: a KS that improved (a negative drop) is normal.
    assert level_of("model_ks", -0.5, DEFAULT_THRESHOLDS["model_ks"]) == "normal"
    assert level_of("score_psi", -1, {"warn": 0.1, "alert": 0.25}) == "normal"


def test_default_thresholds_cover_every_kind():
    assert set(DEFAULT_THRESHOLDS) == set(KINDS)
    assert all(0 < t["warn"] < t["alert"] for t in DEFAULT_THRESHOLDS.values())
