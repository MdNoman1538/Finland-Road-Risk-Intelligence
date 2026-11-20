"""Regression tests: the engine must work on a machine where the DuckDB spatial
extension has never been installed (fresh Render/CI server, or after a DuckDB upgrade,
since extensions are stored per DuckDB version).

See known issue #1 in docs/project-status.md.
"""

import pytest

from src.scoring import RiskQuery, SpatialRiskEngine

OULU = RiskQuery(lat=65.0121, lon=25.4651, radius_m=250)


@pytest.mark.integration
def test_engine_works_with_an_empty_extension_directory(tmp_path):
    engine = SpatialRiskEngine(extension_directory=tmp_path / "duckdb_extensions")

    profile = engine.evaluate_point(OULU)

    assert profile.total_accidents > 0
