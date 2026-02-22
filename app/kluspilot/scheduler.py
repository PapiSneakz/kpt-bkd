from __future__ import annotations

from datetime import datetime, timedelta

OPEN_HOUR = 8
CLOSE_HOUR = 18


def _round_to_next_half_hour(dt: datetime) -> datetime:
    minute = dt.minute
    add = 0
    if minute == 0 or minute == 30:
        add = 0
    elif minute < 30:
        add = 30 - minute
    else:
        add = 60 - minute
    return (dt + timedelta(minutes=add)).replace(second=0, microsecond=0)


def generate_slots(
    now: datetime | None = None,
    days: int = 2,
    duration_minutes: int = 60,
) -> list[tuple[datetime, datetime]]:
    if now is None:
        now = datetime.utcnow()

    now = _round_to_next_half_hour(now)
    slots: list[tuple[datetime, datetime]] = []

    for d in range(days):
        day = (now + timedelta(days=d)).replace(hour=OPEN_HOUR, minute=0, second=0, microsecond=0)

        for hour in range(OPEN_HOUR, CLOSE_HOUR):
            start = day.replace(hour=hour)
            end = start + timedelta(minutes=duration_minutes)

            # skip past
            if start < now:
                continue

            # stay within hours
            if end.hour > CLOSE_HOUR or (end.hour == CLOSE_HOUR and end.minute > 0):
                continue

            slots.append((start, end))

    return slots


def pick_best(slots: list[tuple[datetime, datetime]], count: int = 3) -> list[tuple[datetime, datetime]]:
    return slots[:count]
