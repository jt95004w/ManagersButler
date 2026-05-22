from __future__ import annotations

from zoneinfo import ZoneInfo

from ..models import Event


def normalize_event_datetimes(events: list[Event], venue_timezone: str | None) -> list[Event]:
    normalized: list[Event] = []
    tz = ZoneInfo(venue_timezone) if venue_timezone else None
    for event in events:
        data = event.model_copy(deep=True)
        if data.start_dt and data.start_dt.tzinfo is None and tz is not None:
            data.start_dt = data.start_dt.replace(tzinfo=tz)
            data.timezone = venue_timezone
        if data.end_dt and data.end_dt.tzinfo is None and tz is not None:
            data.end_dt = data.end_dt.replace(tzinfo=tz)
        normalized.append(data)
    return normalized
