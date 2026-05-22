from __future__ import annotations

import math

from .models import ArtistProfile, MatchScore, Venue, VenueProfile


def score_venue_for_artist(venue: Venue, profile: VenueProfile, artist: ArtistProfile) -> MatchScore:
    genre_score = _overlap(profile.inferred_genres, artist.target_genres)
    audience_score = _overlap(profile.audience_traits, artist.audience_traits)
    region_score = 1.0 if not artist.preferred_regions or (venue.region in artist.preferred_regions or venue.city in artist.preferred_regions) else 0.4
    tier_score = {"diy": 0.7, "emerging": 0.85, "mid": 0.75, "premium": 0.45}.get(profile.booking_tier, 0.5)
    capacity_fit = _capacity_fit(venue.capacity_estimate, artist.target_capacity, venue.capacity_confidence)
    data_quality = min(1.0, 0.4 + 0.3 * bool(venue.website_url) + 0.3 * bool(profile.evidence))
    if venue.capacity_estimate is None:
        data_quality = min(data_quality, 0.65)
    support_friendliness = profile.support_friendliness if profile.support_friendliness else 0.5
    total = 0.40 * capacity_fit + 0.15 * region_score + 0.10 * tier_score + 0.10 * data_quality + 0.10 * genre_score + 0.10 * audience_score + 0.05 * support_friendliness
    return MatchScore(
        venue_id=venue.venue_id,
        venue_name=venue.name,
        total_score=round(total, 4),
        genre_score=round(genre_score, 4),
        audience_score=round(audience_score, 4),
        region_score=round(region_score, 4),
        tier_score=round(tier_score, 4),
        capacity_fit=round(capacity_fit, 4),
        data_quality=round(data_quality, 4),
        evidence=list(dict.fromkeys((venue.calendar_urls or []) + profile.evidence))[:8],
    )


def rank_venues(match_scores: list[MatchScore]) -> list[MatchScore]:
    return sorted(match_scores, key=lambda item: (-item.total_score, -item.capacity_fit, item.venue_name.lower()))


def _overlap(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.5 if not b else 0.0
    sa = {x.lower() for x in a}
    sb = {x.lower() for x in b}
    return len(sa & sb) / len(sa | sb)


def _capacity_fit(venue_capacity: int | None, artist_target: int | None, confidence: float) -> float:
    if venue_capacity is None or artist_target is None or artist_target <= 0:
        return 0.55 * max(0.2, confidence)
    ratio = venue_capacity / artist_target
    penalty = abs(math.log(ratio, 2))
    raw = math.exp(-(penalty ** 1.35))
    return max(0.0, min(1.0, raw * (0.35 + 0.65 * confidence)))
