from __future__ import annotations

from datetime import datetime


def parse(value: str):
    if not value:
        return None
    value = value.strip().replace('Z', '+00:00')
    for candidate in (value, value.replace(' at ', ' ')):
        try:
            return datetime.fromisoformat(candidate)
        except Exception:
            pass
    for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d', '%b %d %Y %I:%M %p', '%B %d, %Y %I:%M %p'):
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            pass
    return None
