from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, List

from .models import Event


SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    venue TEXT NOT NULL,
    title TEXT NOT NULL,
    artists TEXT NOT NULL,
    datetime_utc TEXT,
    local_datetime TEXT,
    timezone TEXT,
    url TEXT,
    price TEXT,
    location TEXT,
    raw_html TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
"""


class EventStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute(SCHEMA)
        self.conn.commit()

    def upsert_events(self, events: Iterable[Event]) -> None:
        with self.conn:
            for event in events:
                self.conn.execute(
                    """
                    INSERT INTO events (
                        event_id, venue, title, artists, datetime_utc, local_datetime, timezone, url, price, location, raw_html, first_seen, last_seen
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(event_id) DO UPDATE SET
                        last_seen=excluded.last_seen,
                        raw_html=excluded.raw_html,
                        price=COALESCE(excluded.price, events.price),
                        location=COALESCE(excluded.location, events.location)
                    """,
                    (
                        event.event_id,
                        event.venue,
                        event.title,
                        ", ".join(event.artists),
                        event.datetime_utc.isoformat() if event.datetime_utc else None,
                        event.local_datetime.isoformat() if event.local_datetime else None,
                        event.timezone,
                        event.url,
                        event.price,
                        event.location,
                        event.raw_html,
                        event.first_seen.isoformat(),
                        event.last_seen.isoformat(),
                    ),
                )

    def list_events(self) -> List[Event]:
        cursor = self.conn.execute(
            "SELECT venue, title, artists, datetime_utc, local_datetime, timezone, url, price, location, raw_html, first_seen, last_seen FROM events"
        )
        events: List[Event] = []
        for row in cursor.fetchall():
            event = Event(
                venue=row[0],
                title=row[1],
                artists=[a.strip() for a in row[2].split(",")],
                datetime_utc=_parse_iso(row[3]),
                local_datetime=_parse_iso(row[4]),
                timezone=row[5],
                url=row[6],
                price=row[7],
                location=row[8],
                raw_html=row[9],
                first_seen=_parse_iso(row[10]),
                last_seen=_parse_iso(row[11]),
            )
            events.append(event)
        return events

    def close(self) -> None:
        self.conn.close()


def _parse_iso(value):
    if not value:
        return None
    from datetime import datetime

    return datetime.fromisoformat(value)