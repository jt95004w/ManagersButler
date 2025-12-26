from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha1
from typing import List, Optional


@dataclass
class Event:
    """Normalized event representation."""

    venue: str
    title: str
    artists: List[str]
    datetime_utc: Optional[datetime]
    local_datetime: Optional[datetime]
    timezone: Optional[str]
    url: Optional[str] = None
    price: Optional[str] = None
    location: Optional[str] = None
    raw_html: Optional[str] = None
    first_seen: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)

    @property
    def event_id(self) -> str:
        base = f"{self.venue}|{self.title}|{self.datetime_utc or self.local_datetime}|{self.url}"
        return sha1(base.encode("utf-8")).hexdigest()


@dataclass
class Venue:
    name: str
    url: str
    list_selector: str
    title_selector: str
    date_selector: str
    artist_selector: Optional[str] = None
    detail_url_selector: Optional[str] = None
    timezone: Optional[str] = None
    location: Optional[str] = None