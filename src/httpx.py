from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class Response:
    def __init__(self, url: str, status_code: int, text: str, headers=None):
        self.url = url
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code} for {self.url}")

    def json(self):
        return json.loads(self.text)


def get(url: str, headers=None, timeout=20.0, follow_redirects=True):
    return request('GET', url, headers=headers, timeout=timeout)


def post(url: str, json=None, headers=None, timeout=20.0):
    body = None if json is None else __import__('json').dumps(json).encode('utf-8')
    headers = {**(headers or {}), 'Content-Type': 'application/json'} if body else (headers or {})
    return request('POST', url, data=body, headers=headers, timeout=timeout)


def request(method: str, url: str, data=None, headers=None, timeout=20.0):
    req = Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            return Response(url=resp.geturl(), status_code=getattr(resp, 'status', 200), text=resp.read().decode('utf-8', errors='replace'), headers=dict(resp.headers))
    except HTTPError as exc:
        return Response(url=url, status_code=exc.code, text=exc.read().decode('utf-8', errors='replace'))
    except URLError as exc:
        raise RuntimeError(str(exc))
