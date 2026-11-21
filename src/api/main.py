import logging
import uuid
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.scoring import RiskProfile, RiskQuery, SpatialRiskEngine

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Finnish Road Risk Intelligence API",
    description="Spatial risk scoring backed by 2014–2025 Väylävirasto crash telemetry in DuckDB.",
    # 2.0.0: RiskProfile.nearest_incidents was renamed highest_weighted_incidents (breaking).
    version="2.0.0",
)

engine = SpatialRiskEngine()


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    """Any unexpected error: full details to the server log, only an id to the client.

    Exception text can contain file paths, SQL and data values (known issue #10), so it
    never goes into the response. The id lets a user's report be matched to the log line.
    """
    error_id = uuid.uuid4().hex[:12]
    logger.error("Unhandled error %s on %s %s", error_id, request.method, request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error", "error_id": error_id})


class RouteCorridorRequest(BaseModel):
    waypoints: list[tuple[float, float]]  # List of (lat, lon) pairs
    radius_m: float = 150.0
    winter_only: bool = False
    road_user_filter: str | None = None
    lang: Literal["en", "fi"] = "en"


class RouteCorridorResponse(BaseModel):
    waypoint_count: int
    max_risk_score: float
    mean_risk_score: float
    overall_tier: str
    segments: list[RiskProfile]


@app.get("/health")
def health_check():
    """Readiness check that exercises the real dependencies: the database file AND the
    spatial extension. Render uses this path to decide whether a deploy is healthy, so a
    check that skips them reports "ok" while every risk endpoint fails (known issue #1).
    """
    try:
        con = engine.cursor()
        try:
            accidents = con.execute("SELECT COUNT(*) FROM road_accidents").fetchone()[0]
            con.execute("SELECT ST_Point(0, 0)").fetchone()
        finally:
            con.close()
    except Exception as exc:
        # Report the failure type only; never leak paths or internals to the client.
        return JSONResponse(status_code=503, content={"status": "unavailable", "error": type(exc).__name__})
    return {"status": "ok", "accidents": accidents}


@app.post("/api/v1/risk/point", response_model=RiskProfile)
def evaluate_point_risk(query: RiskQuery):
    return engine.evaluate_point(query)


@app.get("/api/v1/risk/point", response_model=RiskProfile)
def evaluate_point_risk_get(
    lat: float = Query(..., ge=-90.0, le=90.0),
    lon: float = Query(..., ge=-180.0, le=180.0),
    radius_m: float = Query(250.0, gt=0.0, le=10000.0),
    winter_only: bool = Query(False),
    road_user_filter: str | None = Query(None),
    lang: Literal["en", "fi"] = Query("en"),
):
    query = RiskQuery(
        lat=lat,
        lon=lon,
        radius_m=radius_m,
        winter_only=winter_only,
        road_user_filter=road_user_filter,
        lang=lang,
    )
    return engine.evaluate_point(query)


@app.post("/api/v1/risk/route", response_model=RouteCorridorResponse)
def evaluate_route_corridor(req: RouteCorridorRequest):
    if not req.waypoints:
        raise HTTPException(status_code=400, detail="At least one (lat, lon) waypoint is required.")

    profiles = [
        engine.evaluate_point(
            RiskQuery(
                lat=lat,
                lon=lon,
                radius_m=req.radius_m,
                winter_only=req.winter_only,
                road_user_filter=req.road_user_filter,
                lang=req.lang,
            )
        )
        for lat, lon in req.waypoints
    ]

    scores = [p.normalized_risk_score for p in profiles]
    max_score = max(scores)
    mean_score = round(sum(scores) / len(scores), 1)

    return RouteCorridorResponse(
        waypoint_count=len(profiles),
        max_risk_score=max_score,
        mean_risk_score=mean_score,
        overall_tier=engine.classify_tier(max_score),
        segments=profiles,
    )
