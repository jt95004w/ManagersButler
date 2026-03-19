from __future__ import annotations

import json
import os
from pathlib import Path

import typer

from .capacity import infer_capacity
from .db import Database
from .models import ArtistProfile, Event, Venue, VenueProfile
from .places import places_place_details, places_text_search, require_api_key
from .profiling_llm import llm_infer_venue_profile
from .scoring import rank_venues, score_venue_for_artist
from .scraping.extract_css import extract_events_from_css
from .scraping.extract_jsonld import extract_events_from_jsonld
from .scraping.fetch import fetch_html
from .scraping.normalize import normalize_event_datetimes
from .website_discovery import can_fetch, discover_calendar_urls

app = typer.Typer(help="Discover venues, scrape calendars, infer profiles, and rank opener-fit matches.")
DEFAULT_DB = Path("data/venue_matcher.db")
DEFAULT_USER_AGENT = os.getenv("SCRAPER_USER_AGENT", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 venue-match/0.2")
TEXT_MASK = "places.id,places.displayName,places.formattedAddress,places.websiteUri,places.location,places.nationalPhoneNumber"
DETAILS_MASK = "id,displayName,formattedAddress,websiteUri,location,googleMapsUri,utcOffsetMinutes,types"


@app.command()
def discover(query: str = typer.Option(..., "--query"), limit: int = typer.Option(30), db_path: Path = typer.Option(DEFAULT_DB)):
    api_key = require_api_key()
    db = Database(db_path)
    places = places_text_search(query, None, api_key, TEXT_MASK)[:limit]
    for item in places:
        place_id = item.get("id")
        details = places_place_details(place_id, api_key, DETAILS_MASK) if place_id else {}
        name = details.get("displayName", {}).get("text") or item.get("displayName", {}).get("text") or "Unknown venue"
        website = details.get("websiteUri") or item.get("websiteUri")
        city, region = _split_city_region(details.get("formattedAddress") or item.get("formattedAddress", ""))
        venue = Venue(
            venue_id=place_id or name.lower().replace(" ", "-"),
            name=name,
            place_id=place_id,
            website_url=website,
            address=details.get("formattedAddress") or item.get("formattedAddress"),
            city=city,
            region=region,
            latitude=(details.get("location") or item.get("location") or {}).get("latitude"),
            longitude=(details.get("location") or item.get("location") or {}).get("longitude"),
            timezone=None,
        )
        if website:
            try:
                venue.calendar_urls = discover_calendar_urls(website, DEFAULT_USER_AGENT)
            except Exception as exc:
                db.log_extraction(venue.venue_id, website, "calendar_discovery", f"failed: {exc}")
        db.upsert_venue(venue)
        typer.echo(f"{venue.venue_id}\t{venue.name}\t{venue.website_url or 'no-website'}\t{', '.join(venue.calendar_urls[:3])}")


@app.command()
def scrape(venue_id: str = typer.Option(..., "--venue-id"), use_playwright: bool = typer.Option(False), db_path: Path = typer.Option(DEFAULT_DB), ignore_robots: bool = typer.Option(False)):
    db = Database(db_path)
    venue = db.load_venue(venue_id)
    if not venue:
        raise typer.BadParameter(f"Unknown venue_id: {venue_id}")
    html_pages: dict[str, str] = {}
    all_events: list[Event] = []
    targets = venue.calendar_urls or ([venue.website_url] if venue.website_url else [])
    for url in filter(None, targets):
        if not ignore_robots and not can_fetch(url, DEFAULT_USER_AGENT):
            db.log_extraction(venue.venue_id, url, "robots", "blocked by robots.txt")
            continue
        html = fetch_html(url, DEFAULT_USER_AGENT, 20.0)
        html_pages[url] = html
        db.save_snapshot(venue.venue_id, url, html)
        jsonld_events = extract_events_from_jsonld(html, url)
        for event in jsonld_events:
            event.venue_id = venue.venue_id
        css_events = []
        if not jsonld_events:
            rules = {"venue_id": venue.venue_id, "list_selector": ".event, .tribe-events-event, article", "title_selector": "h1, h2, h3, .title", "date_selector": "time, .date", "url_selector": "a[href]", "artist_selector": ".artist, .artists li"}
            css_events = extract_events_from_css(html, url, rules)
        page_events = normalize_event_datetimes(jsonld_events or css_events, venue.timezone)
        db.log_extraction(venue.venue_id, url, "jsonld" if jsonld_events else "css", f"extracted {len(page_events)} events")
        all_events.extend(page_events)
    venue = infer_capacity(venue, html_pages, all_events)
    db.upsert_venue(venue)
    db.upsert_events(all_events)
    if use_playwright:
        typer.echo("Playwright escalation requested; install playwright and add a JS-rendering fetch adapter if needed.")
    typer.echo(f"Scraped {len(all_events)} events for {venue.name}; capacity={venue.capacity_estimate} conf={venue.capacity_confidence}")
    for source in venue.capacity_sources[:5]:
        typer.echo(f"  capacity evidence: {source.source_url} | {source.extracted_value} | {source.extracted_text_snippet[:120]}")


@app.command()
def profile(venue_id: str = typer.Option(..., "--venue-id"), db_path: Path = typer.Option(DEFAULT_DB)):
    db = Database(db_path)
    venue = db.load_venue(venue_id)
    if not venue:
        raise typer.BadParameter(f"Unknown venue_id: {venue_id}")
    events = db.load_events_for_venue(venue_id)
    profile_obj = llm_infer_venue_profile(venue, events)
    db.upsert_profile(profile_obj)
    typer.echo(json.dumps(profile_obj.model_dump(), indent=2))


@app.command()
def rank(artist_profile: Path = typer.Option(..., "--artist-profile"), region: str = typer.Option(..., "--region"), limit: int = typer.Option(30), db_path: Path = typer.Option(DEFAULT_DB)):
    artist = ArtistProfile.model_validate_json(artist_profile.read_text())
    db = Database(db_path)
    rows = db.conn.execute("SELECT venue_id FROM venues WHERE region = ? OR city = ? LIMIT ?", (region, region, limit)).fetchall()
    scores = []
    for (venue_id,) in rows:
        venue = db.load_venue(venue_id)
        if not venue:
            continue
        profile_row = db.conn.execute("SELECT inferred_genres, audience_traits, booking_tier, typical_bill_style, support_friendliness, confidence, reasoning_summary, evidence FROM venue_profiles WHERE venue_id = ?", (venue_id,)).fetchone()
        if profile_row:
            venue_profile = VenueProfile(venue_id=venue_id, inferred_genres=json.loads(profile_row[0] or '[]'), audience_traits=json.loads(profile_row[1] or '[]'), booking_tier=profile_row[2], typical_bill_style=profile_row[3], support_friendliness=profile_row[4], confidence=profile_row[5], reasoning_summary=profile_row[6], evidence=json.loads(profile_row[7] or '[]'))
        else:
            venue_profile = llm_infer_venue_profile(venue, db.load_events_for_venue(venue_id))
            db.upsert_profile(venue_profile)
        scores.append(score_venue_for_artist(venue, venue_profile, artist))
    ranked = rank_venues(scores)
    db.upsert_match_scores(ranked)
    for score in ranked[:limit]:
        typer.echo(f"{score.total_score:.3f} | {score.venue_name} | genre={score.genre_score:.2f} audience={score.audience_score:.2f} region={score.region_score:.2f} tier={score.tier_score:.2f} capacity={score.capacity_fit:.2f} quality={score.data_quality:.2f}")
        for evidence in score.evidence[:4]:
            typer.echo(f"  - {evidence}")


@app.command()
def run(artist_profile: Path = typer.Option(..., "--artist-profile"), query: str = typer.Option(..., "--query"), limit: int = typer.Option(30), db_path: Path = typer.Option(DEFAULT_DB), ignore_robots: bool = typer.Option(False)):
    discover(query=query, limit=limit, db_path=db_path)
    db = Database(db_path)
    venue_ids = [row[0] for row in db.conn.execute("SELECT venue_id FROM venues LIMIT ?", (limit,)).fetchall()]
    for discovered_venue_id in venue_ids:
        scrape(venue_id=discovered_venue_id, db_path=db_path, ignore_robots=ignore_robots)
        profile(venue_id=discovered_venue_id, db_path=db_path)
    region_name = json.loads(artist_profile.read_text()).get('preferred_regions', [query])[0]
    rank(artist_profile=artist_profile, region=region_name, limit=limit, db_path=db_path)


def _split_city_region(address: str) -> tuple[str | None, str | None]:
    bits = [part.strip() for part in address.split(',') if part.strip()]
    if len(bits) >= 3:
        return bits[-3], bits[-2].split()[0]
    if len(bits) >= 2:
        return bits[-2], bits[-1].split()[0]
    return None, None


if __name__ == '__main__':
    app()
