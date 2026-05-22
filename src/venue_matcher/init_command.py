"""Interactive `venue-match init` bootstrap.

Creates an artist.json, .env, and data/ directory in the current working
directory so a brand-new user can go from `pip install` to running the
pipeline in under a minute.
"""
from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt

console = Console()

_ENV_TEMPLATE = """# ManagersButler environment variables
# See README.md for details.

# Required for `discover`/`run` (Google Places API)
# Get a key: https://console.cloud.google.com/apis/credentials
# Enable "Places API (New)" for your project.
GOOGLE_MAPS_API_KEY={google_maps_api_key}

# Local LLM server for venue profiling (optional but recommended)
# Install Ollama: https://ollama.ai  then run: ollama pull qwen3:14b
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL_PROFILE=qwen3:14b

# Optional: override the user-agent used by the scraper
# SCRAPER_USER_AGENT=Mozilla/5.0 (compatible; ManagersButler/0.3)
"""


def run_init(force: bool = False) -> None:
    """Interactive bootstrap. Writes artist.json, .env, and data/ to cwd."""
    cwd = Path.cwd()
    console.print(Panel.fit(
        "[bold]Welcome to ManagersButler![/bold]\n"
        "This will create a ready-to-use workspace in the current directory:\n"
        "  • [cyan]artist.json[/cyan]  — your artist profile\n"
        "  • [cyan].env[/cyan]         — API keys and settings\n"
        "  • [cyan]data/[/cyan]        — database directory\n",
        title="venue-match init",
        border_style="green",
    ))

    artist_path = cwd / "artist.json"
    env_path = cwd / ".env"

    if artist_path.exists() and not force:
        if not Confirm.ask(f"[yellow]{artist_path.name} already exists. Overwrite?[/yellow]", default=False):
            console.print("[dim]Skipping artist.json[/dim]")
            artist_path = None  # type: ignore
    if env_path.exists() and not force:
        if not Confirm.ask(f"[yellow]{env_path.name} already exists. Overwrite?[/yellow]", default=False):
            console.print("[dim]Skipping .env[/dim]")
            env_path = None  # type: ignore

    # Artist profile prompts
    if artist_path is not None:
        console.print("\n[bold]Tell me about the artist you're booking:[/bold]")
        name = Prompt.ask("Artist name", default="My Artist")
        genres_raw = Prompt.ask(
            "Target genres (comma-separated)",
            default="indie rock, alternative",
        )
        target_capacity = IntPrompt.ask("Target venue capacity", default=300)
        regions_raw = Prompt.ask(
            "Preferred regions (comma-separated state codes)",
            default="TX",
        )
        support_ready = Confirm.ask("Artist is willing to play support/opener slots?", default=True)

        artist = {
            "name": name,
            "target_genres": [g.strip() for g in genres_raw.split(",") if g.strip()],
            "audience_traits": [],
            "target_capacity": target_capacity,
            "min_capacity": max(50, target_capacity // 3),
            "max_capacity": target_capacity * 3,
            "preferred_regions": [r.strip() for r in regions_raw.split(",") if r.strip()],
            "support_slot_ready": support_ready,
            "available_dates": [],
        }
        artist_path.write_text(json.dumps(artist, indent=2), encoding="utf-8")
        console.print(f"[green]Created[/green] {artist_path.name}")

    # .env prompts
    if env_path is not None:
        console.print("\n[bold].env setup[/bold]")
        has_key = Confirm.ask(
            "Do you have a Google Maps API key ready to paste? "
            "[dim](say 'no' to skip — you can still run `venue-match demo`)[/dim]",
            default=False,
        )
        google_key = ""
        if has_key:
            google_key = Prompt.ask("Paste your Google Maps API key", default="", password=True).strip()
        env_path.write_text(_ENV_TEMPLATE.format(google_maps_api_key=google_key), encoding="utf-8")
        console.print(f"[green]Created[/green] {env_path.name}")

    data_dir = cwd / "data"
    data_dir.mkdir(exist_ok=True)
    console.print(f"[green]Created[/green] {data_dir.name}/")

    console.print(Panel.fit(
        "[bold green]Setup complete![/bold green]\n\n"
        "Try one of these next:\n\n"
        "  [cyan]venue-match demo[/cyan]\n"
        "      Run against a pre-populated sample DB (no API keys needed).\n\n"
        "  [cyan]venue-match pipeline --file venues.yaml --artist-profile artist.json[/cyan]\n"
        "      Scrape your own venues from a YAML file.\n\n"
        "  [cyan]venue-match run --artist-profile artist.json --query \"live music venues in Austin TX\"[/cyan]\n"
        "      Full Google Places-driven pipeline (requires API key).",
        title="Next steps",
        border_style="green",
    ))


if __name__ == "__main__":
    typer.run(run_init)
