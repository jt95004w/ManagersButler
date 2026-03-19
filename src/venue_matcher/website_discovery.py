from __future__ import annotations

import posixpath
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import httpx
from selectolax.parser import HTMLParser

COMMON_CALENDAR_HINTS = ("calendar", "events", "shows", "concerts", "schedule", "tickets", "happenings")


def can_fetch(url: str, user_agent: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = robotparser.RobotFileParser()
    try:
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(user_agent, url)
    except Exception:
        return True


def discover_calendar_urls(website_url: str, user_agent: str) -> list[str]:
    response = httpx.get(website_url, headers={"User-Agent": user_agent}, timeout=15.0, follow_redirects=True)
    response.raise_for_status()
    tree = HTMLParser(response.text)
    seen: set[str] = set()
    matches: list[str] = []
    for node in tree.css("a[href]"):
        href = node.attributes.get("href", "").strip()
        text = (node.text() or "").strip().lower()
        if not href:
            continue
        abs_url = urljoin(str(response.url), href)
        path = urlparse(abs_url).path.lower()
        if any(hint in text or hint in path for hint in COMMON_CALENDAR_HINTS):
            normalized = _normalize_url(abs_url)
            if normalized not in seen:
                seen.add(normalized)
                matches.append(normalized)
    if not matches:
        for hint in COMMON_CALENDAR_HINTS:
            guess = _normalize_url(urljoin(str(response.url), hint))
            if urlparse(guess).netloc == urlparse(str(response.url)).netloc and guess not in seen:
                seen.add(guess)
                matches.append(guess)
    return matches[:10]


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    clean_path = posixpath.normpath(parsed.path or "/")
    return parsed._replace(fragment="", query="", path=clean_path).geturl()
