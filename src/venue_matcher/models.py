from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from hashlib import sha1


class ModelMixin:
    def model_dump(self):
        return asdict(self)

    @classmethod
    def model_validate(cls, data):
        return cls(**data)

    @classmethod
    def model_validate_json(cls, raw: str):
        return cls.model_validate(json.loads(raw))

    def model_copy(self, update: dict | None = None, deep: bool = False):
        payload = self.model_dump()
        if update:
            payload.update(update)
        return self.__class__.model_validate(copy.deepcopy(payload) if deep else payload)


@dataclass
class CapacitySource(ModelMixin):
    source_url: str
    source_path_hint: str | None = None
    extracted_value: int | None = None
    extracted_text_snippet: str = ""
    method: str = "regex"


@dataclass
class Venue(ModelMixin):
    venue_id: str
    name: str
    place_id: str | None = None
    website_url: str | None = None
    calendar_urls: list[str] = field(default_factory=list)
    address: str | None = None
    city: str | None = None
    region: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    timezone: str | None = None
    genres_hint: list[str] = field(default_factory=list)
    capacity_estimate: int | None = None
    capacity_min: int | None = None
    capacity_max: int | None = None
    capacity_type: str | None = None
    capacity_confidence: float = 0.0
    capacity_sources: list[CapacitySource] = field(default_factory=list)
    css_rules: dict = field(default_factory=dict)


@dataclass
class Event(ModelMixin):
    venue_id: str
    source_url: str
    title: str
    start_dt: datetime | None = None
    end_dt: datetime | None = None
    timezone: str | None = None
    url: str | None = None
    artists: list[str] = field(default_factory=list)
    status: str | None = None
    description: str | None = None
    raw: dict = field(default_factory=dict)

    @property
    def event_id(self) -> str:
        base = f"{self.venue_id}|{self.title}|{self.start_dt}|{self.url or self.source_url}"
        return sha1(base.encode("utf-8")).hexdigest()


@dataclass
class VenueProfile(ModelMixin):
    venue_id: str
    inferred_genres: list[str] = field(default_factory=list)
    audience_traits: list[str] = field(default_factory=list)
    booking_tier: str = "unknown"
    typical_bill_style: str = "unknown"
    support_friendliness: float = 0.0
    confidence: float = 0.0
    reasoning_summary: str = ""
    evidence: list[str] = field(default_factory=list)


@dataclass
class ArtistProfile(ModelMixin):
    name: str
    target_genres: list[str] = field(default_factory=list)
    audience_traits: list[str] = field(default_factory=list)
    target_capacity: int | None = None
    min_capacity: int | None = None
    max_capacity: int | None = None
    preferred_regions: list[str] = field(default_factory=list)
    support_slot_ready: bool = True
    available_dates: list[str] = field(default_factory=list)


@dataclass
class MatchScore(ModelMixin):
    venue_id: str
    venue_name: str
    total_score: float
    genre_score: float
    audience_score: float
    region_score: float
    tier_score: float
    capacity_fit: float
    data_quality: float
    evidence: list[str] = field(default_factory=list)


@dataclass
class ShowOpportunity(ModelMixin):
    event_id: str
    venue_id: str
    venue_name: str
    event_title: str
    event_date: datetime | None = None
    event_url: str | None = None
    headliner: str | None = None
    listed_artists: list[str] = field(default_factory=list)
    opportunity_score: float = 0.0
    capacity_fit: float = 0.0
    bill_openness: float = 0.0
    timing_score: float = 0.0
    venue_support_friendliness: float = 0.0
    reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
