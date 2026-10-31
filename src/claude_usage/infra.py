"""Small I/O adapters: HTTP client and JSON file cache."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol

from .domain import Clock


@dataclass
class HttpResponse:
    status: int
    headers: Dict[str, str] = field(default_factory=dict)  # lower-case names
    body: bytes = b""

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


class HttpClient(Protocol):
    def request(self, url: str, method: str = "GET", headers: Optional[Dict[str, str]] = None,
                body: Optional[bytes] = None, timeout: float = 15) -> HttpResponse: ...


class UrllibHttpClient:
    """HttpClient over urllib. An HTTP error status is a response, not an exception;
    network failures still raise (URLError, timeout)."""

    def request(self, url: str, method: str = "GET", headers: Optional[Dict[str, str]] = None,
                body: Optional[bytes] = None, timeout: float = 15) -> HttpResponse:
        req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return HttpResponse(r.status, _lower_headers(r.headers), r.read())
        except urllib.error.HTTPError as e:
            return HttpResponse(e.code, _lower_headers(e.headers), e.read() or b"")


def _lower_headers(headers) -> Dict[str, str]:
    return {k.lower(): v for k, v in headers.items()} if headers else {}


class JsonCache:
    """Named JSON documents in one directory, with their age."""

    def __init__(self, directory: str, clock: Clock):
        self.directory = directory
        self._clock = clock

    def path(self, name: str) -> str:
        return os.path.join(self.directory, name + ".json")

    def load(self, name: str) -> Any:
        try:
            with open(self.path(name), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def save(self, name: str, data: Any) -> None:
        os.makedirs(self.directory, exist_ok=True)
        tmp = self.path(name) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, self.path(name))

    def age(self, name: str) -> float:
        try:
            return self._clock.now() - os.path.getmtime(self.path(name))
        except OSError:
            return float("inf")

    def fresh(self, name: str, max_age: float) -> Any:
        """The document if it is younger than max_age seconds, else None."""
        return self.load(name) if self.age(name) < max_age else None
