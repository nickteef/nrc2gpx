"""Minimal client for the (undocumented) Nike Run Club API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterator, Optional

import requests

BASE_URL = "https://api.nike.com"
LIST_URL = BASE_URL + "/plus/v3/activities/before_id/v3/{before_id}"
DETAIL_URL = BASE_URL + "/sport/v3/me/activity/{activity_id}"
USER_AGENT = "Mozilla/5.0 (compatible; nrc2gpx)"


class NikeAPIError(Exception):
    """Any unexpected response from the Nike API."""


class AuthError(NikeAPIError):
    """The bearer token is missing, invalid or expired."""


@dataclass
class RunSummary:
    """Lightweight description of a run, taken from the activity list."""

    id: str
    start_ms: int
    duration_ms: Optional[int]
    distance_km: Optional[float]
    name: Optional[str]
    has_gps: Optional[bool]  # None = the list response doesn't say

    @property
    def start(self) -> datetime:
        return datetime.fromtimestamp(self.start_ms / 1000)

    @property
    def pace_s_per_km(self) -> Optional[float]:
        if self.duration_ms and self.distance_km:
            return self.duration_ms / 1000 / self.distance_km
        return None

    @classmethod
    def from_activity(cls, a: dict) -> "RunSummary":
        distance = None
        for s in a.get("summaries") or []:
            if s.get("metric") == "distance" and s.get("summary") == "total":
                distance = s.get("value")
        duration = a.get("active_duration_ms")
        if duration is None and a.get("end_epoch_ms") and a.get("start_epoch_ms"):
            duration = a["end_epoch_ms"] - a["start_epoch_ms"]
        metric_types = a.get("metric_types")
        has_gps = None if metric_types is None else "latitude" in metric_types
        return cls(
            id=a["id"],
            start_ms=a["start_epoch_ms"],
            duration_ms=duration,
            distance_km=distance,
            name=(a.get("tags") or {}).get("com.nike.name"),
            has_gps=has_gps,
        )


def clean_token(token: str) -> str:
    """Accept the token with or without a leading 'Bearer '."""
    token = token.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token


class NikeClient:
    def __init__(self, token: str, timeout: float = 30, session: Optional[requests.Session] = None):
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {clean_token(token)}",
            "User-Agent": USER_AGENT,
        })

    def _get(self, url: str, params: Optional[dict] = None) -> dict:
        r = self.session.get(url, params=params, timeout=self.timeout)
        if r.status_code in (401, 403):
            raise AuthError(
                "Nike rejected the token (HTTP %d). It has probably expired - "
                "tokens are valid for about one hour. Grab a fresh one." % r.status_code
            )
        if r.status_code == 404:
            raise NikeAPIError(
                f"Endpoint not found (HTTP 404): {r.url}\n"
                "Nike may have changed its API. Please open an issue."
            )
        if not r.ok:
            raise NikeAPIError(f"HTTP {r.status_code} for {r.url}: {r.text[:300]}")
        return r.json()

    def iter_activities(self, types: str = "run,jogging", page_size: int = 30) -> Iterator[dict]:
        """Yield all activities, newest first, following pagination."""
        seen: set[str] = set()
        before_id: Optional[str] = "*"
        params = {"limit": page_size, "types": types, "include_deleted": "false"}
        while before_id:
            data = self._get(LIST_URL.format(before_id=before_id), params)
            page = [a for a in data.get("activities") or [] if a.get("id") not in seen]
            if not page:
                return
            for a in page:
                seen.add(a["id"])
                yield a
            before_id = (data.get("paging") or {}).get("before_id")

    def list_runs(self) -> list[RunSummary]:
        runs = [RunSummary.from_activity(a) for a in self.iter_activities()]
        runs.sort(key=lambda r: r.start_ms, reverse=True)
        return runs

    def get_activity(self, activity_id: str) -> dict:
        """Full activity, including GPS, elevation and other metrics."""
        return self._get(DETAIL_URL.format(activity_id=activity_id), {"metrics": "ALL"})
