from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from .models import ArtistProfile, Event, ShowOpportunity, Venue, VenueProfile


W_CAPACITY = 0.45
W_BILL = 0.25
W_TIMING = 0.15
W_SUPPORT = 0.15


def score_show_opportunity(
    event: Event,
    venue: Venue,
    artist: ArtistProfile,
    profile: VenueProfile | None = None,
) -> ShowOpportunity | None:
    """Score a single event as an opener opportunity for the given artist.

    Returns None for past events.
    """
    now = datetime.now(timezone.utc)
    event_dt = event.start_dt
    if event_dt is None:
        return None
    if event_dt.tzinfo is None:
        event_dt = event_dt.replace(tzinfo=timezone.utc)
    if event_dt < now:
        return None

    capacity_fit = _capacity_fit(venue.capacity_estimate, artist.target_capacity, venue.capacity_confidence)
    bill_openness = _bill_openness(event)
    timing = _timing_score(event_dt, now, artist.available_dates)
    support = profile.support_friendliness if profile and profile.support_friendliness else 0.5

    total = W_CAPACITY * capacity_fit + W_BILL * bill_openness + W_TIMING * timing + W_SUPPORT * support

    reasons: list[str] = []
    flags: list[str] = []

    _build_reasons(reasons, flags, event, venue, artist, capacity_fit, bill_openness, timing, event_dt, now)

    headliner = event.artists[0] if event.artists else None

    return ShowOpportunity(
        event_id=event.event_id,
        venue_id=venue.venue_id,
        venue_name=venue.name,
        event_title=event.title,
        event_date=event.start_dt,
        event_url=event.url,
        headliner=headliner,
        listed_artists=list(event.artists),
        opportunity_score=round(total, 4),
        capacity_fit=round(capacity_fit, 4),
        bill_openness=round(bill_openness, 4),
        timing_score=round(timing, 4),
        venue_support_friendliness=round(support, 4),
        reasons=reasons,
        flags=flags,
    )


def rank_opportunities(opportunities: list[ShowOpportunity]) -> list[ShowOpportunity]:
    return sorted(opportunities, key=lambda o: (-o.opportunity_score, o.event_date or datetime.max))


def _capacity_fit(venue_capacity: int | None, artist_target: int | None, confidence: float) -> float:
    if venue_capacity is None or artist_target is None or artist_target <= 0:
        return 0.55 * max(0.2, confidence)
    ratio = venue_capacity / artist_target
    penalty = abs(math.log(ratio, 2))
    raw = math.exp(-(penalty ** 1.35))
    return max(0.0, min(1.0, raw * (0.35 + 0.65 * confidence)))


def _bill_openness(event: Event) -> float:
    artist_count = len(event.artists)
    if artist_count == 0:
        base = 0.7
    elif artist_count == 1:
        base = 0.85
    elif artist_count == 2:
        base = 0.5
    else:
        base = 0.15

    text = (event.title + " " + (event.description or "")).lower()

    if any(kw in text for kw in ("tba", "tbd", "support tba", "opener tbd", "opener tba", "w/ tba", "special guest")):
        base = min(1.0, base + 0.3)

    if any(kw in text for kw in ("sold out", "soldout")):
        base = max(0.0, base - 0.5)
    if any(kw in text for kw in ("festival", "private event", "cancelled", "canceled", "postponed")):
        base = max(0.0, base - 0.4)

    return max(0.0, min(1.0, base))


def _timing_score(event_dt: datetime, now: datetime, available_dates: list[str] | None = None) -> float:
    days_out = (event_dt - now).total_seconds() / 86400

    if days_out < 0:
        return 0.0
    elif days_out < 7:
        score = 0.15
    elif days_out < 14:
        score = 0.5
    elif days_out <= 70:
        score = 1.0
    elif days_out <= 112:
        score = 0.7
    else:
        score = 0.3

    if available_dates:
        date_str = event_dt.strftime("%Y-%m-%d")
        if date_str in available_dates:
            score = min(1.0, score + 0.2)

    return score


def _build_reasons(
    reasons: list[str],
    flags: list[str],
    event: Event,
    venue: Venue,
    artist: ArtistProfile,
    capacity_fit: float,
    bill_openness: float,
    timing: float,
    event_dt: datetime,
    now: datetime,
) -> None:
    days_out = (event_dt - now).total_seconds() / 86400
    weeks_out = days_out / 7

    artist_count = len(event.artists)
    if artist_count <= 1:
        reasons.append("Single headliner with no listed support")
    elif artist_count == 2:
        reasons.append("Small bill, may have room for opener")

    text = (event.title + " " + (event.description or "")).lower()
    if any(kw in text for kw in ("tba", "tbd", "special guest")):
        reasons.append("Open slot indicated (TBA/TBD/special guest)")

    if venue.capacity_estimate and artist.target_capacity:
        pct = int(capacity_fit * 100)
        reasons.append(f"Capacity fit {pct}% (venue {venue.capacity_estimate}, artist target {artist.target_capacity})")
    elif venue.capacity_estimate is None:
        flags.append("No capacity data for venue")

    if 14 <= days_out <= 70:
        reasons.append(f"{weeks_out:.0f} weeks out — good lead time")
    elif days_out < 7:
        flags.append("Show is less than 7 days away")
    elif days_out > 112:
        flags.append(f"Show is {weeks_out:.0f} weeks out — may be too far ahead")

    if any(kw in text for kw in ("sold out", "soldout")):
        flags.append("Sold out")
    if any(kw in text for kw in ("festival", "showcase")):
        flags.append("Festival/showcase event")
    if artist_count >= 3:
        flags.append(f"Bill appears full ({artist_count} artists listed)")
