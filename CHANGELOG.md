# Changelog

## 0.3.0 — User-Friendliness Overhaul

### Added
- **`venue-match init`** — interactive bootstrap that scaffolds `artist.json`, `.env`, and `data/` in the current directory.
- **`venue-match demo`** — runs the ranker against a pre-populated sample dataset. No API keys, no Ollama, no network required.
- **`venue-match list-regions`** — prints the regions present in your database.
- **`venue-match config` subcommands** (`set`, `show`, `unset`) — persistent user config file stored in `~/.config/venue-match/config.toml` (or `%APPDATA%\venue-match\config.toml` on Windows).
- **Rich output**: progress bars, colored tables, and friendly error panels across all commands.
- **`--json` flag** on `rank`, `profile`, `find-openers` for programmatic consumption.
- **`--debug` flag** to show full tracebacks on errors (default: friendly one-line errors).
- **`.env` auto-loading** via `python-dotenv` — put your API keys in a `.env` file and any command picks them up.
- **Sample files**: `artist.sample.json`, `.env.example`.
- **Ollama health check** on startup — loud warning if Ollama is unreachable instead of silent heuristic fallback.
- **LICENSE**, **CONTRIBUTING.md**, **CHANGELOG.md**, and GitHub Actions CI for Python 3.11/3.12/3.13 on Ubuntu + Windows.

### Fixed
- `GOOGLE_MAPS_API_KEY` missing → now raises a friendly error with setup instructions, not a raw `RuntimeError`.
- `httpx.ConnectError` from Google Places → now surfaced as a readable message with troubleshooting hints.
- `rank --region` with no matches → now prints distinct regions in the DB instead of silently returning nothing.
- `pyproject.toml` had an empty `email` field that blocked `pip install -e .` on newer setuptools.

### Removed
- **`src/manager_butler/`** legacy module (385 lines of dead code).
- **Vendor shims** at `src/` root (`dateparser.py`, `httpx.py`, `pydantic.py`, `selectolax/`) that shadowed real pip packages.
- `pydantic` dependency (unused — the code uses `@dataclass` and a tiny `ModelMixin`).

### Added dependencies
- `rich >= 13.7.0` (progress bars, tables, panels)
- `pyyaml >= 6.0` (required by `import-venues`, previously missing from declared deps)
- `python-dotenv >= 1.0.0` (`.env` loading)
