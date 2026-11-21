"""API contract tests that do not touch the database."""

from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_point_risk_rejects_out_of_range_latitude():
    response = client.get("/api/v1/risk/point", params={"lat": 100, "lon": 25})
    assert response.status_code == 422


def test_route_risk_requires_at_least_one_waypoint():
    response = client.post("/api/v1/risk/route", json={"waypoints": []})
    assert response.status_code == 400
