"""Integration tests for SpatialRiskEngine against the real DuckDB warehouse."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from src.scoring import RiskQuery, SpatialRiskEngine

pytestmark = pytest.mark.integration

OULU_250 = RiskQuery(lat=65.0121, lon=25.4651, radius_m=250)
HELSINKI_2000 = RiskQuery(lat=60.1699, lon=24.9384, radius_m=2000)


@pytest.fixture(scope="module")
def engine():
    eng = SpatialRiskEngine()
    yield eng
    eng.close()


@pytest.mark.parametrize(
    ("query", "accidents", "score", "tier"),
    [
        (OULU_250, 95, 57.8, "HIGH"),
        (HELSINKI_2000, 4659, 50.9, "HIGH"),
    ],
)
def test_characterization_current_scores(engine, query, accidents, score, tier):
    """Characterization test: pins today's outputs (recorded 2026-11-21) so refactors
    can be proven behaviour-neutral. When the data or scoring method changes ON PURPOSE,
    update these numbers in the same PR and explain why in the PR description."""
    profile = engine.evaluate_point(query)
    assert (profile.total_accidents, profile.normalized_risk_score, profile.risk_tier) == (
        accidents,
        score,
        tier,
    )


def test_connection_is_reused_across_calls(engine):
    engine.evaluate_point(OULU_250)
    first = engine._con
    engine.evaluate_point(OULU_250)
    assert engine._con is first


def test_concurrent_calls_from_many_threads_give_identical_results(engine):
    # FastAPI runs sync endpoints in a thread pool: the engine must be safe under concurrency.
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: engine.evaluate_point(OULU_250).total_accidents, range(40)))
    assert set(results) == {95}


def test_close_then_reuse_reconnects(engine):
    engine.close()
    assert engine.evaluate_point(OULU_250).total_accidents == 95


def test_latest_data_year_comes_from_the_data(engine):
    con = engine.cursor()
    try:
        expected = con.execute("SELECT MAX(year) FROM road_accidents").fetchone()[0]
    finally:
        con.close()
    assert engine.latest_data_year() == expected


def test_default_reference_year_matches_explicit_latest_year(engine):
    implicit = engine.evaluate_point(OULU_250)
    explicit = engine.evaluate_point(
        OULU_250.model_copy(update={"reference_year": engine.latest_data_year()})
    )
    assert implicit == explicit
    assert implicit.reference_year == engine.latest_data_year()  # the response says which year it used


def test_past_reference_year_ignores_later_crashes(engine):
    """Risk "as of 2018" must not count 2019-2025 crashes (they used to get full weight)."""
    as_of_2018 = engine.evaluate_point(HELSINKI_2000.model_copy(update={"reference_year": 2018}))
    assert as_of_2018.reference_year == 2018
    assert 0 < as_of_2018.total_accidents < 4659
    assert all(i.year <= 2018 for i in as_of_2018.highest_weighted_incidents)


def test_winter_filter_still_matches(engine):
    winter = engine.evaluate_point(HELSINKI_2000.model_copy(update={"winter_only": True}))
    assert 0 < winter.total_accidents < 4659


def test_latest_data_year_survives_a_table_without_years(tmp_path):
    """MAX(year) is NULL for an empty table: fall back to the calendar year instead of a
    TypeError (a 500) later in the decay maths."""
    import datetime

    import duckdb

    db = tmp_path / "empty.duckdb"
    with duckdb.connect(str(db)) as con:
        con.execute("CREATE TABLE road_accidents (year INTEGER)")
    eng = SpatialRiskEngine(db_path=db)
    try:
        assert eng.latest_data_year() == datetime.date.today().year
    finally:
        eng.close()


def test_close_forgets_the_cached_year(engine):
    engine.latest_data_year()
    engine.close()
    assert engine._latest_year is None


def test_incidents_are_the_highest_weighted_and_labelled_as_such(engine):
    """Known issue #5: the field was called nearest_incidents but held the top 15 by weight."""
    profile = engine.evaluate_point(HELSINKI_2000)
    scores = [i.weighted_score for i in profile.highest_weighted_incidents]
    assert len(scores) == 15
    assert scores == sorted(scores, reverse=True)
    assert not hasattr(profile, "nearest_incidents")
