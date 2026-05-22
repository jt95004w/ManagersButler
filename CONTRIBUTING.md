# Contributing to ManagersButler

Thanks for considering a contribution! This is a small open-source CLI and we welcome issues, bug reports, and pull requests.

## Development setup

```bash
git clone https://github.com/jt95004w/ManagersButler
cd ManagersButler
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -U pip
pip install -e ".[dev]"
```

That installs the CLI in editable mode plus `pytest` and `ruff`.

## Running the test suite

```bash
pytest
```

All tests live under `tests/` and should run in under a few seconds. They do not hit the network — the scraping tests use local HTML fixtures.

## Linting

```bash
ruff check src/
```

## Project layout

```
src/venue_matcher/
├── cli.py                # Typer entry points
├── init_command.py       # `venue-match init`
├── demo.py               # `venue-match demo` — sample data seeder
├── config.py             # ~/.config/venue-match/config.toml reader/writer
├── models.py             # Data classes
├── db.py                 # SQLite schema + helpers
├── places.py             # Google Places API
├── profiling_llm.py      # Ollama venue profiling
├── website_discovery.py  # Calendar URL discovery
├── capacity.py           # Capacity inference
├── scoring.py            # Venue-level scoring
├── show_scoring.py       # Show-level opener-opportunity scoring
├── import_venues.py      # YAML -> DB importer
└── scraping/
    ├── fetch.py
    ├── extract_jsonld.py
    ├── extract_css.py
    └── normalize.py
```

## Adding a new CLI command

1. Add a `@app.command()`-decorated function in `src/venue_matcher/cli.py`.
2. Wrap the body in `_handle(_run)` for friendly error formatting.
3. Use `rich` primitives (`Console`, `Table`, `Progress`) for output, and add a `--json` flag if the output is data-oriented.
4. Add a test under `tests/` if the command has non-trivial logic.
5. Add an entry to `CHANGELOG.md`.

## Updating the demo dataset

The demo data is hand-authored in `src/venue_matcher/demo.py` in `_sample_venues()`. To change it, edit that function — the `venue-match demo` command rebuilds the sample SQLite DB from scratch on every run, so no binary needs to be committed.

## Release checklist

1. Bump the version in `pyproject.toml`.
2. Add a new section to `CHANGELOG.md`.
3. Tag the commit: `git tag vX.Y.Z && git push --tags`.
4. CI will build wheels. Manual PyPI publish is disabled by default — enable `.github/workflows/release.yml` when ready.

## Reporting bugs

Please include:
- Your OS and Python version (`python --version`)
- The exact command you ran
- The full output with `--debug` enabled
- What you expected to happen
