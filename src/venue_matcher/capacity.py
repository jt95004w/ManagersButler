from __future__ import annotations

import json
import os
import re

import httpx

from .models import CapacitySource, Event, Venue

CAPACITY_PATTERNS = [
    re.compile(r"capacity[^\d]{0,20}(\d{2,5})", re.I),
    re.compile(r"holds?[^\d]{0,20}(\d{2,5})", re.I),
    re.compile(r"room for[^\d]{0,20}(\d{2,5})", re.I),
    re.compile(r"(\d{2,5})[- ]?(cap|capacity)", re.I),
]

CAPACITY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["capacity_numbers", "best_estimate", "confidence"],
    "properties": {
        "capacity_numbers": {"type": "array", "items": {"type": "integer"}},
        "best_estimate": {"type": ["integer", "null"]},
        "confidence": {"type": "number"},
    },
}


def infer_capacity(venue: Venue, html_pages: dict[str, str], events: list[Event]) -> Venue:
    del events
    sources: list[CapacitySource] = []
    candidates: list[int] = []
    llm_result: tuple[list[int], int | None, float] | None = None
    for url, html in html_pages.items():
        text = _strip_html(html)
        for pattern in CAPACITY_PATTERNS:
            for match in pattern.finditer(text):
                value = int(match.group(1))
                snippet = text[max(0, match.start()-60):match.end()+60]
                candidates.append(value)
                sources.append(CapacitySource(source_url=url, source_path_hint="body", extracted_value=value, extracted_text_snippet=snippet, method="regex"))
    if candidates:
        confidence = min(1.0, 0.45 + 0.15 * len(candidates))
        estimate = int(round(sum(candidates) / len(candidates)))
    else:
        llm_result = _capacity_from_llm(venue, html_pages)
        if llm_result:
            numbers, best, confidence = llm_result
            candidates = numbers or ([best] if best is not None else [])
            estimate = best if best is not None else (int(round(sum(candidates) / len(candidates))) if candidates else None)
            if estimate is not None:
                sources.append(CapacitySource(source_url=next(iter(html_pages.keys()), venue.website_url or ""), source_path_hint="llm-summary", extracted_value=estimate, extracted_text_snippet="LLM-derived from deterministic text excerpts", method="llm"))
        else:
            confidence = 0.0
            estimate = None
    venue.capacity_sources = sources
    venue.capacity_confidence = round(confidence, 3)
    if candidates and estimate is not None:
        venue.capacity_estimate = estimate
        venue.capacity_min = min(candidates)
        venue.capacity_max = max(candidates)
        venue.capacity_type = "standing"
    return venue


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def _capacity_from_llm(venue: Venue, html_pages: dict[str, str]) -> tuple[list[int], int | None, float] | None:
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL_CAPACITY", "llama3.1:8b")
    excerpts = []
    for url, html in list(html_pages.items())[:3]:
        text = re.sub(r"\s+", " ", _strip_html(html))[:4000]
        excerpts.append(f"URL: {url}\nTEXT: {text}")
    if not excerpts:
        return None
    prompt = f"Extract venue capacity numbers only from the provided venue text for {venue.name}."
    payload = {"model": model, "messages": [{"role": "user", "content": prompt + "\n\n" + "\n\n".join(excerpts)}], "format": CAPACITY_SCHEMA, "stream": False}
    try:
        response = httpx.post(f"{host}/api/chat", json=payload, timeout=45.0)
        response.raise_for_status()
        content = response.json().get("message", {}).get("content", "{}")
        data = json.loads(content)
        numbers = [int(n) for n in data.get("capacity_numbers", []) if isinstance(n, int)]
        best = data.get("best_estimate") if isinstance(data.get("best_estimate"), int) else None
        confidence = float(data.get("confidence", 0.0))
        return numbers, best, confidence
    except Exception:
        return None
