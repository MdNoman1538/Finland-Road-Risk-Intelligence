"""The ingestion pipeline cleans the raw data reproducibly (Phase 0 data hygiene).

Uses tiny synthetic CSVs in both source formats (2014-21 "legacy" and 2022+ "modern"),
so it runs without the real raw data. Each row stands for a problem measured in the real
data on 2026-11-22 (see devlog).
"""

import duckdb
import pytest

from src.core.db import connect_spatial
from src.ingestion import clean
from src.ingestion.ingest_all import build_database, table_fingerprint
from src.scoring import RiskQuery, SpatialRiskEngine

LEGACY_ACC = """Onnett_id;Vuosi;Kk;Vakavuus;Nopraj;Pintasel;Valsel;Sääsel;Risteyssel;Ontyypsel;Maakuntsel;Kuntasel;Raskos;X;Y
9710903;2019;10;Kuolemaan johtanut;40;Ei arvoa;päivänvalo;kirkas;Unknown;kumoonajo  ajoradalla ;Pohjois-Karjala;Joensuu;on;640000;6945000
100;2019;5;Ei henkilövahinkoja;-1;-;Unknown;Ei arvoa;-;eläinonnettomuus ;Ei tiedossa;Unknown;ei arvoa;640100;6945100
101;2019;6;Loukkaantumiseen johtanut;80;jäinen;hämärä;lumisade;x;ohitus;Lappi;Rovaniemi;ei;;
"""
LEGACY_PART = """Onnett_id;Osall_id;Osnro;Oslajisel;Ajoneuvika;Ajoneuvmas
9710903;17333514;1;polkupyöräilijä;-1;-1
100;5;1;-;3;1500
101;6;1;henkilöauto;5;1200
"""
MODERN_ACC = """OnnettomuusID;Vuosi;Kuukausi;Vakavuus;Nopeusrajoitus;Pinta;Valoisuus;Sää;Liittymäjärjestelyt;Onnettomyystyyppi;Maakunta;Kunta;Raskaan liikenteen onnettomuus;x-koordinaatti;y-koordinaatti
9710903;2022;3;Ei henkilövahinkoja;;paljas, kuiva;päivänvalo;kirkas;-;eläinonnettomuus;Pohjois-Savo;Kuopio;true;530000;6970000
200;2022;4;Loukkaantumiseen johtanut;60;Ei arvoa;Ei arvoa;Ei arvoa;-;ohitus;Uusimaa;Helsinki;false;385000;6672000
"""
MODERN_PART = """OnnettomuusID;Tekninen osallinen ID;Osallisen numero;Osallisen lajikoodi;Ajoneuvon ikä;Ajoneuvon massa
9710903;17333514;1;henkilöauto;4;1300
200;7;1;Ei arvoa;;
"""


def _write_raw(root, legacy_acc=LEGACY_ACC):
    files = {
        "tieliikenneonnettomuudet_2019/tieliikenneonnettomuudet_2019_onnettomuus.csv": legacy_acc,
        "tieliikenneonnettomuudet_2019/tieliikenneonnettomuudet_2019_osallinen.csv": LEGACY_PART,
        "tieliikenneonnettomuudet_2022/tieliikenneonnettomuudet_2022_onnettomuus.csv": MODERN_ACC,
        "tieliikenneonnettomuudet_2022/tieliikenneonnettomuudet_2022_osalliset.csv": MODERN_PART,
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("build")
    db = tmp / "road_risk.duckdb"
    build_database(_write_raw(tmp / "raw"), db, quiet=True)
    con = connect_spatial(db)
    yield db, con
    con.close()


def _row(con, year, accident_id, cols):
    return con.execute(
        f"SELECT {cols} FROM road_accidents WHERE year = ? AND accident_id = ?", [year, accident_id]
    ).fetchone()


# --- the rules themselves -----------------------------------------------------------


@pytest.mark.parametrize(
    "raw", ["", "  ", "-", "Ei arvoa", "ei arvoa", "Unknown", "Ei tiedossa", "tuntematon"]
)
def test_every_missing_spelling_becomes_null(raw):
    con = duckdb.connect()
    assert con.execute(f"SELECT {clean.text('v')} FROM (SELECT ?::VARCHAR AS v)", [raw]).fetchone()[0] is None


def test_text_is_trimmed_and_inner_whitespace_collapsed():
    con = duckdb.connect()
    got = con.execute(
        f"SELECT {clean.text('v')} FROM (SELECT ' kumoonajo  ajoradalla '::VARCHAR AS v)"
    ).fetchone()
    assert got[0] == "kumoonajo ajoradalla"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("on", True), ("true", True), ("kyllä", True), ("Kyllä", True), ("ei", False), ("false", False)]
    + [("ei arvoa", None), ("", None), (None, None)],
)
def test_heavy_vehicle_spellings_map_to_one_boolean(raw, expected):
    con = duckdb.connect()
    assert (
        con.execute(f"SELECT {clean.heavy_vehicle('v')} FROM (SELECT ?::VARCHAR AS v)", [raw]).fetchone()[0]
        is expected
    )


def test_unknown_heavy_vehicle_spelling_stops_the_build_instead_of_guessing():
    con = duckdb.connect()
    with pytest.raises(duckdb.Error, match="heavy_vehicle"):
        con.execute(f"SELECT {clean.heavy_vehicle('v')} FROM (SELECT 'maybe'::VARCHAR AS v)").fetchone()


@pytest.mark.parametrize(
    ("raw", "expected"), [("40", 40), ("-1", None), ("0", None), ("", None), ("abc", None)]
)
def test_speed_limit_sentinels_become_null(raw, expected):
    con = duckdb.connect()
    assert (
        con.execute(f"SELECT {clean.speed_limit('v')} FROM (SELECT ?::VARCHAR AS v)", [raw]).fetchone()[0]
        == expected
    )


# --- the built database ----------------------------------------------------------------


def test_missing_values_are_null_in_both_formats(built):
    _, con = built
    assert _row(
        con, 2019, "100", "surface_condition, lighting, weather, junction_type, region, municipality"
    ) == (
        None,
        None,
        None,
        None,
        None,
        None,
    )
    assert _row(con, 2022, "200", "surface_condition, lighting, weather, junction_type") == (
        None,
        None,
        None,
        None,
    )


def test_speed_limit_and_heavy_vehicle_are_unified(built):
    _, con = built
    assert _row(con, 2019, "9710903", "speed_limit, heavy_vehicle") == (40, True)
    assert _row(con, 2019, "100", "speed_limit, heavy_vehicle") == (None, None)
    assert _row(con, 2022, "9710903", "speed_limit, heavy_vehicle") == (None, True)
    assert _row(con, 2022, "200", "speed_limit, heavy_vehicle") == (60, False)


def test_category_whitespace_is_normalised(built):
    _, con = built
    assert _row(con, 2019, "9710903", "accident_type")[0] == "kumoonajo ajoradalla"
    assert _row(con, 2019, "100", "accident_type")[0] == "eläinonnettomuus"


def test_reused_ids_are_kept_apart_by_year(built):
    """The source reuses accident and participant IDs across years for different events."""
    _, con = built
    assert con.execute("SELECT COUNT(*) FROM road_accidents WHERE accident_id = '9710903'").fetchone()[0] == 2
    dup = "SELECT COUNT(*) - COUNT(DISTINCT (year, accident_id)) FROM road_accidents"
    assert con.execute(dup).fetchone()[0] == 0
    parts = con.execute(
        "SELECT year, vehicle_type FROM accident_participants WHERE accident_id = '9710903' ORDER BY year"
    ).fetchall()
    assert parts == [(2019, "polkupyöräilijä"), (2022, "henkilöauto")]


def test_crashes_without_coordinates_are_quarantined_not_silently_dropped(built):
    _, con = built
    assert _row(con, 2019, "101", "1") is None
    rejects = con.execute(
        "SELECT table_name, year, accident_id, reason FROM ingest_rejects ORDER BY table_name"
    ).fetchall()
    assert rejects == [
        ("accident_participants", 2019, "101", "crash_not_loaded"),
        ("road_accidents", 2019, "101", "no_coordinates"),
    ]


def test_participant_cleaning(built):
    _, con = built
    rows = con.execute(
        "SELECT year, accident_id, vehicle_type, vehicle_age, vehicle_mass_kg FROM accident_participants ORDER BY year, accident_id"
    ).fetchall()
    assert rows == [
        (2019, "100", None, 3, 1500),
        (2019, "9710903", "polkupyöräilijä", None, None),
        (2022, "200", None, None, None),
        (2022, "9710903", "henkilöauto", 4, 1300),
    ]


def test_every_source_file_is_logged_with_its_checksum_and_counts(built):
    _, con = built
    log = con.execute(
        "SELECT kind, year, rows_read, rows_loaded, rows_rejected, length(sha256) FROM ingest_files ORDER BY kind, year"
    ).fetchall()
    assert log == [
        ("accidents", 2019, 3, 2, 1, 64),
        ("accidents", 2022, 2, 2, 0, 64),
        ("participants", 2019, 3, 2, 1, 64),
        ("participants", 2022, 2, 2, 0, 64),
    ]


def test_build_is_reproducible(built, tmp_path):
    """Same raw files -> same table contents, every time."""
    db, con = built
    again = tmp_path / "again.duckdb"
    build_database(_write_raw(tmp_path / "raw"), again, quiet=True)
    with connect_spatial(again) as con2:
        for table in ("road_accidents", "accident_participants", "ingest_rejects"):
            assert table_fingerprint(con, table) == table_fingerprint(con2, table), table


def test_a_failed_build_leaves_the_existing_database_untouched(tmp_path):
    db = tmp_path / "road_risk.duckdb"
    db.write_bytes(b"the previous good database")
    bad = LEGACY_ACC.replace(";on;640000", ";maybe;640000")
    with pytest.raises(duckdb.Error):
        build_database(_write_raw(tmp_path / "raw", legacy_acc=bad), db, quiet=True)
    assert db.read_bytes() == b"the previous good database"
    assert not list(tmp_path.glob("*.building*"))


def test_road_user_filter_does_not_match_a_crash_from_another_year(built):
    """Crash 9710903 had a cyclist in 2019. The unrelated 2022 crash with the same ID must
    not show up as a cyclist crash."""
    db, con = built
    lat22, lon22 = _row(con, 2022, "9710903", "lat, lon")
    lat19, lon19 = _row(con, 2019, "9710903", "lat, lon")
    engine = SpatialRiskEngine(db_path=db)
    try:
        cyclist = {"road_user_filter": "polkupyöräilijä", "radius_m": 50}
        assert engine.evaluate_point(RiskQuery(lat=lat19, lon=lon19, **cyclist)).total_accidents == 1
        assert engine.evaluate_point(RiskQuery(lat=lat22, lon=lon22, **cyclist)).total_accidents == 0
    finally:
        engine.close()
