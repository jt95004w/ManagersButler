from __future__ import annotations

import os
import threading
import time
from collections import defaultdict
from urllib.parse import urlparse

import httpx

_HOST_LOCKS: dict[str, threading.BoundedSemaphore] = {}
_HOST_LAST_REQUEST: dict[str, float] = defaultdict(float)
_BACKOFFS = (0.0, 0.5, 1.0)


def _host_limit(host: str) -> threading.BoundedSemaphore:
    if host not in _HOST_LOCKS:
        _HOST_LOCKS[host] = threading.BoundedSemaphore(max(1, int(os.getenv("SCRAPER_MAX_CONCURRENCY", "4"))))
    return _HOST_LOCKS[host]


def fetch_html(url: str, user_agent: str, timeout_s: float) -> str:
    host = urlparse(url).netloc
    gate = _host_limit(host)
    response = None
    for backoff in _BACKOFFS:
        if backoff:
            time.sleep(backoff)
        with gate:
            delta = time.time() - _HOST_LAST_REQUEST[host]
            if delta < 0.25:
                time.sleep(0.25 - delta)
            response = httpx.get(url, headers={"User-Agent": user_agent}, timeout=timeout_s, follow_redirects=True)
            _HOST_LAST_REQUEST[host] = time.time()
        if response.status_code < 500:
            response.raise_for_status()
            return response.text
    assert response is not None
    response.raise_for_status()
    return response.text
