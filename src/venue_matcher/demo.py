"""Demo mode: ships a small hand-authored dataset so new users can try the
tool without Google Places API keys, Ollama, or network access.

The `venue-match demo` command seeds a SQLite DB with fake venues, events, and
venue profiles in one region, then runs the opener-opportunity ranker against
a sample artist profile.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from .db import Database
from .models import ArtistProfile, Event, Venue, VenueProfile


SAMPLE_ARTIST = ArtistProfile(
    name="Demo Band",
    target_genres=["indie rock", "alternative", "post-punk"],
    audience_traits=["college-age", "local-scene"],
    target_capacity=400,
    min_capacity=150,
    max_capacity=800,
    preferred_regions=["TX"],
    support_slot_ready=True,
    available_dates=[],
)


def _sample_venues() -> list[tuple[Venue, VenueProfile, list[tuple[str, int, list[str]]]]]:
    """Return (venue, profile, [(event_title, days_from_now, artists)]) tuples."""
    return [
        (
            Venue(
                venue_id="demo-mohawk",
                name="The Mohawk (Demo)",
                website_url="https://example.com/mohawk",
                city="Austin",
                region="TX",
                timezone="America/Chicago",
                capacity_estimate=500,
                capacity_confidence=0.9,
            ),
            VenueProfile(
                venue_id="demo-mohawk",
                inferred_genres=["indie rock", "alternative", "garage rock"],
                audience_traits=["college-age", "local-scene"],
                booking_tier="emerging",
                typical_bill_style="three-band bill",
                support_friendliness=0.85,
                confidence=0.9,
                reasoning_summary="Demo profile for Mohawk-like indie rock venue.",
                evidence=["Headliner A", "Headliner B"],
            ),
            [
                ("Indie Headliner A", 21, ["Indie Headliner A"]),
                ("Rock Night with TBA support", 35, ["Rock Headliner", "TBA"]),
                ("Festival Showcase", 10, ["Band 1", "Band 2", "Band 3", "Band 4"]),
            ],
        ),
        (
            Venue(
                venue_id="demo-parish",
                name="The Parish (Demo)",
                website_url="https://example.com/parish",
                city="Austin",
                region="TX",
                timezone="America/Chicago",
                capacity_estimate=425,
                capacity_confidence=0.85,
            ),
            VenueProfile(
                venue_id="demo-parish",
                inferred_genres=["indie rock", "post-punk", "electronic"],
                audience_traits=["music-fans", "active-regulars"],
                booking_tier="emerging",
                typical_bill_style="two-band bill",
                support_friendliness=0.8,
                confidence=0.85,
                reasoning_summary="Demo profile for a mid-capacity Austin indie venue.",
                evidence=["Show 1", "Show 2"],
            ),
            [
                ("Post-Punk Night — headliner TBA", 28, ["TBA"]),
                ("Sold Out: Big Indie Act", 14, ["Big Indie Act"]),
                ("Single Headliner Night", 42, ["One Band"]),
            ],
        ),
        (
            Venue(
                venue_id="demo-empire",
                name="Empire Control Room (Demo)",
                website_url="https://example.com/empire",
                city="Austin",
                region="TX",
                timezone="America/Chicago",
                capacity_estimate=350,
                capacity_confidence=0.8,
            ),
            VenueProfile(
                venue_id="demo-empire",
                inferred_genres=["electronic", "indie rock", "hip-hop"],
                audience_traits=["college-age"],
                booking_tier="emerging",
                typical_bill_style="single headliner with openers",
                support_friendliness=0.75,
                confidence=0.8,
                reasoning_summary="Demo profile for a versatile small venue.",
                evidence=["Event X", "Event Y"],
            ),
            [
                ("Alt Rock Showcase", 49, ["Headliner"]),
                ("Indie Night w/ special guest", 56, ["Main Act"]),
            ],
        ),
        (
            Venue(
                venue_id="demo-stubbs",
                name="Stubb's Indoor (Demo)",
                website_url="https://example.com/stubbs",
                city="Austin",
                region="TX",
                timezone="America/Chicago",
                capacity_estimate=2200,
                capacity_confidence=0.95,
            ),
            VenueProfile(
                venue_id="demo-stubbs",
                inferred_genres=["rock", "country", "indie"],
                audience_traits=["tourists", "active-regulars"],
                booking_tier="premium",
                typical_bill_style="headliner + one opener",
                support_friendliness=0.5,
                confidence=0.95,
                reasoning_summary="Demo profile for a large venue — probably too big.",
                evidence=["Famous Act 1"],
            ),
            [
                ("Famous Act Live", 60, ["Famous Act", "Established Opener"]),
            ],
        ),
        (
            Venue(
                venue_id="demo-barracuda",
                name="Barracuda Backroom (Demo)",
                website_url="https://example.com/barracuda",
                city="Austin",
                region="TX",
                timezone="America/Chicago",
                capacity_estimate=180,
                capacity_confidence=0.7,
            ),
            VenueProfile(
                venue_id="demo-barracuda",
                inferred_genres=["punk", "indie rock", "alternative"],
                audience_traits=["local-scene", "diy"],
                booking_tier="diy",
                typical_bill_style="diy three-band bill",
                support_friendliness=0.95,
                confidence=0.75,
                reasoning_summary="Demo DIY venue open to local openers.",
                evidence=["Local Band A"],
            ),
            [
                ("DIY Night — openers TBA", 17, ["Local Band A", "TBA"]),
                ("Punk Showcase", 31, ["Band 1", "Band 2"]),
            ],
        ),
    ]


def seed_demo_db(db_path: Path) -> Database:
    """Create a fresh demo DB (wipes any existing file at db_path)."""
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path)

    now = datetime.now(timezone.utc)
    for venue, profile, events in _sample_venues():
        db.upsert_venue(venue)
        db.upsert_profile(profile)
        event_objs = []
        for title, days_out, artists in events:
            dt = now + timedelta(days=days_out)
            event_objs.append(
                Event(
                    venue_id=venue.venue_id,
                    source_url=venue.website_url or "https://example.com/",
                    title=title,
                    start_dt=dt,
                    timezone=venue.timezone,
                    url=f"{venue.website_url}/event/{title.replace(' ', '-')}",
                    artists=artists,
                    status="scheduled",
                )
            )
        db.upsert_events(event_objs)
    return db
