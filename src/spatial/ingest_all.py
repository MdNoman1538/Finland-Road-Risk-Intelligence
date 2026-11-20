from pathlib import Path
import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "processed" / "road_risk.duckdb"
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"


def detect_file_format(csv_path: Path) -> tuple[str, str, list[str]]:
    """Detects encoding ('utf-16', 'utf-8', 'ISO-8859-1'), delimiter (';' or '\\t'), and headers."""
    with open(csv_path, "rb") as f:
        bom = f.read(4)

    if bom.startswith(b"\xff\xfe") or bom.startswith(b"\xfe\xff"):
        encodings = ["utf-16"]
    elif bom.startswith(b"\xef\xbb\xbf"):
        encodings = ["utf-8-sig"]
    else:
        encodings = ["utf-8", "ISO-8859-1"]

    for enc in encodings:
        try:
            with open(csv_path, "r", encoding=enc) as f:
                first_line = f.readline().strip()
                if not first_line:
                    continue
                delim = "\t" if first_line.count("\t") > first_line.count(";") else ";"
                cols = [c.strip().lstrip("\ufeff") for c in first_line.split(delim)]
                if len(cols) > 4:
                    return enc, delim, cols
        except UnicodeDecodeError:
            continue

    raise ValueError(f"Could not detect encoding/delimiter for {csv_path}")


def get_unique_csvs(keyword_include: list[str], keyword_exclude: list[str]) -> list[Path]:
    all_csvs = sorted(RAW_DATA_DIR.glob("**/*.csv"))
    filtered = [
        p for p in all_csvs
        if any(k in p.name.lower() for k in keyword_include)
        and not any(k in p.name.lower() for k in keyword_exclude)
    ]
    unique = {}
    for p in filtered:
        if p.name not in unique:
            unique[p.name] = p
    return sorted(unique.values(), key=lambda x: x.name)


def ingest_accidents(con: duckdb.DuckDBPyConnection):
    accident_csvs = get_unique_csvs(["onnettomuus", "onnettomuudet"], ["osalli"])
    print(f"\n[1/2] Ingesting {len(accident_csvs)} Accident CSV files...")

    con.execute("DROP TABLE IF EXISTS road_accidents;")
    con.execute("""
        CREATE TABLE road_accidents (
            accident_id VARCHAR,
            year INTEGER,
            month INTEGER,
            severity VARCHAR,
            speed_limit INTEGER,
            surface_condition VARCHAR,
            lighting VARCHAR,
            weather VARCHAR,
            junction_type VARCHAR,
            accident_type VARCHAR,
            region VARCHAR,
            municipality VARCHAR,
            heavy_vehicle VARCHAR,
            geom_3067 GEOMETRY,
            lat DOUBLE,
            lon DOUBLE
        );
    """)

    for csv_path in accident_csvs:
        enc, delim, cols = detect_file_format(csv_path)
        duck_enc = "utf-8" if enc in ("utf-8", "utf-8-sig") else "ISO-8859-1"
        print(f"  -> {csv_path.name} ({len(cols)} cols, {duck_enc})")

        if "Onnett_id" in cols:
            # Legacy Schema (2014–2021)
            query = f"""
                INSERT INTO road_accidents
                SELECT 
                    CAST(Onnett_id AS VARCHAR) AS accident_id,
                    CAST(Vuosi AS INTEGER) AS year,
                    CAST(Kk AS INTEGER) AS month,
                    COALESCE(CAST(Vakavuus AS VARCHAR), 'Unknown') AS severity,
                    TRY_CAST(Nopraj AS INTEGER) AS speed_limit,
                    COALESCE(CAST(Pintasel AS VARCHAR), 'Unknown') AS surface_condition,
                    COALESCE(CAST(Valsel AS VARCHAR), 'Unknown') AS lighting,
                    COALESCE(CAST(Sääsel AS VARCHAR), 'Unknown') AS weather,
                    COALESCE(CAST(Risteyssel AS VARCHAR), 'Unknown') AS junction_type,
                    COALESCE(CAST(Ontyypsel AS VARCHAR), 'Unknown') AS accident_type,
                    COALESCE(NULLIF(TRIM(CAST(Maakuntsel AS VARCHAR)), ''), 'Unknown') AS region,
                    COALESCE(NULLIF(TRIM(CAST(Kuntasel AS VARCHAR)), ''), 'Unknown') AS municipality,
                    COALESCE(LOWER(CAST(Raskos AS VARCHAR)), 'ei') AS heavy_vehicle,
                    ST_Point(CAST(X AS DOUBLE), CAST(Y AS DOUBLE)) AS geom_3067,
                    ST_Y(ST_Transform(ST_Point(CAST(X AS DOUBLE), CAST(Y AS DOUBLE)), 'EPSG:3067', 'EPSG:4326', always_xy := true)) AS lat,
                    ST_X(ST_Transform(ST_Point(CAST(X AS DOUBLE), CAST(Y AS DOUBLE)), 'EPSG:3067', 'EPSG:4326', always_xy := true)) AS lon
                FROM read_csv('{csv_path}', header=true, delim='{delim}', encoding='{duck_enc}', auto_detect=true, ignore_errors=true)
                WHERE X IS NOT NULL AND Y IS NOT NULL;
            """
        else:
            # Modern Schema (2022–2025)
            region_col = '"Maakunta (koordinaattien perusteella)"' if "Maakunta (koordinaattien perusteella)" in cols else '"Maakunta"'
            query = f"""
                INSERT INTO road_accidents
                SELECT 
                    CAST("OnnettomuusID" AS VARCHAR) AS accident_id,
                    CAST(Vuosi AS INTEGER) AS year,
                    CAST(Kuukausi AS INTEGER) AS month,
                    COALESCE(CAST(Vakavuus AS VARCHAR), 'Unknown') AS severity,
                    TRY_CAST(Nopeusrajoitus AS INTEGER) AS speed_limit,
                    COALESCE(CAST(Pinta AS VARCHAR), 'Unknown') AS surface_condition,
                    COALESCE(CAST(Valoisuus AS VARCHAR), 'Unknown') AS lighting,
                    COALESCE(CAST(Sää AS VARCHAR), 'Unknown') AS weather,
                    COALESCE(CAST(Liittymäjärjestelyt AS VARCHAR), 'Unknown') AS junction_type,
                    COALESCE(CAST(Onnettomyystyyppi AS VARCHAR), 'Unknown') AS accident_type,
                    COALESCE(NULLIF(TRIM(CAST({region_col} AS VARCHAR)), ''), 'Unknown') AS region,
                    COALESCE(NULLIF(TRIM(CAST(Kunta AS VARCHAR)), ''), 'Unknown') AS municipality,
                    COALESCE(LOWER(CAST("Raskaan liikenteen onnettomuus" AS VARCHAR)), 'ei') AS heavy_vehicle,
                    ST_Point(CAST("x-koordinaatti" AS DOUBLE), CAST("y-koordinaatti" AS DOUBLE)) AS geom_3067,
                    ST_Y(ST_Transform(ST_Point(CAST("x-koordinaatti" AS DOUBLE), CAST("y-koordinaatti" AS DOUBLE)), 'EPSG:3067', 'EPSG:4326', always_xy := true)) AS lat,
                    ST_X(ST_Transform(ST_Point(CAST("x-koordinaatti" AS DOUBLE), CAST("y-koordinaatti" AS DOUBLE)), 'EPSG:3067', 'EPSG:4326', always_xy := true)) AS lon
                FROM read_csv('{csv_path}', header=true, delim='{delim}', encoding='{duck_enc}', auto_detect=true, ignore_errors=true)
                WHERE "x-koordinaatti" IS NOT NULL AND "y-koordinaatti" IS NOT NULL;
            """
        con.execute(query)

    print("  -> Building R-Tree spatial index on geom_3067...")
    con.execute("CREATE INDEX IF NOT EXISTS idx_accidents_geom ON road_accidents USING RTREE (geom_3067);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_accidents_id ON road_accidents (accident_id);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_accidents_region_muni ON road_accidents (region, municipality);")

def ingest_participants(con: duckdb.DuckDBPyConnection):
    part_csvs = get_unique_csvs(["osallinen", "osalliset"], [])
    print(f"\n[2/2] Ingesting {len(part_csvs)} Participant CSV files...")

    con.execute("DROP TABLE IF EXISTS accident_participants;")
    con.execute("""
        CREATE TABLE accident_participants (
            accident_id VARCHAR,
            participant_id VARCHAR,
            participant_no INTEGER,
            vehicle_type VARCHAR,
            vehicle_age INTEGER,
            vehicle_mass_kg INTEGER
        );
    """)

    for csv_path in part_csvs:
        enc, delim, cols = detect_file_format(csv_path)
        print(f"  -> {csv_path.name} ({len(cols)} cols, enc={enc}, delim={repr(delim)})")

        # Read with pandas to seamlessly handle UTF-16 LE (2025) as well as UTF-8 / ISO-8859-1
        df = pd.read_csv(csv_path, sep=delim, encoding=enc, low_memory=False)
        df.columns = [c.strip().lstrip("\ufeff") for c in df.columns]

        if "Onnett_id" in df.columns:
            # Legacy Schema (2014–2021)
            mapped = pd.DataFrame({
                "accident_id": df["Onnett_id"].astype(str),
                "participant_id": df["Osall_id"].astype(str),
                "participant_no": pd.to_numeric(df["Osnro"], errors="coerce"),
                "vehicle_type": df["Oslajisel"].fillna("Unknown").astype(str).str.lower().str.strip(),
                "vehicle_age": pd.to_numeric(df["Ajoneuvika"], errors="coerce"),
                "vehicle_mass_kg": pd.to_numeric(df["Ajoneuvmas"], errors="coerce"),
            })
        else:
            # Modern Schema (2022–2025)
            mapped = pd.DataFrame({
                "accident_id": df["OnnettomuusID"].astype(str),
                "participant_id": df["Tekninen osallinen ID"].astype(str),
                "participant_no": pd.to_numeric(df["Osallisen numero"], errors="coerce"),
                "vehicle_type": df["Osallisen lajikoodi"].fillna("Unknown").astype(str).str.lower().str.strip(),
                "vehicle_age": pd.to_numeric(df["Ajoneuvon ikä"], errors="coerce"),
                "vehicle_mass_kg": pd.to_numeric(df["Ajoneuvon massa"], errors="coerce"),
            })

        # Clean negative sentinel values (-1) used in legacy Finnish datasets
        mapped.loc[mapped["vehicle_age"] < 0, "vehicle_age"] = None
        mapped.loc[mapped["vehicle_mass_kg"] <= 0, "vehicle_mass_kg"] = None

        con.register("tmp_part_df", mapped)
        con.execute("INSERT INTO accident_participants SELECT * FROM tmp_part_df;")
        con.unregister("tmp_part_df")

    con.execute("CREATE INDEX IF NOT EXISTS idx_part_acc_id ON accident_participants (accident_id);")


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    con.execute("INSTALL spatial;")
    con.execute("LOAD spatial;")

    ingest_accidents(con)
    ingest_participants(con)

    # Verification checks
    acc_cnt = con.execute("SELECT COUNT(*) FROM road_accidents;").fetchone()[0]
    part_cnt = con.execute("SELECT COUNT(*) FROM accident_participants;").fetchone()[0]
    top_vehicles = con.execute("""
        SELECT vehicle_type, COUNT(*) AS cnt 
        FROM accident_participants 
        GROUP BY vehicle_type 
        ORDER BY cnt DESC 
        LIMIT 8;
    """).fetchall()
    oulu_winter = con.execute("""
        SELECT surface_condition, COUNT(*) 
        FROM road_accidents 
        WHERE municipality = 'Oulu' 
        GROUP BY surface_condition 
        ORDER BY COUNT(*) DESC 
        LIMIT 5;
    """).fetchall()

    print(f"\n=== STEP 1 COMPLETE ===")
    print(f"Total Accidents:    {acc_cnt:,}")
    print(f"Total Participants: {part_cnt:,}")
    print("\nTop Road User / Vehicle Categories:")
    for vtype, cnt in top_vehicles:
        print(f" - {vtype}: {cnt:,}")

    print("\nOulu Road Surface Breakdown:")
    for surf, cnt in oulu_winter:
        print(f" - {surf}: {cnt:,}")

    con.close()


if __name__ == "__main__":
    main()