import datetime
import heapq
import math
import threading
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import duckdb
from pydantic import BaseModel, Field

from src.core.db import DB_PATH, connect_spatial
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
    reference_year: int | None = Field(
        default=None,
        ge=2014,
        le=2100,
        description="Year that time decay counts back from. None = the latest year in the data.",
    )
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
    reference_year: int = Field(
        ..., description="Year time decay counted back from; later crashes are excluded"
    )
    total_accidents: int
    raw_severity_points: float
    decayed_risk_index: float
    normalized_risk_score: float = Field(..., description="0–100 calibrated spatial risk score")
    risk_tier: str
    severity_breakdown: dict[str, int]
    top_surface_conditions: dict[str, int]
    top_accident_types: dict[str, int]
    highest_weighted_incidents: list[AccidentSummary] = Field(
        ..., description="Up to 15 incidents with the highest weighted_score (severity × recency × proximity)"
    )


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
        self._latest_year: int | None = None

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
            self._latest_year = None  # a reconnect may see refreshed data

    def latest_data_year(self) -> int:
        """The newest crash year in the database: the default "now" for time decay.

        Read once per connection (the database is read-only while the app runs). A data
        refresh is picked up after a restart or close(), never frozen in code (known issue
        #4). With no years at all (empty table) it falls back to the calendar year.
        """
        if self._latest_year is None:
            con = self.cursor()
            try:
                latest = con.execute("SELECT MAX(year) FROM road_accidents").fetchone()[0]
            finally:
                con.close()
            self._latest_year = int(latest) if latest is not None else datetime.date.today().year
        return self._latest_year

    @staticmethod
    def classify_tier(score: float) -> str:
        if score >= 75.0:
            return "CRITICAL"
        if score >= 50.0:
            return "HIGH"
        if score >= 25.0:
            return "MODERATE"
        return "LOW"

    def evaluate_point(self, query: RiskQuery) -> RiskProfile:
        reference_year = query.reference_year if query.reference_year is not None else self.latest_data_year()

        # Every value goes in as a parameter, never spliced into the SQL text.
        params: list = [query.lon, query.lat]

        def param(value) -> str:
            params.append(value)
            return f"${len(params)}"

        where_clauses = [f"ST_DWithin(r.geom_3067, t.pt, {param(query.radius_m)})"]
        # Risk "as of" a year must not see later crashes (they would get full weight).
        where_clauses.append(f"(r.year IS NULL OR r.year <= {param(reference_year)})")
        if query.winter_only:
            where_clauses.append(f"LOWER(r.surface_condition) = ANY({param(list(WINTER_SURFACES))})")

        join_clause = ""
        if query.road_user_filter:
            join_clause = f"""
                INNER JOIN (
                    SELECT DISTINCT year, accident_id
                    FROM accident_participants
                    WHERE vehicle_type = LOWER({param(query.road_user_filter.strip())})
                ) p ON r.year = p.year AND r.accident_id = p.accident_id  -- IDs repeat across years
            """

        con = self.cursor()
        try:
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

        # Count the canonical Finnish values; translate each distinct value once afterwards.
        severity_raw: Counter[str] = Counter()
        surface_raw: Counter[str] = Counter()
        type_raw: Counter[str] = Counter()
        scored: list[tuple[float, tuple]] = []

        for row in rows:
            (_, year, _, severity, surface, _, _, acc_type, dist_m, _, _) = row

            w_sev = SEVERITY_WEIGHTS.get(severity, 1.0)
            age_years = max(0, reference_year - (year or reference_year))
            w_time = math.exp(-decay_lambda * age_years)
            w_dist = max(0.05, 1.0 - (dist_m / query.radius_m))

            incident_score = w_sev * w_time * w_dist
            raw_points += w_sev
            decayed_index += incident_score

            severity_raw[severity] += 1
            surface_raw[surface] += 1
            type_raw[acc_type] += 1
            scored.append((round(incident_score, 3), row))

        area_scale = (query.radius_m / 250.0) ** 2
        density_adjusted = decayed_index / max(0.25, area_scale)
        normalized_score = round(100.0 * (1.0 - math.exp(-density_adjusted / 25.0)), 1)

        # Only the returned incidents become objects (known issue #11: building all 4,659 at
        # Helsinki 2 km and keeping 15 dominated the time). nlargest equals a stable sort's top 15.
        top_rows = heapq.nlargest(15, scored, key=lambda s: s[0])
        top_incidents = [self._summary(row, score, query.lang) for score, row in top_rows]

        severity_counts = _translated_counts(severity_raw, translate_severity, query.lang)
        surface_counts = _translated_counts(surface_raw, translate_surface, query.lang)
        type_counts = _translated_counts(type_raw, translate_accident_type, query.lang)
        top_surfaces = dict(sorted(surface_counts.items(), key=lambda x: x[1], reverse=True)[:5])
        top_types = dict(sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:5])

        return RiskProfile(
            lat=query.lat,
            lon=query.lon,
            radius_m=query.radius_m,
            lang=query.lang,
            reference_year=reference_year,
            total_accidents=len(rows),
            raw_severity_points=round(raw_points, 2),
            decayed_risk_index=round(decayed_index, 2),
            normalized_risk_score=normalized_score,
            risk_tier=self.classify_tier(normalized_score),
            severity_breakdown=severity_counts,
            top_surface_conditions=top_surfaces,
            top_accident_types=top_types,
            highest_weighted_incidents=top_incidents,
        )

    @staticmethod
    def _summary(row: tuple, weighted_score: float, lang: str) -> AccidentSummary:
        (acc_id, year, month, severity, surface, lighting, speed_limit, acc_type, dist_m, lat, lon) = row
        return AccidentSummary(
            accident_id=acc_id,
            year=year,
            month=month,
            severity=translate_severity(severity, lang),
            surface_condition=translate_surface(surface, lang),
            lighting=translate_lighting(lighting, lang),
            speed_limit=speed_limit,
            accident_type=translate_accident_type(acc_type, lang),
            distance_m=dist_m,
            weighted_score=weighted_score,
            lat=lat,
            lon=lon,
        )


def _translated_counts(raw: Counter[str], translate: Callable[[str, str], str], lang: str) -> dict[str, int]:
    """Translate count keys. Two raw values can share a label (e.g. different spellings of
    "missing"), so counts are summed. Keys keep first-appearance order, as before."""
    out: dict[str, int] = {}
    for value, count in raw.items():
        label = translate(value, lang)
        out[label] = out.get(label, 0) + count
    return out
