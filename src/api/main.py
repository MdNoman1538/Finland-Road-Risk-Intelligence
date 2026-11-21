from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from src.scoring import RiskProfile, RiskQuery, SpatialRiskEngine

app = FastAPI(
    title="Finnish Road Risk Intelligence API",
    description="Spatial risk scoring backed by 2014–2025 Väylävirasto crash telemetry in DuckDB.",
    version="1.0.0",
)

engine = SpatialRiskEngine()


class RouteCorridorRequest(BaseModel):
    waypoints: list[tuple[float, float]]  # List of (lat, lon) pairs
    radius_m: float = 150.0
    winter_only: bool = False
    road_user_filter: str | None = None


class RouteCorridorResponse(BaseModel):
    waypoint_count: int
    max_risk_score: float
    mean_risk_score: float
    overall_tier: str
    segments: list[RiskProfile]


@app.get("/health")
def health_check():
    return {"status": "ok", "database": str(engine.db_path)}


@app.post("/api/v1/risk/point", response_model=RiskProfile)
def evaluate_point_risk(query: RiskQuery):
    try:
        return engine.evaluate_point(query)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/v1/risk/point", response_model=RiskProfile)
def evaluate_point_risk_get(
    lat: float = Query(..., ge=-90.0, le=90.0),
    lon: float = Query(..., ge=-180.0, le=180.0),
    radius_m: float = Query(250.0, gt=0.0, le=10000.0),
    winter_only: bool = Query(False),
    road_user_filter: str | None = Query(None),
):
    query = RiskQuery(
        lat=lat,
        lon=lon,
        radius_m=radius_m,
        winter_only=winter_only,
        road_user_filter=road_user_filter,
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
        overall_tier=engine._classify_tier(max_score),
        segments=profiles,
    )
