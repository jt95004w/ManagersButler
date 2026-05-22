"""Google Places API integration.

Requires the GOOGLE_MAPS_API_KEY environment variable and the "Places API (New)"
enabled in your Google Cloud project. Get a key at:
    https://console.cloud.google.com/apis/credentials
"""
from __future__ import annotations

import os

import httpx
import typer

PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"


class PlacesError(RuntimeError):
    """User-facing error from the Google Places integration."""


def _friendly_network_error(operation: str, exc: Exception) -> PlacesError:
    return PlacesError(
        f"Could not reach Google Places while {operation}.\n"
        f"  Underlying error: {exc}\n"
        f"  Check your internet connection, VPN, or proxy settings.\n"
        f"  Also verify 'Places API (New)' is enabled at "
        f"https://console.cloud.google.com/apis/library/places.googleapis.com"
    )


def places_text_search(text_query: str, location_bias: dict | None, api_key: str, field_mask: str) -> list[dict]:
    payload: dict = {"textQuery": text_query}
    if location_bias:
        payload["locationBias"] = location_bias
    try:
        response = httpx.post(
            PLACES_TEXT_SEARCH_URL,
            json=payload,
            headers={"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": field_mask},
            timeout=20.0,
        )
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
        raise _friendly_network_error("searching for venues", exc) from exc
    if response.status_code == 403:
        raise PlacesError(
            "Google Places returned 403 Forbidden. Your API key may be invalid or "
            "'Places API (New)' may not be enabled. Enable it at "
            "https://console.cloud.google.com/apis/library/places.googleapis.com"
        )
    response.raise_for_status()
    return response.json().get("places", [])


def places_place_details(place_id: str, api_key: str, field_mask: str) -> dict:
    try:
        response = httpx.get(
            PLACES_DETAILS_URL.format(place_id=place_id),
            headers={"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": field_mask},
            timeout=20.0,
        )
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
        raise _friendly_network_error("fetching venue details", exc) from exc
    response.raise_for_status()
    return response.json()


def require_api_key() -> str:
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise typer.BadParameter(
            "GOOGLE_MAPS_API_KEY is not set.\n\n"
            "  1. Get a key: https://console.cloud.google.com/apis/credentials\n"
            "  2. Enable 'Places API (New)' for your project:\n"
            "     https://console.cloud.google.com/apis/library/places.googleapis.com\n"
            "  3. Set the env var:\n"
            "       Windows PowerShell:  $env:GOOGLE_MAPS_API_KEY = \"your-key\"\n"
            "       macOS/Linux:         export GOOGLE_MAPS_API_KEY=\"your-key\"\n"
            "     Or add it to a .env file in your project directory (see .env.example).\n\n"
            "  If you just want to try the tool without an API key, run:\n"
            "       venue-match demo"
        )
    return api_key
