from __future__ import annotations

import json
import os

import httpx

from .models import Event, Venue, VenueProfile

VENUE_PROFILE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["inferred_genres", "audience_traits", "booking_tier", "typical_bill_style", "support_friendliness", "confidence", "reasoning_summary", "evidence"],
    "properties": {
        "inferred_genres": {"type": "array", "items": {"type": "string"}},
        "audience_traits": {"type": "array", "items": {"type": "string"}},
        "booking_tier": {"type": "string"},
        "typical_bill_style": {"type": "string"},
        "support_friendliness": {"type": "number"},
        "confidence": {"type": "number"},
        "reasoning_summary": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
}


def llm_infer_venue_profile(venue: Venue, recent_events: list[Event]) -> VenueProfile:
    fallback = _heuristic_profile(venue, recent_events)
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL_PROFILE", "qwen3:14b")
    event_lines = [f"- {event.title} | artists={', '.join(event.artists)} | status={event.status or 'unknown'}" for event in recent_events[:25]]
    prompt = "Infer a music venue profile from event titles and artists. Do not invent facts outside the evidence. Return only JSON matching the schema."
    for _attempt in range(2):
        try:
            response = httpx.post(
                f"{host}/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt + "\nVenue: " + venue.name + "\n" + "\n".join(event_lines)}],
                    "format": VENUE_PROFILE_SCHEMA,
                    "stream": False,
                },
                timeout=45.0,
            )
            response.raise_for_status()
            content = response.json().get("message", {}).get("content", "{}")
            data = json.loads(content)
            return VenueProfile(venue_id=venue.venue_id, **data)
        except Exception:
            prompt = "STRICT JSON ONLY. Required keys must all be present. " + prompt
    return fallback


def _heuristic_profile(venue: Venue, recent_events: list[Event]) -> VenueProfile:
    corpus = " ".join([event.title + " " + " ".join(event.artists) for event in recent_events]).lower()
    genres = []
    for genre in ["indie", "rock", "punk", "metal", "jazz", "electronic", "hip-hop", "folk", "country", "pop"]:
        if genre in corpus:
            genres.append(genre)
    audience = ["local-scene"] if len(recent_events) < 15 else ["active-regulars"]
    return VenueProfile(
        venue_id=venue.venue_id,
        inferred_genres=genres[:5],
        audience_traits=audience,
        booking_tier="emerging" if (venue.capacity_estimate or 0) < 500 else "mid",
        typical_bill_style="multi-band showcase",
        support_friendliness=0.7,
        confidence=0.35,
        reasoning_summary="Deterministic fallback based on event-title token frequencies and capacity heuristics.",
        evidence=[event.title for event in recent_events[:5]],
    )
