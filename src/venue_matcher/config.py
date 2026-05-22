"""User-level config file (~/.config/venue-match/config.toml).

Provides a persistent place to store API keys and defaults so users don't have
to re-export environment variables every shell session. Environment variables
always win over config file values.

Config keys (all optional):
    google_maps_api_key   Maps to GOOGLE_MAPS_API_KEY
    ollama_host           Maps to OLLAMA_HOST
    ollama_model_profile  Maps to OLLAMA_MODEL_PROFILE
    default_db_path       Default --db-path value
    default_region        Default --region value for `rank`
    scraper_user_agent    Maps to SCRAPER_USER_AGENT
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

# Env-var name for each supported config key
_ENV_MAP = {
    "google_maps_api_key": "GOOGLE_MAPS_API_KEY",
    "ollama_host": "OLLAMA_HOST",
    "ollama_model_profile": "OLLAMA_MODEL_PROFILE",
    "scraper_user_agent": "SCRAPER_USER_AGENT",
}

# Keys that don't map to env vars but are read directly by commands
_NON_ENV_KEYS = {"default_db_path", "default_region"}

ALLOWED_KEYS = set(_ENV_MAP.keys()) | _NON_ENV_KEYS


def config_path() -> Path:
    """Return the platform-appropriate config file path."""
    if sys.platform == "win32":
        base = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "venue-match" / "config.toml"
    xdg = os.getenv("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else (Path.home() / ".config")
    return base / "venue-match" / "config.toml"


def load_config() -> dict:
    """Load config from disk. Returns empty dict if file doesn't exist."""
    path = config_path()
    if not path.exists():
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def apply_config_to_env() -> None:
    """Populate environment variables from config file values.

    Called at CLI startup. Environment variables already set in the shell
    take precedence — we only fill in missing values from the config file.
    """
    cfg = load_config()
    for key, env_var in _ENV_MAP.items():
        if env_var not in os.environ and cfg.get(key):
            os.environ[env_var] = str(cfg[key])


def get_config_value(key: str) -> str | None:
    """Read a single config value (used for default_db_path, default_region)."""
    cfg = load_config()
    return cfg.get(key)


def set_config_value(key: str, value: str) -> Path:
    """Set a single config value and write the file. Returns the config path."""
    if key not in ALLOWED_KEYS:
        raise ValueError(
            f"Unknown config key '{key}'. Allowed keys: {', '.join(sorted(ALLOWED_KEYS))}"
        )
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    cfg[key] = value
    # Simple TOML writer — we only store flat string/number values
    lines = [f'{k} = "{v}"' if isinstance(v, str) else f"{k} = {v}" for k, v in sorted(cfg.items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def unset_config_value(key: str) -> Path:
    """Remove a config value and write the file."""
    path = config_path()
    cfg = load_config()
    cfg.pop(key, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f'{k} = "{v}"' if isinstance(v, str) else f"{k} = {v}" for k, v in sorted(cfg.items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
