import math
import threading
from pathlib import Path
from typing import Literal

import duckdb
from pydantic import BaseModel, Field

from src.db import DB_PATH, connect_spatial
from src.i18n import (
    translate_accident_type,
    translate_lighting,
    translate_severity,
    translate_surface,
)

SEVERITY_WEIGHTS: dict[str, float] = {
    "Kuolemaan johtanut": 10.0,
    "Vakavaan loukkaantumiseen johtanut": 5.0,
    "Loukkaantumiseen johtanut": 3.0,
    "Ei henkilövahinkoja": 1.0,
}

WINTER_SURFACES = ("jäinen", "luminen", "sohjoinen", "polanteinen", "kuura")


class RiskQuery(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0, description="WGS84 Latitude")
    lon: float = Field(..., ge=-180.0, le=180.0, description="WGS84 Longitude")
    radius_m: float = Field(default=250.0, gt=0.0, le=10000.0, description="Search radius in meters")
    reference_year: int = Field(default=2025, ge=2014, le=2030)
    half_life_years: float = Field(default=5.0, gt=0.0)
    winter_only: bool = Field(default=False, description="Filter to icy/snowy/slushy road surfaces")
    road_user_filter: str | None = Field(
        default=None,
        description="Optional participant filter, e.g. 'polkupyöräilijä', 'jalankulkija', 'hirvi', 'kuorma-auto'",
    )
    lang: Literal["en", "fi"] = Field(default="en", description="Output language ('en' or 'fi')")


class AccidentSummary(BaseModel):
    accident_id: str
    year: int
    month: int | None
    severity: str
    surface_condition: str
    lighting: str
    speed_limit: int | None
    accident_type: str
    distance_m: float
    weighted_score: float
    lat: float
    lon: float


class RiskProfile(BaseModel):
    lat: float
    lon: float
    radius_m: float
    lang: str
    total_accidents: int
    raw_severity_points: float
    decayed_risk_index: float
    normalized_risk_score: float = Field(..., description="0–100 calibrated spatial risk score")
    risk_tier: str
    severity_breakdown: dict[str, int]
    top_surface_conditions: dict[str, int]
    top_accident_types: dict[str, int]
    nearest_incidents: list[AccidentSummary]


class SpatialRiskEngine:
    """Radius-based spatial risk scoring over the DuckDB crash warehouse.

    Holds ONE database connection for its lifetime (opening a connection and loading
    the spatial extension costs ~56 ms, measured 2026-11-21, see ADR-0003). Each unit of
    work uses its own cursor, because a DuckDB connection must not be shared between
    threads (FastAPI runs sync endpoints in a thread pool), while cursors may.
    """

    def __init__(self, db_path: Path = DB_PATH, extension_directory: Path | None = None):
        self.db_path = db_path
        # Where DuckDB stores extensions. None = DuckDB default (~/.duckdb/extensions).
        # Tests point this at an empty directory to simulate a fresh machine.
        self.extension_directory = extension_directory
        self._con: duckdb.DuckDBPyConnection | None = None
        self._con_lock = threading.Lock()

    def _connection(self) -> duckdb.DuckDBPyConnection:
        # Lazy, so that creating the engine (e.g. at API import time) never touches the DB.
        if self._con is None:
            with self._con_lock:
                if self._con is None:  # double-checked: another thread may have won the race
                    self._con = connect_spatial(self.db_path, extension_directory=self.extension_directory)
        return self._con

    def cursor(self) -> duckdb.DuckDBPyConnection:
        """A thread-safe handle for one unit of work. Close it when done."""
        return self._connection().cursor()

    def close(self) -> None:
        with self._con_lock:
            if self._con is not None:
                self._con.close()
                self._con = None

    @staticmethod
    def _classify_tier(score: float) -> str:
        if score >= 75.0:
            return "CRITICAL"
        if score >= 50.0:
            return "HIGH"
        if score >= 25.0:
            return "MODERATE"
        return "LOW"

    def evaluate_point(self, query: RiskQuery) -> RiskProfile:
        con = self.cursor()
        try:
            where_clauses = ["ST_DWithin(r.geom_3067, t.pt, $3)"]
            params: list = [query.lon, query.lat, query.radius_m]

            if query.winter_only:
                placeholders = ", ".join([f"'{s}'" for s in WINTER_SURFACES])
                where_clauses.append(f"LOWER(r.surface_condition) IN ({placeholders})")

            join_clause = ""
            if query.road_user_filter:
                join_clause = """
                    INNER JOIN (
                        SELECT DISTINCT accident_id
                        FROM accident_participants
                        WHERE LOWER(vehicle_type) = LOWER($4)
                    ) p ON r.accident_id = p.accident_id
                """
                params.append(query.road_user_filter.strip())

            sql = f"""
                WITH target AS (
                    SELECT ST_Transform(ST_Point($1, $2), 'EPSG:4326', 'EPSG:3067', always_xy := true) AS pt
                )
                SELECT
                    r.accident_id,
                    r.year,
                    r.month,
                    r.severity,
                    r.surface_condition,
                    r.lighting,
                    r.speed_limit,
                    r.accident_type,
                    ROUND(ST_Distance(r.geom_3067, t.pt), 2) AS distance_m,
                    r.lat,
                    r.lon
                FROM road_accidents r
                CROSS JOIN target t
                {join_clause}
                WHERE {" AND ".join(where_clauses)}
                ORDER BY distance_m ASC;
            """

            rows = con.execute(sql, params).fetchall()
        finally:
            con.close()

        decay_lambda = math.log(2.0) / query.half_life_years
        raw_points = 0.0
        decayed_index = 0.0

        severity_counts: dict[str, int] = {}
        surface_counts: dict[str, int] = {}
        type_counts: dict[str, int] = {}
        scored_incidents: list[AccidentSummary] = []

        for row in rows:
            (acc_id, year, month, severity, surface, lighting, speed_limit, acc_type, dist_m, lat, lon) = row

            # Always compute weight using canonical Finnish severity key
            w_sev = SEVERITY_WEIGHTS.get(severity, 1.0)
            age_years = max(0, query.reference_year - (year or query.reference_year))
            w_time = math.exp(-decay_lambda * age_years)
            w_dist = max(0.05, 1.0 - (dist_m / query.radius_m))

            incident_score = w_sev * w_time * w_dist
            raw_points += w_sev
            decayed_index += incident_score

            # Translate output fields according to requested language
            sev_label = translate_severity(severity, query.lang)
            surf_label = translate_surface(surface, query.lang)
            light_label = translate_lighting(lighting, query.lang)
            type_label = translate_accident_type(acc_type, query.lang)

            severity_counts[sev_label] = severity_counts.get(sev_label, 0) + 1
            surface_counts[surf_label] = surface_counts.get(surf_label, 0) + 1
            type_counts[type_label] = type_counts.get(type_label, 0) + 1

            scored_incidents.append(
                AccidentSummary(
                    accident_id=acc_id,
                    year=year,
                    month=month,
                    severity=sev_label,
                    surface_condition=surf_label,
                    lighting=light_label,
                    speed_limit=speed_limit,
                    accident_type=type_label,
                    distance_m=dist_m,
                    weighted_score=round(incident_score, 3),
                    lat=lat,
                    lon=lon,
                )
            )

        area_scale = (query.radius_m / 250.0) ** 2
        density_adjusted = decayed_index / max(0.25, area_scale)
        normalized_score = round(100.0 * (1.0 - math.exp(-density_adjusted / 25.0)), 1)

        top_incidents = sorted(scored_incidents, key=lambda x: x.weighted_score, reverse=True)[:15]
        top_surfaces = dict(sorted(surface_counts.items(), key=lambda x: x[1], reverse=True)[:5])
        top_types = dict(sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:5])

        return RiskProfile(
            lat=query.lat,
            lon=query.lon,
            radius_m=query.radius_m,
            lang=query.lang,
            total_accidents=len(rows),
            raw_severity_points=round(raw_points, 2),
            decayed_risk_index=round(decayed_index, 2),
            normalized_risk_score=normalized_score,
            risk_tier=self._classify_tier(normalized_score),
            severity_breakdown=severity_counts,
            top_surface_conditions=top_surfaces,
            top_accident_types=top_types,
            nearest_incidents=top_incidents,
        )
