from __future__ import annotations

from pathlib import Path

import yaml

from .db import Database
from .models import Venue


def import_from_yaml(path: Path | str, db: Database) -> list[Venue]:
    """Import venues from a YAML file into the database.

    Accepts both the original manager_butler format (url + CSS selectors)
    and extended venue_matcher fields (capacity, calendar_urls, city, region).
    """
    data = yaml.safe_load(Path(path).read_text())
    venues: list[Venue] = []
    for item in data:
        venue_id = item.get("venue_id") or item["name"].lower().replace(" ", "-").replace(":", "")
        city, region = _split_location(item.get("location", ""))
        calendar_urls = item.get("calendar_urls", [])
        if not calendar_urls and item.get("url"):
            calendar_urls = [item["url"]]
        css_rules = {}
        for key in ("list_selector", "title_selector", "date_selector", "artist_selector", "detail_url_selector", "url_selector"):
            if item.get(key):
                css_rules[key] = item[key]
        venue = Venue(
            venue_id=venue_id,
            name=item["name"],
            website_url=item.get("website_url") or item.get("url"),
            calendar_urls=calendar_urls,
            address=item.get("address"),
            city=item.get("city") or city,
            region=item.get("region") or region,
            timezone=item.get("timezone"),
            genres_hint=item.get("genres_hint", []),
            capacity_estimate=item.get("capacity_estimate"),
            capacity_min=item.get("capacity_min"),
            capacity_max=item.get("capacity_max"),
            capacity_type=item.get("capacity_type"),
            css_rules=css_rules,
        )
        db.upsert_venue(venue)
        venues.append(venue)
    return venues


def _split_location(location: str) -> tuple[str | None, str | None]:
    if not location:
        return None, None
    parts = [p.strip() for p in location.split(",") if p.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1].split()[0]
    if len(parts) == 1:
        return parts[0], None
    return None, None
