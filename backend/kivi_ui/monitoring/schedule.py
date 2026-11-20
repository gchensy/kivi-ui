"""Monitor schedules: hourly, daily or weekly at a local time, or manual only.

A schedule is a small JSON object, for example ``{"freq": "daily", "hour": 6, "minute": 0}``.
Times are read in ``KIVI_TIMEZONE`` and stored in UTC.
"""

from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from ..config import get_settings

Freq = Literal["hourly", "daily", "weekly", "manual"]


class Schedule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    freq: Freq = "daily"
    hour: int = Field(6, ge=0, le=23)
    minute: int = Field(0, ge=0, le=59)
    weekday: int = Field(0, ge=0, le=6, description="0 is Monday")


def zone() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def next_run(
    schedule: Schedule | dict, after: datetime | None = None, tz: ZoneInfo | None = None
) -> datetime | None:
    """The first scheduled time strictly after `after` (UTC), or None for manual monitors."""
    s = schedule if isinstance(schedule, Schedule) else Schedule.model_validate(schedule)
    if s.freq == "manual":
        return None
    tz = tz or zone()
    after = (after or datetime.now(UTC)).astimezone(UTC)
    # Compare instants in UTC: two times in the same zone compare by wall clock, which misorders
    # the repeated hour when clocks go back.
    local_after = after.astimezone(tz)
    if s.freq == "hourly":
        candidate = local_after.replace(minute=s.minute, second=0, microsecond=0).astimezone(UTC)
        while candidate <= after:
            candidate += timedelta(hours=1)
        return candidate
    # Daily and weekly: walk local calendar days so daylight-saving changes keep the wall-clock time.
    day = local_after.date()
    for _ in range(15):
        local = datetime(day.year, day.month, day.day, s.hour, s.minute, tzinfo=tz)
        if local.astimezone(UTC) > after and (s.freq == "daily" or local.weekday() == s.weekday):
            return local.astimezone(UTC)
        day += timedelta(days=1)
    raise AssertionError("no run time found within two weeks")  # pragma: no cover
