from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import Event, MatchScore, ShowOpportunity, Venue, VenueProfile, CapacitySource

SCHEMA = """
CREATE TABLE IF NOT EXISTS venues (
    venue_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    place_id TEXT,
    website_url TEXT,
    calendar_urls TEXT,
    address TEXT,
    city TEXT,
    region TEXT,
    latitude REAL,
    longitude REAL,
    timezone TEXT,
    genres_hint TEXT,
    capacity_estimate INTEGER,
    capacity_min INTEGER,
    capacity_max INTEGER,
    capacity_type TEXT,
    capacity_confidence REAL,
    capacity_sources TEXT,
    css_rules TEXT
);
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    venue_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    title TEXT NOT NULL,
    start_dt TEXT,
    end_dt TEXT,
    timezone TEXT,
    url TEXT,
    artists TEXT,
    status TEXT,
    description TEXT,
    raw_json TEXT
);
CREATE TABLE IF NOT EXISTS venue_profiles (
    venue_id TEXT PRIMARY KEY,
    inferred_genres TEXT,
    audience_traits TEXT,
    booking_tier TEXT,
    typical_bill_style TEXT,
    support_friendliness REAL,
    confidence REAL,
    reasoning_summary TEXT,
    evidence TEXT
);
CREATE TABLE IF NOT EXISTS match_scores (
    venue_id TEXT PRIMARY KEY,
    venue_name TEXT NOT NULL,
    total_score REAL,
    genre_score REAL,
    audience_score REAL,
    region_score REAL,
    tier_score REAL,
    capacity_fit REAL,
    data_quality REAL,
    evidence TEXT
);
CREATE TABLE IF NOT EXISTS raw_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    venue_id TEXT,
    url TEXT,
    html TEXT,
    fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS extraction_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    venue_id TEXT,
    url TEXT,
    extractor TEXT,
    message TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS show_opportunities (
    event_id TEXT PRIMARY KEY,
    venue_id TEXT NOT NULL,
    venue_name TEXT NOT NULL,
    event_title TEXT NOT NULL,
    event_date TEXT,
    event_url TEXT,
    headliner TEXT,
    listed_artists TEXT,
    opportunity_score REAL,
    capacity_fit REAL,
    bill_openness REAL,
    timing_score REAL,
    venue_support_friendliness REAL,
    reasons TEXT,
    flags TEXT,
    scored_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def upsert_venue(self, venue: Venue) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT OR REPLACE INTO venues VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    venue.venue_id, venue.name, venue.place_id, venue.website_url, json.dumps(venue.calendar_urls), venue.address,
                    venue.city, venue.region, venue.latitude, venue.longitude, venue.timezone, json.dumps(venue.genres_hint),
                    venue.capacity_estimate, venue.capacity_min, venue.capacity_max, venue.capacity_type,
                    venue.capacity_confidence, json.dumps([source.model_dump() for source in venue.capacity_sources]),
                    json.dumps(venue.css_rules),
                ),
            )

    def upsert_events(self, events: list[Event]) -> None:
        with self.conn:
            for event in events:
                self.conn.execute(
                    """INSERT OR REPLACE INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (event.event_id, event.venue_id, event.source_url, event.title, _iso(event.start_dt), _iso(event.end_dt), event.timezone, event.url, json.dumps(event.artists), event.status, event.description, json.dumps(event.raw)),
                )

    def upsert_profile(self, profile: VenueProfile) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT OR REPLACE INTO venue_profiles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (profile.venue_id, json.dumps(profile.inferred_genres), json.dumps(profile.audience_traits), profile.booking_tier, profile.typical_bill_style, profile.support_friendliness, profile.confidence, profile.reasoning_summary, json.dumps(profile.evidence)),
            )

    def upsert_match_scores(self, scores: list[MatchScore]) -> None:
        with self.conn:
            for score in scores:
                self.conn.execute(
                    """INSERT OR REPLACE INTO match_scores VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (score.venue_id, score.venue_name, score.total_score, score.genre_score, score.audience_score, score.region_score, score.tier_score, score.capacity_fit, score.data_quality, json.dumps(score.evidence)),
                )

    def save_snapshot(self, venue_id: str, url: str, html: str) -> None:
        with self.conn:
            self.conn.execute("INSERT INTO raw_snapshots (venue_id, url, html) VALUES (?, ?, ?)", (venue_id, url, html))

    def log_extraction(self, venue_id: str, url: str, extractor: str, message: str) -> None:
        with self.conn:
            self.conn.execute("INSERT INTO extraction_logs (venue_id, url, extractor, message) VALUES (?, ?, ?, ?)", (venue_id, url, extractor, message))

    def load_venue(self, venue_id: str) -> Venue | None:
        row = self.conn.execute("SELECT * FROM venues WHERE venue_id = ?", (venue_id,)).fetchone()
        if not row:
            return None
        return Venue(
            venue_id=row[0], name=row[1], place_id=row[2], website_url=row[3], calendar_urls=json.loads(row[4] or '[]'),
            address=row[5], city=row[6], region=row[7], latitude=row[8], longitude=row[9], timezone=row[10], genres_hint=json.loads(row[11] or '[]'),
            capacity_estimate=row[12], capacity_min=row[13], capacity_max=row[14], capacity_type=row[15], capacity_confidence=row[16] or 0.0,
            capacity_sources=[CapacitySource.model_validate(item) for item in json.loads(row[17] or '[]')],
            css_rules=json.loads(row[18] or '{}'),
        )

    def load_all_venues(self) -> list[Venue]:
        rows = self.conn.execute("SELECT venue_id FROM venues").fetchall()
        return [v for vid in rows if (v := self.load_venue(vid[0]))]

    def load_future_events(self) -> list[Event]:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        rows = self.conn.execute(
            "SELECT venue_id, source_url, title, start_dt, end_dt, timezone, url, artists, status, description, raw_json FROM events WHERE start_dt >= ? ORDER BY start_dt",
            (now,),
        ).fetchall()
        return [Event(venue_id=r[0], source_url=r[1], title=r[2], start_dt=_dt(r[3]), end_dt=_dt(r[4]), timezone=r[5], url=r[6], artists=json.loads(r[7] or '[]'), status=r[8], description=r[9], raw=json.loads(r[10] or '{}')) for r in rows]

    def upsert_show_opportunities(self, opportunities: list[ShowOpportunity]) -> None:
        with self.conn:
            for opp in opportunities:
                self.conn.execute(
                    """INSERT OR REPLACE INTO show_opportunities (event_id, venue_id, venue_name, event_title, event_date, event_url, headliner, listed_artists, opportunity_score, capacity_fit, bill_openness, timing_score, venue_support_friendliness, reasons, flags) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (opp.event_id, opp.venue_id, opp.venue_name, opp.event_title, _iso(opp.event_date), opp.event_url, opp.headliner, json.dumps(opp.listed_artists), opp.opportunity_score, opp.capacity_fit, opp.bill_openness, opp.timing_score, opp.venue_support_friendliness, json.dumps(opp.reasons), json.dumps(opp.flags)),
                )

    def load_opportunities(self, min_score: float = 0.0, limit: int = 50) -> list[ShowOpportunity]:
        rows = self.conn.execute(
            "SELECT event_id, venue_id, venue_name, event_title, event_date, event_url, headliner, listed_artists, opportunity_score, capacity_fit, bill_openness, timing_score, venue_support_friendliness, reasons, flags FROM show_opportunities WHERE opportunity_score >= ? ORDER BY opportunity_score DESC LIMIT ?",
            (min_score, limit),
        ).fetchall()
        return [ShowOpportunity(event_id=r[0], venue_id=r[1], venue_name=r[2], event_title=r[3], event_date=_dt(r[4]), event_url=r[5], headliner=r[6], listed_artists=json.loads(r[7] or '[]'), opportunity_score=r[8], capacity_fit=r[9], bill_openness=r[10], timing_score=r[11], venue_support_friendliness=r[12], reasons=json.loads(r[13] or '[]'), flags=json.loads(r[14] or '[]')) for r in rows]

    def load_events_for_venue(self, venue_id: str) -> list[Event]:
        rows = self.conn.execute("SELECT venue_id, source_url, title, start_dt, end_dt, timezone, url, artists, status, description, raw_json FROM events WHERE venue_id = ? ORDER BY start_dt", (venue_id,)).fetchall()
        return [Event(venue_id=r[0], source_url=r[1], title=r[2], start_dt=_dt(r[3]), end_dt=_dt(r[4]), timezone=r[5], url=r[6], artists=json.loads(r[7] or '[]'), status=r[8], description=r[9], raw=json.loads(r[10] or '{}')) for r in rows]


def _iso(value):
    return value.isoformat() if value else None


def _dt(value):
    from datetime import datetime
    return datetime.fromisoformat(value) if value else None
