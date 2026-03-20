from __future__ import annotations

import json
import os
from pathlib import Path

import typer

from .capacity import infer_capacity
from .db import Database
from .import_venues import import_from_yaml
from .models import ArtistProfile, Event, Venue, VenueProfile
from .places import places_place_details, places_text_search, require_api_key
from .profiling_llm import llm_infer_venue_profile
from .scoring import rank_venues, score_venue_for_artist
from .scraping.extract_css import extract_events_from_css
from .scraping.extract_jsonld import extract_events_from_jsonld
from .scraping.fetch import fetch_html
from .scraping.normalize import normalize_event_datetimes
from .show_scoring import rank_opportunities, score_show_opportunity
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
def scrape(venue_id: str = typer.Option(None, "--venue-id"), all_venues: bool = typer.Option(False, "--all"), use_playwright: bool = typer.Option(False), db_path: Path = typer.Option(DEFAULT_DB), ignore_robots: bool = typer.Option(False)):
    db = Database(db_path)
    if all_venues:
        venues = db.load_all_venues()
        if not venues:
            typer.echo("No venues in database. Import venues first with import-venues.")
            raise typer.Exit(1)
        for v in venues:
            _scrape_venue(v, db, ignore_robots, use_playwright)
    elif venue_id:
        venue = db.load_venue(venue_id)
        if not venue:
            raise typer.BadParameter(f"Unknown venue_id: {venue_id}")
        _scrape_venue(venue, db, ignore_robots, use_playwright)
    else:
        typer.echo("Provide --venue-id or --all")
        raise typer.Exit(1)


def _scrape_venue(venue: Venue, db: Database, ignore_robots: bool, use_playwright: bool = False) -> list[Event]:
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
            if venue.css_rules:
                rules = {**venue.css_rules, "venue_id": venue.venue_id}
            else:
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
    return all_events


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


@app.command("import-venues")
def import_venues_cmd(file: Path = typer.Option(..., "--file"), db_path: Path = typer.Option(DEFAULT_DB)):
    """Import venues from a YAML file (no Google Places API needed)."""
    db = Database(db_path)
    venues = import_from_yaml(file, db)
    for v in venues:
        typer.echo(f"  {v.venue_id}\t{v.name}\t{', '.join(v.calendar_urls[:3])}")
    typer.echo(f"Imported {len(venues)} venues.")


@app.command("find-openers")
def find_openers(
    artist_profile: Path = typer.Option(..., "--artist-profile"),
    min_score: float = typer.Option(0.3, "--min-score"),
    weeks_ahead: int = typer.Option(12, "--weeks-ahead"),
    limit: int = typer.Option(30, "--limit"),
    db_path: Path = typer.Option(DEFAULT_DB),
):
    """Find opener/support slot opportunities at scraped venues."""
    artist = ArtistProfile.model_validate_json(artist_profile.read_text())
    db = Database(db_path)
    events = db.load_future_events()
    if not events:
        typer.echo("No future events in database. Run scrape first.")
        raise typer.Exit(1)

    from datetime import datetime, timedelta, timezone as tz
    cutoff = datetime.now(tz.utc) + timedelta(weeks=weeks_ahead)

    opportunities = []
    for event in events:
        if event.start_dt and event.start_dt.replace(tzinfo=event.start_dt.tzinfo or tz.utc) > cutoff:
            continue
        venue = db.load_venue(event.venue_id)
        if not venue:
            continue
        profile_row = db.conn.execute(
            "SELECT venue_id, inferred_genres, audience_traits, booking_tier, typical_bill_style, support_friendliness, confidence, reasoning_summary, evidence FROM venue_profiles WHERE venue_id = ?",
            (event.venue_id,),
        ).fetchone()
        venue_profile = None
        if profile_row:
            venue_profile = VenueProfile(
                venue_id=profile_row[0],
                inferred_genres=json.loads(profile_row[1] or '[]'),
                audience_traits=json.loads(profile_row[2] or '[]'),
                booking_tier=profile_row[3],
                typical_bill_style=profile_row[4],
                support_friendliness=profile_row[5],
                confidence=profile_row[6],
                reasoning_summary=profile_row[7],
                evidence=json.loads(profile_row[8] or '[]'),
            )
        opp = score_show_opportunity(event, venue, artist, venue_profile)
        if opp and opp.opportunity_score >= min_score:
            opportunities.append(opp)

    ranked = rank_opportunities(opportunities)[:limit]
    db.upsert_show_opportunities(ranked)

    if not ranked:
        typer.echo("No opportunities found above the minimum score threshold.")
        raise typer.Exit(0)

    typer.echo(f"\n{'SCORE':>5} | {'DATE':10} | {'VENUE':20} | {'SHOW':30} | WHY")
    typer.echo("-" * 100)
    for opp in ranked:
        date_str = opp.event_date.strftime("%Y-%m-%d") if opp.event_date else "TBD"
        why = "; ".join(opp.reasons[:2]) if opp.reasons else ""
        flag_str = (" [" + ", ".join(opp.flags) + "]") if opp.flags else ""
        typer.echo(f"{opp.opportunity_score:.2f}  | {date_str:10} | {opp.venue_name:20.20} | {opp.event_title:30.30} | {why}{flag_str}")
    typer.echo(f"\n{len(ranked)} opportunities found.")


@app.command()
def pipeline(
    file: Path = typer.Option(..., "--file"),
    artist_profile: Path = typer.Option(..., "--artist-profile"),
    weeks_ahead: int = typer.Option(12, "--weeks-ahead"),
    min_score: float = typer.Option(0.3, "--min-score"),
    limit: int = typer.Option(30, "--limit"),
    db_path: Path = typer.Option(DEFAULT_DB),
    ignore_robots: bool = typer.Option(False),
):
    """Full pipeline: import venues -> scrape all -> find opener opportunities."""
    typer.echo("=== Step 1: Import venues ===")
    import_venues_cmd(file=file, db_path=db_path)
    typer.echo("\n=== Step 2: Scrape all venues ===")
    scrape(all_venues=True, db_path=db_path, ignore_robots=ignore_robots)
    typer.echo("\n=== Step 3: Find opener opportunities ===")
    find_openers(artist_profile=artist_profile, min_score=min_score, weeks_ahead=weeks_ahead, limit=limit, db_path=db_path)


def _split_city_region(address: str) -> tuple[str | None, str | None]:
    bits = [part.strip() for part in address.split(',') if part.strip()]
    if len(bits) >= 3:
        return bits[-3], bits[-2].split()[0]
    if len(bits) >= 2:
        return bits[-2], bits[-1].split()[0]
    return None, None


if __name__ == '__main__':
    app()
