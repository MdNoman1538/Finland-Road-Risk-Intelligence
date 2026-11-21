from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "processed" / "road_risk.duckdb"


def test_radius_lookup(lat: float = 65.0121, lon: float = 25.4651, radius_m: float = 500.0):
    con = duckdb.connect(str(DB_PATH), read_only=True)
    con.execute("LOAD spatial;")

    # Transform query point (WGS84) -> EPSG:3067 (meters) and query using R-Tree index via ST_DWithin
    results = con.execute(
        """
        WITH target AS (
            SELECT ST_Transform(ST_Point($1, $2), 'EPSG:4326', 'EPSG:3067', always_xy := true) AS pt
        )
        SELECT
            r.year,
            r.severity,
            ROUND(ST_Distance(r.geom_3067, t.pt), 1) AS distance_m,
            r.lat,
            r.lon
        FROM road_accidents r, target t
        WHERE ST_DWithin(r.geom_3067, t.pt, $3)
        ORDER BY distance_m ASC
        LIMIT 10;
    """,
        [lon, lat, radius_m],
    ).fetchall()

    total_nearby = con.execute(
        """
        WITH target AS (
            SELECT ST_Transform(ST_Point($1, $2), 'EPSG:4326', 'EPSG:3067', always_xy := true) AS pt
        )
        SELECT COUNT(*)
        FROM road_accidents r, target t
        WHERE ST_DWithin(r.geom_3067, t.pt, $3);
    """,
        [lon, lat, radius_m],
    ).fetchone()[0]

    print(f"Found {total_nearby} accidents within {radius_m}m of ({lat}, {lon}). Closest 10:")
    for row in results:
        print(f" - Year {row[0]} | {row[1]} | {row[2]}m away ({row[3]:.5f}, {row[4]:.5f})")

    con.close()


if __name__ == "__main__":
    test_radius_lookup()
