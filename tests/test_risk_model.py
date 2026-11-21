"""Unit tests for risk-engine logic that does not need the database."""

import pytest
from pydantic import ValidationError

from src.scoring import RiskQuery, SpatialRiskEngine


@pytest.mark.parametrize(
    ("score", "tier"),
    [
        (0.0, "LOW"),
        (24.9, "LOW"),
        (25.0, "MODERATE"),
        (49.9, "MODERATE"),
        (50.0, "HIGH"),
        (74.9, "HIGH"),
        (75.0, "CRITICAL"),
        (100.0, "CRITICAL"),
    ],
)
def test_tier_boundaries(score, tier):
    assert SpatialRiskEngine._classify_tier(score) == tier


def test_query_defaults():
    q = RiskQuery(lat=65.0, lon=25.0)
    assert q.radius_m == 250.0
    assert q.lang == "en"
    assert q.winter_only is False


@pytest.mark.parametrize(
    "bad",
    [
        {"lat": 91.0, "lon": 25.0},
        {"lat": 65.0, "lon": 181.0},
        {"lat": 65.0, "lon": 25.0, "radius_m": 0},
        {"lat": 65.0, "lon": 25.0, "radius_m": 10_001},
        {"lat": 65.0, "lon": 25.0, "lang": "sv"},
    ],
)
def test_query_rejects_invalid_input(bad):
    with pytest.raises(ValidationError):
        RiskQuery(**bad)
