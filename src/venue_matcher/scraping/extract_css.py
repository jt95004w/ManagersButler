from __future__ import annotations

from urllib.parse import urljoin

from dateparser import parse as parse_date
from selectolax.parser import HTMLParser, Node

from ..models import Event


def extract_events_from_css(html: str, source_url: str, rules: dict) -> list[Event]:
    tree = HTMLParser(html)
    events: list[Event] = []
    for item in tree.css(rules["list_selector"]):
        title = _text(item, rules.get("title_selector"))
        if not title:
            continue
        date_text = _text(item, rules.get("date_selector"))
        link = _attr(item, rules.get("url_selector"), "href")
        artists = _texts(item, rules.get("artist_selector")) if rules.get("artist_selector") else []
        events.append(
            Event(
                venue_id=rules.get("venue_id", "unknown"),
                source_url=source_url,
                title=title,
                start_dt=parse_date(date_text) if date_text else None,
                url=urljoin(source_url, link) if link else source_url,
                artists=artists,
                raw={"date_text": date_text},
            )
        )
    return events


def _text(node: Node, selector: str | None) -> str:
    if not selector:
        return ""
    match = node.css_first(selector)
    return match.text(strip=True) if match else ""


def _texts(node: Node, selector: str | None) -> list[str]:
    if not selector:
        return []
    return [n.text(strip=True) for n in node.css(selector) if n.text(strip=True)]


def _attr(node: Node, selector: str | None, attr: str) -> str | None:
    if not selector:
        return None
    match = node.css_first(selector)
    return match.attributes.get(attr) if match else None
