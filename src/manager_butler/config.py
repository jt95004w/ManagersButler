from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

import yaml

from .models import Venue


def load_venues(path: Path | str) -> List[Venue]:
    data = yaml.safe_load(Path(path).read_text())
    venues: List[Venue] = []
    for item in data:
        venues.append(
            Venue(
                name=item["name"],
                url=item["url"],
                list_selector=item["list_selector"],
                title_selector=item["title_selector"],
                date_selector=item["date_selector"],
                artist_selector=item.get("artist_selector"),
                detail_url_selector=item.get("detail_url_selector"),
                timezone=item.get("timezone"),
                location=item.get("location"),
            )
        )
    return venues


def save_venues(path: Path | str, venues: Iterable[Venue]) -> None:
    serializable = [
        {
            "name": v.name,
            "url": v.url,
            "list_selector": v.list_selector,
            "title_selector": v.title_selector,
            "date_selector": v.date_selector,
            "artist_selector": v.artist_selector,
            "detail_url_selector": v.detail_url_selector,
            "timezone": v.timezone,
            "location": v.location,
        }
        for v in venues
    ]
    Path(path).write_text(yaml.safe_dump(serializable, sort_keys=False))