"""API contract tests."""

import pytest
from fastapi.testclient import TestClient

import src.api.main as api
from src.scoring import SpatialRiskEngine

client = TestClient(api.app)


@pytest.mark.integration
def test_health_reports_ok_when_database_and_spatial_extension_work():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "accidents": 180_734}


def test_health_reports_503_when_database_is_unusable(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "engine", SpatialRiskEngine(db_path=tmp_path / "missing.duckdb"))
    response = client.get("/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert str(tmp_path) not in response.text  # never leak filesystem paths


@pytest.mark.integration
def test_point_risk_returns_profile():
    response = client.get("/api/v1/risk/point", params={"lat": 65.0121, "lon": 25.4651})
    assert response.status_code == 200
    assert response.json()["total_accidents"] == 95


def test_point_risk_rejects_out_of_range_latitude():
    response = client.get("/api/v1/risk/point", params={"lat": 100, "lon": 25})
    assert response.status_code == 422


def test_route_risk_requires_at_least_one_waypoint():
    response = client.post("/api/v1/risk/route", json={"waypoints": []})
    assert response.status_code == 400
