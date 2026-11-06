"""Convert a Nike activity (with metrics) into a GPX 1.1 document."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from xml.sax.saxutils import escape


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _metric(activity: dict, name: str) -> list[dict]:
    for m in activity.get("metrics") or []:
        if m.get("type") == name:
            return m.get("values") or []
    return []


def has_gps(activity: dict) -> bool:
    return bool(_metric(activity, "latitude") and _metric(activity, "longitude"))


def build_gpx(activity: dict) -> Optional[str]:
    """Return GPX XML as a string, or None if the activity has no GPS data."""
    lat = _metric(activity, "latitude")
    lon = _metric(activity, "longitude")
    if not lat or not lon:
        return None

    elevation = {v["start_epoch_ms"]: v["value"] for v in _metric(activity, "elevation")}
    name = (activity.get("tags") or {}).get("com.nike.name") or "Nike Run Club run"

    points = []
    for la, lo in zip(lat, lon):
        t = la["start_epoch_ms"]
        ele = elevation.get(t)
        ele_tag = f"<ele>{ele}</ele>" if ele is not None else ""
        points.append(
            f'      <trkpt lat="{la["value"]}" lon="{lo["value"]}">'
            f"{ele_tag}<time>{_iso(t)}</time></trkpt>"
        )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gpx version="1.1" creator="nrc2gpx" xmlns="http://www.topografix.com/GPX/1/1">\n'
        f"  <metadata><time>{_iso(activity['start_epoch_ms'])}</time></metadata>\n"
        "  <trk>\n"
        f"    <name>{escape(name)}</name>\n"
        "    <type>running</type>\n"
        "    <trkseg>\n"
        + "\n".join(points)
        + "\n    </trkseg>\n  </trk>\n</gpx>\n"
    )
