"""Raw Väylävirasto crash CSVs -> data/processed/road_risk.duckdb, reproducibly.

    uv run python src/ingestion/ingest_all.py [--raw-dir data/raw] [--output path]

Same raw files in -> same table contents out (tests/test_ingestion_cleaning.py builds twice
and compares). The cleaning rules live in src/ingestion/clean.py. Nothing is dropped
silently: rows that can't be used go to `ingest_rejects` with a reason, and every source
file is logged in `ingest_files` with its SHA-256 and row counts.

The build writes to `<output>.building` and renames it into place only on success, so a
failed build never leaves a broken database where the app would open it.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
from pathlib import Path

import duckdb
import pandas as pd

from src.core.db import connect_spatial
from src.core.paths import DB_PATH, PROJECT_ROOT
from src.ingestion import clean

RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"

__all__ = ["PROJECT_ROOT", "build_database", "detect_file_format", "get_unique_csvs", "table_fingerprint"]

# Source column for each target column, per file format. Values are SQL column references.
ACCIDENT_SOURCES = {
    "legacy": {  # 2014-2021
        "accident_id": "Onnett_id",
        "year": "Vuosi",
        "month": "Kk",
        "severity": "Vakavuus",
        "speed_limit": "Nopraj",
        "surface_condition": "Pintasel",
        "lighting": "Valsel",
        "weather": "Sääsel",
        "junction_type": "Risteyssel",
        "accident_type": "Ontyypsel",
        "region": "Maakuntsel",
        "municipality": "Kuntasel",
        "heavy_vehicle": "Raskos",
        "x": "X",
        "y": "Y",
    },
    "modern": {  # 2022+
        "accident_id": '"OnnettomuusID"',
        "year": "Vuosi",
        "month": "Kuukausi",
        "severity": "Vakavuus",
        "speed_limit": "Nopeusrajoitus",
        "surface_condition": "Pinta",
        "lighting": "Valoisuus",
        "weather": "Sää",
        "junction_type": "Liittymäjärjestelyt",
        "accident_type": "Onnettomyystyyppi",
        "region": '"Maakunta"',
        "municipality": "Kunta",
        "heavy_vehicle": '"Raskaan liikenteen onnettomuus"',
        "x": '"x-koordinaatti"',
        "y": '"y-koordinaatti"',
    },
}

PARTICIPANT_SOURCES = {
    "legacy": {"accident_id": "Onnett_id", "participant_id": "Osall_id", "participant_no": "Osnro",
               "vehicle_type": "Oslajisel", "vehicle_age": "Ajoneuvika", "vehicle_mass_kg": "Ajoneuvmas"},
    "modern": {"accident_id": '"OnnettomuusID"', "participant_id": '"Tekninen osallinen ID"',
               "participant_no": '"Osallisen numero"', "vehicle_type": '"Osallisen lajikoodi"',
               "vehicle_age": '"Ajoneuvon ikä"', "vehicle_mass_kg": '"Ajoneuvon massa"'},
}  # fmt: skip

SCHEMA = """
CREATE TABLE road_accidents (
    year INTEGER NOT NULL,            -- (year, accident_id) is the key: the source reuses IDs across years
    accident_id VARCHAR NOT NULL,
    month INTEGER,
    severity VARCHAR,
    speed_limit INTEGER,              -- km/h; NULL = not recorded
    surface_condition VARCHAR,        -- category columns: Finnish source spelling, NULL = not recorded
    lighting VARCHAR,
    weather VARCHAR,
    junction_type VARCHAR,
    accident_type VARCHAR,
    region VARCHAR,
    municipality VARCHAR,
    heavy_vehicle BOOLEAN,
    geom_3067 GEOMETRY NOT NULL,
    lat DOUBLE NOT NULL,
    lon DOUBLE NOT NULL
);
CREATE TABLE accident_participants (
    year INTEGER NOT NULL,
    accident_id VARCHAR NOT NULL,
    participant_id VARCHAR,
    participant_no INTEGER,
    vehicle_type VARCHAR,             -- lower-case Finnish; NULL = not recorded
    vehicle_age INTEGER,
    vehicle_mass_kg INTEGER
);
CREATE TABLE ingest_rejects (         -- rows that could not be used, and why
    table_name VARCHAR NOT NULL,
    year INTEGER,
    accident_id VARCHAR,
    participant_id VARCHAR,
    source_file VARCHAR NOT NULL,
    reason VARCHAR NOT NULL
);
CREATE TABLE ingest_files (           -- which raw files built this database
    kind VARCHAR NOT NULL,
    year INTEGER NOT NULL,
    source_file VARCHAR NOT NULL,
    sha256 VARCHAR NOT NULL,
    rows_read INTEGER NOT NULL,
    rows_loaded INTEGER NOT NULL,
    rows_rejected INTEGER NOT NULL
);
"""


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
            with open(csv_path, encoding=enc) as f:
                first_line = f.readline().strip()
                if not first_line:
                    continue
                delim = "\t" if first_line.count("\t") > first_line.count(";") else ";"
                cols = [c.strip().lstrip("﻿") for c in first_line.split(delim)]
                if len(cols) > 4:
                    return enc, delim, cols
        except UnicodeDecodeError:
            continue

    raise ValueError(f"Could not detect encoding/delimiter for {csv_path}")


def get_unique_csvs(
    keyword_include: list[str], keyword_exclude: list[str], raw_dir: Path = RAW_DATA_DIR
) -> list[Path]:
    all_csvs = sorted(raw_dir.glob("**/*.csv"))
    filtered = [
        p
        for p in all_csvs
        if any(k in p.name.lower() for k in keyword_include)
        and not any(k in p.name.lower() for k in keyword_exclude)
    ]
    unique = {}
    for p in filtered:
        if p.name not in unique:
            unique[p.name] = p
    return sorted(unique.values(), key=lambda x: x.name)


def _file_year(path: Path) -> int:
    match = re.search(r"_(\d{4})_", path.name)
    if not match:
        raise ValueError(f"No year in file name: {path.name}")
    return int(match.group(1))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _log_file(con, kind: str, path: Path, raw_dir: Path, read: int, loaded: int, rejected: int) -> None:
    con.execute(
        "INSERT INTO ingest_files VALUES (?, ?, ?, ?, ?, ?, ?)",
        [kind, _file_year(path), path.relative_to(raw_dir).as_posix(), _sha256(path), read, loaded, rejected],
    )


def _ingest_accident_file(con: duckdb.DuckDBPyConnection, path: Path, raw_dir: Path) -> None:
    enc, delim, cols = detect_file_format(path)
    duck_enc = "utf-8" if enc in ("utf-8", "utf-8-sig") else "ISO-8859-1"
    fmt = "legacy" if "Onnett_id" in cols else "modern"
    src = dict(ACCIDENT_SOURCES[fmt])
    if fmt == "modern" and "Maakunta (koordinaattien perusteella)" in cols:
        src["region"] = '"Maakunta (koordinaattien perusteella)"'
    year = _file_year(path)
    rel = path.relative_to(raw_dir).as_posix()
    csv = str(path).replace("'", "''")

    # ignore_errors=false: a malformed row stops the build instead of vanishing (all 12 real
    # files parse strictly, checked 2026-11-22).
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE stage AS
        SELECT
            CAST({src["year"]} AS INTEGER) AS year,
            TRIM(CAST({src["accident_id"]} AS VARCHAR)) AS accident_id,
            TRY_CAST({src["month"]} AS INTEGER) AS month,
            {clean.text(src["severity"])} AS severity,
            {clean.speed_limit(src["speed_limit"])} AS speed_limit,
            {clean.text(src["surface_condition"])} AS surface_condition,
            {clean.text(src["lighting"])} AS lighting,
            {clean.text(src["weather"])} AS weather,
            {clean.text(src["junction_type"])} AS junction_type,
            {clean.text(src["accident_type"])} AS accident_type,
            {clean.text(src["region"])} AS region,
            {clean.text(src["municipality"])} AS municipality,
            {clean.heavy_vehicle(src["heavy_vehicle"])} AS heavy_vehicle,
            TRY_CAST({src["x"]} AS DOUBLE) AS x,
            TRY_CAST({src["y"]} AS DOUBLE) AS y
        FROM read_csv('{csv}', header=true, delim='{delim}', encoding='{duck_enc}', auto_detect=true, ignore_errors=false)
    """)
    wrong_year = con.execute("SELECT COUNT(*) FROM stage WHERE year IS DISTINCT FROM ?", [year]).fetchone()[0]
    if wrong_year:  # participants get their year from the file name, so the two must agree
        raise ValueError(f"{rel}: {wrong_year} rows have a year other than {year}")

    con.execute("""
        INSERT INTO road_accidents
        SELECT year, accident_id, month, severity, speed_limit, surface_condition, lighting, weather,
               junction_type, accident_type, region, municipality, heavy_vehicle,
               ST_Point(x, y) AS geom_3067,
               ST_Y(ST_Transform(ST_Point(x, y), 'EPSG:3067', 'EPSG:4326', always_xy := true)) AS lat,
               ST_X(ST_Transform(ST_Point(x, y), 'EPSG:3067', 'EPSG:4326', always_xy := true)) AS lon
        FROM stage WHERE x IS NOT NULL AND y IS NOT NULL
    """)
    con.execute(
        """INSERT INTO ingest_rejects
           SELECT 'road_accidents', year, accident_id, NULL, ?, 'no_coordinates'
           FROM stage WHERE x IS NULL OR y IS NULL""",
        [rel],
    )
    read, rejected = con.execute(
        "SELECT COUNT(*), COUNT(*) FILTER (WHERE x IS NULL OR y IS NULL) FROM stage"
    ).fetchone()
    _log_file(con, "accidents", path, raw_dir, read, read - rejected, rejected)


def _ingest_participant_file(con: duckdb.DuckDBPyConnection, path: Path, raw_dir: Path) -> None:
    enc, delim, _ = detect_file_format(path)
    # pandas reads UTF-16 (the 2025 file) reliably. Everything stays a raw string here;
    # the cleaning is done by the same SQL rules as for accidents.
    df = pd.read_csv(path, sep=delim, encoding=enc, dtype=str, keep_default_na=False)
    df.columns = [c.strip().lstrip("﻿") for c in df.columns]
    src = PARTICIPANT_SOURCES["legacy" if "Onnett_id" in df.columns else "modern"]
    year = _file_year(path)
    rel = path.relative_to(raw_dir).as_posix()

    con.register("raw_participants", df)
    try:
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE pstage AS
            SELECT
                {year} AS year,
                TRIM({src["accident_id"]}) AS accident_id,
                {clean.text(src["participant_id"])} AS participant_id,
                TRY_CAST({src["participant_no"]} AS INTEGER) AS participant_no,
                {clean.lower_text(src["vehicle_type"])} AS vehicle_type,
                {clean.non_negative_int(src["vehicle_age"])} AS vehicle_age,
                {clean.positive_int(src["vehicle_mass_kg"])} AS vehicle_mass_kg
            FROM raw_participants
        """)
    finally:
        con.unregister("raw_participants")

    has_crash = (
        "EXISTS (SELECT 1 FROM road_accidents r WHERE r.year = s.year AND r.accident_id = s.accident_id)"
    )
    con.execute(f"INSERT INTO accident_participants SELECT s.* FROM pstage s WHERE {has_crash}")
    con.execute(
        f"""INSERT INTO ingest_rejects
            SELECT 'accident_participants', s.year, s.accident_id, s.participant_id, ?, 'crash_not_loaded'
            FROM pstage s WHERE NOT {has_crash}""",
        [rel],
    )
    read, loaded = con.execute(
        f"SELECT COUNT(*), COUNT(*) FILTER (WHERE {has_crash}) FROM pstage s"
    ).fetchone()
    _log_file(con, "participants", path, raw_dir, read, loaded, read - loaded)


def table_fingerprint(con: duckdb.DuckDBPyConnection, table: str) -> str:
    """SHA-256 of a table's contents in a fixed order: equal fingerprints = identical data.
    (The .duckdb file itself is not byte-stable between builds; its contents are.)"""
    columns = con.execute(f"DESCRIBE {table}").fetchall()
    exprs = [f"ST_AsText({name})" if typ.startswith("GEOMETRY") else name for name, typ, *_ in columns]
    rows = con.execute(f"SELECT {', '.join(exprs)} FROM {table} ORDER BY ALL").fetchall()
    return hashlib.sha256(repr(rows).encode()).hexdigest()


def build_database(raw_dir: Path = RAW_DATA_DIR, db_path: Path = DB_PATH, *, quiet: bool = False) -> dict:
    """Build the database from `raw_dir` into `db_path`, atomically. Returns summary counts."""
    say = (lambda *_: None) if quiet else print
    accident_csvs = get_unique_csvs(["onnettomuus", "onnettomuudet"], ["osalli"], raw_dir)
    participant_csvs = get_unique_csvs(["osallinen", "osalliset"], [], raw_dir)
    if not accident_csvs:
        raise FileNotFoundError(f"No accident CSVs under {raw_dir}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    building = db_path.with_name(db_path.name + ".building")
    for leftover in (building, building.with_name(building.name + ".wal")):
        leftover.unlink(missing_ok=True)

    try:
        con = connect_spatial(building, read_only=False)
        try:
            con.execute(SCHEMA)
            say(f"[1/2] {len(accident_csvs)} accident files")
            for path in accident_csvs:
                say(f"  -> {path.name}")
                _ingest_accident_file(con, path, raw_dir)
            say(f"[2/2] {len(participant_csvs)} participant files")
            for path in participant_csvs:
                say(f"  -> {path.name}")
                _ingest_participant_file(con, path, raw_dir)

            con.execute("CREATE INDEX idx_accidents_geom ON road_accidents USING RTREE (geom_3067);")
            con.execute("CREATE INDEX idx_accidents_key ON road_accidents (year, accident_id);")
            con.execute("CREATE INDEX idx_accidents_region_muni ON road_accidents (region, municipality);")
            con.execute("CREATE INDEX idx_part_key ON accident_participants (year, accident_id);")
            summary = _summary(con)
        finally:
            con.close()
        os.replace(building, db_path)  # atomic: the old database stays until the new one is complete
    finally:
        for leftover in (building, building.with_name(building.name + ".wal")):
            leftover.unlink(missing_ok=True)

    say(_report(summary))
    return summary


def _summary(con: duckdb.DuckDBPyConnection) -> dict:
    one = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
    return {
        "accidents": one("SELECT COUNT(*) FROM road_accidents"),
        "participants": one("SELECT COUNT(*) FROM accident_participants"),
        "rejects": dict(con.execute("SELECT table_name || ':' || reason, COUNT(*) FROM ingest_rejects GROUP BY 1 ORDER BY 1").fetchall()),
        "fingerprints": {t: table_fingerprint(con, t) for t in ("road_accidents", "accident_participants", "ingest_rejects")},
    }  # fmt: skip


def _report(s: dict) -> str:
    lines = [
        f"\nAccidents loaded:    {s['accidents']:,}",
        f"Participants loaded: {s['participants']:,}",
        "Rejected:",
    ]
    lines += [f"  {k}: {v:,}" for k, v in s["rejects"].items()] or ["  none"]
    lines += ["Content fingerprints (equal across builds = reproducible):"]
    lines += [f"  {t}: {fp[:16]}" for t, fp in s["fingerprints"].items()]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--raw-dir", type=Path, default=RAW_DATA_DIR)
    ap.add_argument("--output", type=Path, default=DB_PATH)
    args = ap.parse_args(argv)
    build_database(args.raw_dir, args.output)


if __name__ == "__main__":
    main()
