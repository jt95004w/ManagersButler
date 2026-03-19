from __future__ import annotations

import json
from typing import Any
from urllib.parse import urljoin

from dateparser import parse as parse_date
from selectolax.parser import HTMLParser

from ..models import Event


def extract_events_from_jsonld(html: str, source_url: str) -> list[Event]:
    tree = HTMLParser(html)
    events: list[Event] = []
    for node in tree.css('script[type="application/ld+json"]'):
        raw_text = node.text(strip=True)
        if not raw_text:
            continue
        for payload in _load_json_candidates(raw_text):
            for obj in _walk(payload):
                if _is_event(obj):
                    events.append(_event_from_jsonld(obj, source_url))
    return [event for event in events if event.title]


def _load_json_candidates(raw_text: str) -> list[Any]:
    try:
        loaded = json.loads(raw_text)
        return loaded if isinstance(loaded, list) else [loaded]
    except json.JSONDecodeError:
        return []


def _walk(obj: Any):
    if isinstance(obj, list):
        for item in obj:
            yield from _walk(item)
    elif isinstance(obj, dict):
        yield obj
        for key in ("@graph", "itemListElement", "mainEntity"):
            if key in obj:
                yield from _walk(obj[key])


def _is_event(obj: dict) -> bool:
    type_value = obj.get("@type")
    if isinstance(type_value, list):
        return "Event" in type_value or "MusicEvent" in type_value
    return type_value in {"Event", "MusicEvent"}


def _event_from_jsonld(obj: dict, source_url: str) -> Event:
    performers = obj.get("performer") or obj.get("organizer") or []
    if isinstance(performers, dict):
        performers = [performers]
    artists = [p.get("name") for p in performers if isinstance(p, dict) and p.get("name")]
    start_dt = parse_date(obj.get("startDate")) if obj.get("startDate") else None
    end_dt = parse_date(obj.get("endDate")) if obj.get("endDate") else None
    offers = obj.get("offers") or {}
    return Event(
        venue_id="unknown",
        source_url=source_url,
        title=obj.get("name", "").strip(),
        start_dt=start_dt,
        end_dt=end_dt,
        timezone=getattr(start_dt.tzinfo, 'key', None) if start_dt and start_dt.tzinfo else None,
        url=urljoin(source_url, obj.get("url", "")) if obj.get("url") else source_url,
        artists=artists,
        status=obj.get("eventStatus") or offers.get("availability"),
        description=obj.get("description"),
        raw=obj,
    )
