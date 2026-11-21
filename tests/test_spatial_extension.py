"""Regression tests: the engine must work on a machine where the DuckDB spatial
extension has never been installed (fresh Render/CI server, or after a DuckDB upgrade,
since extensions are stored per DuckDB version).

See known issue #1 in docs/project-status.md.
"""

import shutil

import pytest

from src.core.db import DB_PATH
from src.scoring import RiskQuery, SpatialRiskEngine

OULU = RiskQuery(lat=65.0121, lon=25.4651, radius_m=250)


@pytest.mark.integration
def test_engine_works_with_an_empty_extension_directory(tmp_path):
    # Use a private copy of the DB: within one process DuckDB shares a database instance
    # per file and refuses a second connection with a different config (here: another
    # extension_directory) while other tests hold one open. A copy keeps this test
    # independent of test order.
    db_copy = tmp_path / "road_risk.duckdb"
    shutil.copy(DB_PATH, db_copy)
    engine = SpatialRiskEngine(db_path=db_copy, extension_directory=tmp_path / "duckdb_extensions")

    try:
        profile = engine.evaluate_point(OULU)
    finally:
        engine.close()

    assert profile.total_accidents > 0
