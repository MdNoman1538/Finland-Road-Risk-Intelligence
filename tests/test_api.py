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


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("post", "/api/v1/risk/point", {"json": {"lat": 65.0, "lon": 25.0}}),
        ("get", "/api/v1/risk/point", {"params": {"lat": 65.0, "lon": 25.0}}),
        ("post", "/api/v1/risk/route", {"json": {"waypoints": [[65.0, 25.0]]}}),
    ],
)
def test_internal_errors_do_not_leak_details(monkeypatch, tmp_path, method, path, kwargs):
    """Known issue #10: a 500 must not reveal paths, SQL or exception text to the client.
    The full error goes to the server log under an id the client can quote."""
    monkeypatch.setattr(api, "engine", SpatialRiskEngine(db_path=tmp_path / "secret-dir" / "missing.duckdb"))
    unsafe_client = TestClient(api.app, raise_server_exceptions=False)
    response = getattr(unsafe_client, method)(path, **kwargs)
    assert response.status_code == 500
    assert "secret-dir" not in response.text
    assert "duckdb" not in response.text.lower()
    body = response.json()
    assert body["detail"] == "Internal server error"
    assert len(body["error_id"]) == 12


def test_internal_error_details_go_to_the_server_log(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(api, "engine", SpatialRiskEngine(db_path=tmp_path / "secret-dir" / "missing.duckdb"))
    unsafe_client = TestClient(api.app, raise_server_exceptions=False)
    with caplog.at_level("ERROR", logger="src.api.main"):
        response = unsafe_client.get("/api/v1/risk/point", params={"lat": 65.0, "lon": 25.0})
    error_id = response.json()["error_id"]
    record = next(r for r in caplog.records if error_id in r.getMessage())
    assert record.exc_info is not None
    assert "secret-dir" in str(record.exc_info[1])  # the operator still sees the real cause


@pytest.mark.integration
def test_get_point_risk_supports_finnish_labels():
    """Known issue #6: the GET endpoint ignored lang, so it always answered in English."""
    response = client.get("/api/v1/risk/point", params={"lat": 65.0121, "lon": 25.4651, "lang": "fi"})
    assert response.status_code == 200
    body = response.json()
    assert body["lang"] == "fi"
    assert "Ei henkilövahinkoja" in body["severity_breakdown"]


def test_get_point_risk_rejects_unknown_language():
    response = client.get("/api/v1/risk/point", params={"lat": 65.0, "lon": 25.0, "lang": "sv"})
    assert response.status_code == 422
