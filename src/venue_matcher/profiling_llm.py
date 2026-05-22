"""LLM-based venue profile inference.

Uses a local Ollama server to infer venue genre, audience, and booking tier from
scraped event titles. Falls back to a heuristic profile if Ollama is unreachable.

Environment variables:
    OLLAMA_HOST           Ollama server URL (default: http://localhost:11434)
    OLLAMA_MODEL_PROFILE  Model to use (default: qwen3:14b)

To install Ollama and pull the default model:
    https://ollama.ai
    ollama pull qwen3:14b
"""
from __future__ import annotations

import json
import os
import sys

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

_OLLAMA_WARNED = False


def _check_ollama_available(host: str) -> tuple[bool, str]:
    """Quick health check — returns (available, error_message)."""
    try:
        response = httpx.get(f"{host}/api/tags", timeout=3.0)
        if response.status_code == 200:
            return True, ""
        return False, f"Ollama returned HTTP {response.status_code}"
    except httpx.ConnectError:
        return False, f"Could not connect to Ollama at {host}"
    except Exception as exc:
        return False, f"Ollama check failed: {exc}"


def _warn_ollama_unavailable(reason: str) -> None:
    """Print a loud warning to stderr once per run explaining the fallback."""
    global _OLLAMA_WARNED
    if _OLLAMA_WARNED:
        return
    _OLLAMA_WARNED = True
    try:
        from rich.console import Console
        from rich.panel import Panel
        console = Console(stderr=True)
        console.print(Panel.fit(
            f"[bold yellow]Ollama unavailable — using heuristic fallback[/bold yellow]\n\n"
            f"[dim]{reason}[/dim]\n\n"
            f"Profiles will be low-confidence. To get proper LLM-based profiles:\n"
            f"  1. Install Ollama: [link]https://ollama.ai[/link]\n"
            f"  2. Pull the model:  [cyan]ollama pull qwen3:14b[/cyan]\n"
            f"  3. Verify it's running: [cyan]curl http://localhost:11434/api/tags[/cyan]",
            title="LLM Warning",
            border_style="yellow",
        ))
    except ImportError:
        print(f"WARNING: Ollama unavailable ({reason}). Using heuristic fallback.", file=sys.stderr)


def llm_infer_venue_profile(venue: Venue, recent_events: list[Event]) -> VenueProfile:
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL_PROFILE", "qwen3:14b")

    available, reason = _check_ollama_available(host)
    if not available:
        _warn_ollama_unavailable(reason)
        return _heuristic_profile(venue, recent_events, flagged=True)

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
    _warn_ollama_unavailable("Ollama reachable but generation failed after 2 attempts")
    return _heuristic_profile(venue, recent_events, flagged=True)


def _heuristic_profile(venue: Venue, recent_events: list[Event], flagged: bool = False) -> VenueProfile:
    corpus = " ".join([event.title + " " + " ".join(event.artists) for event in recent_events]).lower()
    genres = []
    for genre in ["indie", "rock", "punk", "metal", "jazz", "electronic", "hip-hop", "folk", "country", "pop"]:
        if genre in corpus:
            genres.append(genre)
    audience = ["local-scene"] if len(recent_events) < 15 else ["active-regulars"]
    reasoning = "Deterministic fallback based on event-title token frequencies and capacity heuristics."
    if flagged:
        reasoning = "HEURISTIC FALLBACK (install Ollama for better results). " + reasoning
    return VenueProfile(
        venue_id=venue.venue_id,
        inferred_genres=genres[:5],
        audience_traits=audience,
        booking_tier="emerging" if (venue.capacity_estimate or 0) < 500 else "mid",
        typical_bill_style="multi-band showcase",
        support_friendliness=0.7,
        confidence=0.35,
        reasoning_summary=reasoning,
        evidence=[event.title for event in recent_events[:5]],
    )
