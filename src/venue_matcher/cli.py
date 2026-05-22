"""ManagersButler CLI entry points.

Run `venue-match --help` to see all commands.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone as tz
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

# Load .env from cwd (if present) before reading any env-var config.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from . import config as user_config
user_config.apply_config_to_env()

from .capacity import infer_capacity
from .db import Database
from .demo import SAMPLE_ARTIST, seed_demo_db
from .import_venues import import_from_yaml
from .init_command import run_init
from .models import ArtistProfile, Event, Venue, VenueProfile
from .places import PlacesError, places_place_details, places_text_search, require_api_key
from .profiling_llm import llm_infer_venue_profile
from .scoring import rank_venues, score_venue_for_artist
from .scraping.extract_css import extract_events_from_css
from .scraping.extract_jsonld import extract_events_from_jsonld
from .scraping.fetch import fetch_html
from .scraping.normalize import normalize_event_datetimes
from .show_scoring import rank_opportunities, score_show_opportunity
from .website_discovery import can_fetch, discover_calendar_urls

app = typer.Typer(
    help="Discover venues, scrape calendars, infer profiles, and find opener/support slot opportunities.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
config_app = typer.Typer(help="Manage persistent CLI config stored in your user config dir.")
app.add_typer(config_app, name="config")

console = Console()
err_console = Console(stderr=True)

DEFAULT_DB = Path(user_config.get_config_value("default_db_path") or "data/venue_matcher.db")
DEFAULT_USER_AGENT = os.getenv("SCRAPER_USER_AGENT", "Mozilla/5.0 (compatible; ManagersButler/0.3)")
TEXT_MASK = "places.id,places.displayName,places.formattedAddress,places.websiteUri,places.location,places.nationalPhoneNumber"
DETAILS_MASK = "id,displayName,formattedAddress,websiteUri,location,googleMapsUri,utcOffsetMinutes,types"


# Module-level debug flag toggled by the --debug callback
_DEBUG = False


@app.callback()
def main(
    debug: bool = typer.Option(False, "--debug", help="Show full tracebacks on errors."),
):
    """ManagersButler — find venues and opener slots for your artists."""
    global _DEBUG
    _DEBUG = debug


def _fail(message: str, hint: str | None = None) -> None:
    """Print a friendly red error panel and exit with code 1."""
    body = message
    if hint:
        body += f"\n\n[dim]{hint}[/dim]"
    err_console.print(Panel(body, title="Error", border_style="red"))
    raise typer.Exit(1)


def _handle(fn, *args, **kwargs):
    """Run a command body with friendly error formatting."""
    try:
        return fn(*args, **kwargs)
    except typer.Exit:
        raise
    except typer.BadParameter as exc:
        _fail(str(exc))
    except PlacesError as exc:
        _fail(str(exc))
    except Exception as exc:
        if _DEBUG:
            raise
        _fail(f"{type(exc).__name__}: {exc}", hint="Run with --debug for a full traceback.")


# ---------------------------------------------------------------------------
# init / demo
# ---------------------------------------------------------------------------

@app.command()
def init(
    force: bool = typer.Option(False, "--force", help="Overwrite existing files without prompting."),
):
    """Interactively scaffold artist.json, .env, and data/ in the current directory."""
    _handle(run_init, force=force)


@app.command()
def demo(
    db_path: Path = typer.Option(Path("data/venue_matcher_demo.db"), "--db-path"),
    min_score: float = typer.Option(0.3, "--min-score"),
    limit: int = typer.Option(20, "--limit"),
):
    """Run the ranker against a pre-populated sample dataset. [green]No API keys required.[/green]"""
    def _run():
        console.print(Panel.fit(
            "[bold]Seeding demo database[/bold] with 5 sample venues in Austin, TX\n"
            "and running opener-opportunity ranking against a sample artist profile.\n"
            "[dim]No network, no API keys, no Ollama required.[/dim]",
            title="venue-match demo",
            border_style="green",
        ))
        db = seed_demo_db(db_path)
        console.print(f"[green]Seeded[/green] {db_path}")

        events = db.load_future_events()
        opportunities = []
        for event in events:
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
            opp = score_show_opportunity(event, venue, SAMPLE_ARTIST, venue_profile)
            if opp and opp.opportunity_score >= min_score:
                opportunities.append(opp)

        ranked = rank_opportunities(opportunities)[:limit]
        _render_opportunities_table(ranked, title="Demo: opener opportunities for a sample indie-rock artist")
        console.print(
            "\n[dim]Try [cyan]venue-match init[/cyan] to set up a real artist profile, "
            "or [cyan]venue-match pipeline --file venues.yaml --artist-profile artist.json[/cyan] "
            "to scrape real venues.[/dim]"
        )
    _handle(_run)


# ---------------------------------------------------------------------------
# discover / scrape / profile / rank / run  (existing commands, polished)
# ---------------------------------------------------------------------------

@app.command()
def discover(
    query: str = typer.Option(..., "--query", help="Google Places text query, e.g. 'live music venues in Austin TX'"),
    limit: int = typer.Option(30, "--limit"),
    db_path: Path = typer.Option(DEFAULT_DB, "--db-path"),
):
    """Discover venues via Google Places API and store them in the local database."""
    def _run():
        api_key = require_api_key()
        db = Database(db_path)
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as prog:
            task = prog.add_task(f"Searching Google Places for '{query}'...", total=None)
            places = places_text_search(query, None, api_key, TEXT_MASK)[:limit]
            prog.update(task, description=f"Found {len(places)} places — fetching details...", total=len(places))
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
                prog.advance(task)
        console.print(f"[green]Discovered[/green] {len(places)} venues into {db_path}")
    _handle(_run)


@app.command()
def scrape(
    venue_id: str = typer.Option(None, "--venue-id", help="Scrape a single venue by id."),
    all_venues: bool = typer.Option(False, "--all", help="Scrape every venue in the database."),
    use_playwright: bool = typer.Option(False, "--use-playwright"),
    db_path: Path = typer.Option(DEFAULT_DB, "--db-path"),
    ignore_robots: bool = typer.Option(False, "--ignore-robots"),
):
    """Scrape event calendars from a venue's website."""
    def _run():
        db = Database(db_path)
        if all_venues:
            venues = db.load_all_venues()
            if not venues:
                _fail("No venues in database.", hint="Run `venue-match discover` or `venue-match import-venues` first.")
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TaskProgressColumn(), console=console) as prog:
                task = prog.add_task("Scraping venues...", total=len(venues))
                for v in venues:
                    prog.update(task, description=f"Scraping {v.name}")
                    try:
                        _scrape_venue(v, db, ignore_robots, use_playwright)
                    except Exception as exc:
                        console.print(f"[yellow]warn:[/yellow] failed to scrape {v.name}: {exc}")
                    prog.advance(task)
        elif venue_id:
            venue = db.load_venue(venue_id)
            if not venue:
                raise typer.BadParameter(f"Unknown venue_id: {venue_id}")
            _scrape_venue(venue, db, ignore_robots, use_playwright)
        else:
            _fail("Provide either --venue-id or --all")
    _handle(_run)


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
    console.print(f"  [dim]{venue.name}:[/dim] {len(all_events)} events, capacity={venue.capacity_estimate} (conf {venue.capacity_confidence:.2f})")
    return all_events


@app.command()
def profile(
    venue_id: str = typer.Option(..., "--venue-id"),
    db_path: Path = typer.Option(DEFAULT_DB, "--db-path"),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON instead of a table."),
):
    """Generate an LLM-inferred profile for a venue (requires Ollama for best results)."""
    def _run():
        db = Database(db_path)
        venue = db.load_venue(venue_id)
        if not venue:
            raise typer.BadParameter(f"Unknown venue_id: {venue_id}")
        events = db.load_events_for_venue(venue_id)
        profile_obj = llm_infer_venue_profile(venue, events)
        db.upsert_profile(profile_obj)
        if json_output:
            print(json.dumps(profile_obj.model_dump(), indent=2))
        else:
            table = Table(title=f"Profile: {venue.name}")
            table.add_column("field", style="cyan")
            table.add_column("value")
            table.add_row("genres", ", ".join(profile_obj.inferred_genres))
            table.add_row("audience", ", ".join(profile_obj.audience_traits))
            table.add_row("booking tier", profile_obj.booking_tier)
            table.add_row("bill style", profile_obj.typical_bill_style)
            table.add_row("support friendliness", f"{profile_obj.support_friendliness:.2f}")
            table.add_row("confidence", f"{profile_obj.confidence:.2f}")
            console.print(table)
            console.print(f"[dim]{profile_obj.reasoning_summary}[/dim]")
    _handle(_run)


@app.command()
def rank(
    artist_profile: Path = typer.Option(..., "--artist-profile"),
    region: str = typer.Option(None, "--region", help="State/region code. Defaults to the first preferred_regions entry in the artist profile."),
    limit: int = typer.Option(30, "--limit"),
    db_path: Path = typer.Option(DEFAULT_DB, "--db-path"),
    json_output: bool = typer.Option(False, "--json"),
):
    """Rank venues for an artist (venue-level compatibility scoring)."""
    def _run():
        if not artist_profile.exists():
            raise typer.BadParameter(f"Artist profile not found: {artist_profile}")
        artist = ArtistProfile.model_validate_json(artist_profile.read_text())
        target_region = region or (artist.preferred_regions[0] if artist.preferred_regions else None)
        if not target_region:
            raise typer.BadParameter("No --region given and artist profile has no preferred_regions.")
        db = Database(db_path)
        rows = db.conn.execute("SELECT venue_id FROM venues WHERE region = ? OR city = ? LIMIT ?", (target_region, target_region, limit)).fetchall()
        if not rows:
            regions_in_db = [r[0] for r in db.conn.execute("SELECT DISTINCT region FROM venues WHERE region IS NOT NULL").fetchall()]
            hint = f"Regions in DB: {', '.join(regions_in_db) or '(none)'}. Try `venue-match list-regions` or run `venue-match discover` first."
            _fail(f"No venues found for region '{target_region}'.", hint=hint)
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
        if json_output:
            print(json.dumps([s.model_dump() for s in ranked[:limit]], indent=2, default=str))
            return
        table = Table(title=f"Top {min(limit, len(ranked))} venues for {artist.name}")
        table.add_column("score", justify="right", style="green")
        table.add_column("venue", style="cyan")
        table.add_column("genre", justify="right")
        table.add_column("cap.fit", justify="right")
        table.add_column("quality", justify="right")
        for score in ranked[:limit]:
            table.add_row(
                f"{score.total_score:.3f}",
                score.venue_name,
                f"{score.genre_score:.2f}",
                f"{score.capacity_fit:.2f}",
                f"{score.data_quality:.2f}",
            )
        console.print(table)
    _handle(_run)


@app.command()
def run(
    artist_profile: Path = typer.Option(..., "--artist-profile"),
    query: str = typer.Option(..., "--query"),
    limit: int = typer.Option(30, "--limit"),
    db_path: Path = typer.Option(DEFAULT_DB, "--db-path"),
    ignore_robots: bool = typer.Option(False, "--ignore-robots"),
):
    """End-to-end Google Places pipeline: discover -> scrape -> profile -> rank."""
    def _inner():
        if not artist_profile.exists():
            raise typer.BadParameter(f"Artist profile not found: {artist_profile}")
        api_key = require_api_key()  # fail early with friendly error
        db = Database(db_path)
        console.rule("[bold]Step 1: discover[/bold]")
        places = places_text_search(query, None, api_key, TEXT_MASK)[:limit]
        for item in places:
            place_id = item.get("id")
            details = places_place_details(place_id, api_key, DETAILS_MASK) if place_id else {}
            name = details.get("displayName", {}).get("text") or "Unknown venue"
            website = details.get("websiteUri") or item.get("websiteUri")
            city, region = _split_city_region(details.get("formattedAddress") or item.get("formattedAddress", ""))
            venue = Venue(
                venue_id=place_id or name.lower().replace(" ", "-"),
                name=name,
                place_id=place_id,
                website_url=website,
                address=details.get("formattedAddress"),
                city=city,
                region=region,
            )
            if website:
                try:
                    venue.calendar_urls = discover_calendar_urls(website, DEFAULT_USER_AGENT)
                except Exception:
                    pass
            db.upsert_venue(venue)
        console.rule("[bold]Step 2: scrape[/bold]")
        for v in db.load_all_venues()[:limit]:
            try:
                _scrape_venue(v, db, ignore_robots)
            except Exception as exc:
                console.print(f"[yellow]warn:[/yellow] {v.name}: {exc}")
        console.rule("[bold]Step 3: profile[/bold]")
        for v in db.load_all_venues()[:limit]:
            events = db.load_events_for_venue(v.venue_id)
            p = llm_infer_venue_profile(v, events)
            db.upsert_profile(p)
        console.rule("[bold]Step 4: rank[/bold]")
        region_name = json.loads(artist_profile.read_text()).get('preferred_regions', [query])[0]
        rank(artist_profile=artist_profile, region=region_name, limit=limit, db_path=db_path, json_output=False)
    _handle(_inner)


# ---------------------------------------------------------------------------
# import-venues / find-openers / pipeline / list-regions
# ---------------------------------------------------------------------------

@app.command("import-venues")
def import_venues_cmd(
    file: Path = typer.Option(..., "--file", help="YAML file listing venues."),
    db_path: Path = typer.Option(DEFAULT_DB, "--db-path"),
):
    """Import venues from a YAML file (no Google Places API needed)."""
    def _run():
        if not file.exists():
            raise typer.BadParameter(f"YAML file not found: {file}")
        db = Database(db_path)
        venues = import_from_yaml(file, db)
        table = Table(title=f"Imported {len(venues)} venues")
        table.add_column("venue_id", style="dim")
        table.add_column("name", style="cyan")
        table.add_column("location")
        for v in venues:
            loc = ", ".join(filter(None, [v.city, v.region]))
            table.add_row(v.venue_id, v.name, loc)
        console.print(table)
    _handle(_run)


@app.command("find-openers")
def find_openers(
    artist_profile: Path = typer.Option(..., "--artist-profile"),
    min_score: float = typer.Option(0.3, "--min-score"),
    weeks_ahead: int = typer.Option(12, "--weeks-ahead"),
    limit: int = typer.Option(30, "--limit"),
    db_path: Path = typer.Option(DEFAULT_DB, "--db-path"),
    json_output: bool = typer.Option(False, "--json"),
):
    """Find opener/support slot opportunities at scraped venues."""
    def _run():
        if not artist_profile.exists():
            raise typer.BadParameter(f"Artist profile not found: {artist_profile}")
        artist = ArtistProfile.model_validate_json(artist_profile.read_text())
        db = Database(db_path)
        events = db.load_future_events()
        if not events:
            _fail("No future events in database.", hint="Run `venue-match scrape --all` or `venue-match pipeline` first.")

        cutoff = datetime.now(tz.utc) + timedelta(weeks=weeks_ahead)
        opportunities = []
        for event in events:
            event_dt = event.start_dt
            if event_dt and event_dt.tzinfo is None:
                event_dt = event_dt.replace(tzinfo=tz.utc)
            if event_dt and event_dt > cutoff:
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
            console.print("[yellow]No opportunities found above the minimum score threshold.[/yellow]")
            return
        if json_output:
            print(json.dumps([o.model_dump() for o in ranked], indent=2, default=str))
            return
        _render_opportunities_table(ranked, title=f"Opener opportunities for {artist.name}")
    _handle(_run)


@app.command()
def pipeline(
    file: Path = typer.Option(..., "--file", help="YAML file listing venues to scrape."),
    artist_profile: Path = typer.Option(..., "--artist-profile"),
    weeks_ahead: int = typer.Option(12, "--weeks-ahead"),
    min_score: float = typer.Option(0.3, "--min-score"),
    limit: int = typer.Option(30, "--limit"),
    db_path: Path = typer.Option(DEFAULT_DB, "--db-path"),
    ignore_robots: bool = typer.Option(False, "--ignore-robots"),
):
    """Full YAML-driven pipeline: import-venues -> scrape --all -> find-openers.

    [green]Does not require a Google Maps API key[/green] — you provide the venue list yourself.
    """
    def _run():
        console.rule("[bold]Step 1: import venues[/bold]")
        import_venues_cmd(file=file, db_path=db_path)
        console.rule("[bold]Step 2: scrape all venues[/bold]")
        scrape(all_venues=True, db_path=db_path, ignore_robots=ignore_robots)
        console.rule("[bold]Step 3: find opener opportunities[/bold]")
        find_openers(artist_profile=artist_profile, min_score=min_score, weeks_ahead=weeks_ahead, limit=limit, db_path=db_path)
    _handle(_run)


@app.command("list-regions")
def list_regions(db_path: Path = typer.Option(DEFAULT_DB, "--db-path")):
    """List the distinct regions/states for venues in the database."""
    def _run():
        db = Database(db_path)
        rows = db.conn.execute(
            "SELECT region, COUNT(*) FROM venues WHERE region IS NOT NULL GROUP BY region ORDER BY COUNT(*) DESC"
        ).fetchall()
        if not rows:
            console.print("[dim]No venues in database yet. Run `venue-match discover` or `venue-match import-venues`.[/dim]")
            return
        table = Table(title="Regions in database")
        table.add_column("region", style="cyan")
        table.add_column("venue count", justify="right")
        for region, count in rows:
            table.add_row(region, str(count))
        console.print(table)
    _handle(_run)


# ---------------------------------------------------------------------------
# config subcommands
# ---------------------------------------------------------------------------

@config_app.command("show")
def config_show():
    """Show the contents of your user config file."""
    cfg = user_config.load_config()
    path = user_config.config_path()
    if not cfg:
        console.print(f"[dim]No config file at {path}[/dim]")
        return
    table = Table(title=f"Config: {path}")
    table.add_column("key", style="cyan")
    table.add_column("value")
    for key, value in sorted(cfg.items()):
        # Redact anything that looks like a secret
        if "key" in key.lower() or "token" in key.lower() or "secret" in key.lower():
            display = value[:4] + "…" if isinstance(value, str) and len(value) > 4 else "***"
        else:
            display = str(value)
        table.add_row(key, display)
    console.print(table)


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help=f"One of: {', '.join(sorted(user_config.ALLOWED_KEYS))}"),
    value: str = typer.Argument(...),
):
    """Set a persistent config value."""
    try:
        path = user_config.set_config_value(key, value)
    except ValueError as exc:
        _fail(str(exc))
    console.print(f"[green]Set[/green] {key} in {path}")


@config_app.command("unset")
def config_unset(key: str = typer.Argument(...)):
    """Remove a persistent config value."""
    path = user_config.unset_config_value(key)
    console.print(f"[green]Removed[/green] {key} from {path}")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _render_opportunities_table(ranked, title: str) -> None:
    if not ranked:
        console.print("[yellow]No opportunities to display.[/yellow]")
        return
    table = Table(title=title)
    table.add_column("score", justify="right", style="green")
    table.add_column("date", style="cyan")
    table.add_column("venue")
    table.add_column("show", max_width=32)
    table.add_column("why", style="dim")
    for opp in ranked:
        date_str = opp.event_date.strftime("%Y-%m-%d") if opp.event_date else "TBD"
        why = "; ".join(opp.reasons[:2]) if opp.reasons else ""
        if opp.flags:
            why += f" [red]({', '.join(opp.flags)})[/red]"
        table.add_row(f"{opp.opportunity_score:.2f}", date_str, opp.venue_name, opp.event_title, why)
    console.print(table)
    console.print(f"\n[bold]{len(ranked)}[/bold] opportunities found.")


def _split_city_region(address: str) -> tuple[str | None, str | None]:
    bits = [part.strip() for part in address.split(',') if part.strip()]
    if len(bits) >= 3:
        return bits[-3], bits[-2].split()[0]
    if len(bits) >= 2:
        return bits[-2], bits[-1].split()[0]
    return None, None


if __name__ == '__main__':
    app()
