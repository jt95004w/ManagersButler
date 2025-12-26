from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional
from urllib.parse import urljoin

import dateparser
import requests
from selectolax.parser import HTMLParser

from .models import Event, Venue


USER_AGENT = "ManagersButler/0.1 (contact: you@example.com)"


def fetch_html(url: str, *, timeout: float = 15.0) -> str:
    response = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.text


def parse_events(html: str, venue: Venue) -> List[Event]:
    tree = HTMLParser(html)
    events: List[Event] = []

    for node in tree.css(venue.list_selector):
        title_node = node.css_first(venue.title_selector)
        date_node = node.css_first(venue.date_selector)
        if not title_node or not date_node:
            continue

        title = title_node.text(strip=True)
        date_text = date_node.text(strip=True)
        local_dt = _parse_datetime(date_text, venue.timezone)
        artists = _extract_artists(node, venue) or [title]
        detail_url = _extract_url(node, venue.detail_url_selector, venue.url)

        events.append(
            Event(
                venue=venue.name,
                title=title,
                artists=artists,
                datetime_utc=local_dt if local_dt else None,
                local_datetime=local_dt,
                timezone=venue.timezone,
                url=detail_url,
                location=venue.location,
                raw_html=node.html,
            )
        )

    return events


def _parse_datetime(text: str, timezone: Optional[str]) -> Optional[datetime]:
    settings = {
        "RETURN_AS_TIMEZONE_AWARE": True,
        "TIMEZONE": timezone,
    }
    dt = dateparser.parse(text, settings=settings)
    return dt


def _extract_artists(node, venue: Venue) -> List[str]:
    if venue.artist_selector:
        return [n.text(strip=True) for n in node.css(venue.artist_selector) if n.text(strip=True)]
    return []


def _extract_url(node, selector: Optional[str], base_url: str) -> Optional[str]:
    if selector:
        url_node = node.css_first(selector)
        if url_node and (href := url_node.attributes.get("href")):
            return urljoin(base_url, href)
    return None


def scrape(venues: Iterable[Venue]) -> List[Event]:
    results: List[Event] = []
    for venue in venues:
        html = fetch_html(venue.url)
        events = parse_events(html, venue)
        results.extend(events)
    return results