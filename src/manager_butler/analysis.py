from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Iterable, List, Tuple

from .models import Event


def find_compatible_artists(events: Iterable[Event], target_genre: str) -> List[Tuple[Event, float]]:
    target = target_genre.lower()
    scored = []
    for event in events:
        score = _genre_similarity(event, target)
        scored.append((event, score))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored


def _genre_similarity(event: Event, target: str) -> float:
    text = " ".join([event.title] + event.artists).lower()
    tokens = set(text.replace("/", " ").replace(",", " ").split())
    hit = 1.0 if target in tokens else 0.0
    fuzz = sum(1 for token in tokens if target in token) * 0.1
    return hit + fuzz


def find_schedule_gaps(events: Iterable[Event], window_days: int = 30) -> dict[str, List[Tuple[datetime, datetime]]]:
    by_venue: dict[str, List[datetime]] = defaultdict(list)
    for event in events:
        if event.local_datetime:
            by_venue[event.venue].append(event.local_datetime)

    gaps: dict[str, List[Tuple[datetime, datetime]]] = {}
    now = datetime.utcnow()
    horizon = now + timedelta(days=window_days)

    for venue, dates in by_venue.items():
        if not dates:
            continue
        dates = sorted(dt for dt in dates if now <= dt <= horizon)
        venue_gaps: List[Tuple[datetime, datetime]] = []
        for earlier, later in zip(dates, dates[1:]):
            if later - earlier > timedelta(days=3):
                venue_gaps.append((earlier, later))
        gaps[venue] = venue_gaps
    return gaps