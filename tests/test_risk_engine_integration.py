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
