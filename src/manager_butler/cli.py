from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .analysis import find_compatible_artists, find_schedule_gaps
from .config import load_venues
from .db import EventStore
from .scraper import scrape

app = typer.Typer(help="Scrape venue calendars and analyze compatible artists/schedule gaps.")


@app.command()
def scrape_venues(
    config: Path = typer.Option(Path("venues.yaml"), help="Path to venue config YAML"),
    db_path: Path = typer.Option(Path("data/events.db"), help="SQLite database path"),
    genre: Optional[str] = typer.Option(None, help="Target genre for compatibility scoring"),
    window: int = typer.Option(30, help="Days forward to search for gaps"),
):
    """Scrape venues, persist events, and optionally print analysis."""

    venues = load_venues(config)
    events = scrape(venues)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = EventStore(db_path)
    store.upsert_events(events)

    typer.echo(f"Stored {len(events)} events across {len(venues)} venues → {db_path}")

    if genre:
        ranked = find_compatible_artists(events, genre)
        typer.echo("\nTop compatible artists:")
        for event, score in ranked[:10]:
            typer.echo(f"[{score:.1f}] {event.title} @ {event.venue} → {', '.join(event.artists)} ({event.url or 'no link'})")

    gaps = find_schedule_gaps(events, window_days=window)
    if gaps:
        typer.echo("\nUpcoming schedule gaps (>=3 days):")
        for venue, gap_list in gaps.items():
            if not gap_list:
                continue
            typer.echo(f"- {venue}")
            for start, end in gap_list:
                typer.echo(f"  * {start.date()} → {end.date()} ({(end-start).days} days)")


@app.command()
def dump_events(db_path: Path = typer.Option(Path("data/events.db"), help="SQLite database path")):
    """Print events currently saved in the SQLite database."""

    store = EventStore(db_path)
    events = store.list_events()
    for ev in events:
        typer.echo(f"{ev.local_datetime or ev.datetime_utc} | {ev.venue} | {ev.title} | {', '.join(ev.artists)}")


if __name__ == "__main__":
    app()