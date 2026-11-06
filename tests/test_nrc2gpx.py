import xml.etree.ElementTree as ET
from datetime import date

import pytest

from nrc2gpx.api import RunSummary, clean_token
from nrc2gpx.cli import filter_by_date, fmt_duration, fmt_pace, parse_selection
from nrc2gpx.gpx import build_gpx

NS = {"g": "http://www.topografix.com/GPX/1/1"}
T0 = 1_793_900_000_000  # 2026-11-05


def make_activity(with_gps=True):
    metrics = []
    if with_gps:
        metrics = [
            {"type": "latitude", "values": [
                {"start_epoch_ms": T0, "value": 41.15},
                {"start_epoch_ms": T0 + 1000, "value": 41.151}]},
            {"type": "longitude", "values": [
                {"start_epoch_ms": T0, "value": -8.61},
                {"start_epoch_ms": T0 + 1000, "value": -8.611}]},
            {"type": "elevation", "values": [{"start_epoch_ms": T0, "value": 12.5}]},
        ]
    return {"id": "abc", "start_epoch_ms": T0,
            "tags": {"com.nike.name": "Evening Run & <fun>"}, "metrics": metrics}


def test_build_gpx_is_valid_xml():
    root = ET.fromstring(build_gpx(make_activity()))
    pts = root.findall(".//g:trkpt", NS)
    assert len(pts) == 2
    assert pts[0].get("lat") == "41.15"
    assert pts[0].find("g:ele", NS).text == "12.5"
    assert pts[1].find("g:ele", NS) is None
    assert root.find(".//g:name", NS).text == "Evening Run & <fun>"


def test_build_gpx_without_gps():
    assert build_gpx(make_activity(with_gps=False)) is None


@pytest.mark.parametrize("text,expected", [
    ("1", [0]),
    ("1,3", [0, 2]),
    ("2-4", [1, 2, 3]),
    ("4-2, 1", [0, 1, 2, 3]),
    ("all", [0, 1, 2, 3, 4]),
])
def test_parse_selection(text, expected):
    assert parse_selection(text, 5) == expected


@pytest.mark.parametrize("text", ["0", "6", "1-9", "x"])
def test_parse_selection_invalid(text):
    with pytest.raises(ValueError):
        parse_selection(text, 5)


def test_clean_token():
    assert clean_token("  Bearer abc ") == "abc"
    assert clean_token("abc") == "abc"


def test_run_summary_from_activity():
    r = RunSummary.from_activity({
        "id": "x", "start_epoch_ms": T0, "active_duration_ms": 1_500_000,
        "summaries": [{"metric": "distance", "summary": "total", "value": 5.0}],
        "metric_types": ["distance", "latitude", "longitude"],
    })
    assert r.distance_km == 5.0
    assert r.has_gps is True
    assert fmt_pace(r.pace_s_per_km) == "5:00/km"
    assert fmt_duration(r.duration_ms) == "25:00"


def test_filter_by_date():
    runs = [RunSummary.from_activity({"id": str(i), "start_epoch_ms": T0 + i * 86_400_000})
            for i in range(5)]
    d = runs[2].start.date()
    assert [r.id for r in filter_by_date(runs, d, d)] == ["2"]
    assert len(filter_by_date(runs, d, None)) == 3
    assert len(filter_by_date(runs, None, date(2000, 1, 1))) == 0
