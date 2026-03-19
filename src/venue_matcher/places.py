from __future__ import annotations

import os

import httpx

PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"


def places_text_search(text_query: str, location_bias: dict | None, api_key: str, field_mask: str) -> list[dict]:
    payload: dict = {"textQuery": text_query}
    if location_bias:
        payload["locationBias"] = location_bias
    response = httpx.post(
        PLACES_TEXT_SEARCH_URL,
        json=payload,
        headers={"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": field_mask},
        timeout=20.0,
    )
    response.raise_for_status()
    return response.json().get("places", [])


def places_place_details(place_id: str, api_key: str, field_mask: str) -> dict:
    response = httpx.get(
        PLACES_DETAILS_URL.format(place_id=place_id),
        headers={"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": field_mask},
        timeout=20.0,
    )
    response.raise_for_status()
    return response.json()


def require_api_key() -> str:
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_MAPS_API_KEY is required")
    return api_key
