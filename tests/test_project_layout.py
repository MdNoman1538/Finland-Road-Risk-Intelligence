"""Guards for the module layout (ADR-0006): paths computed from __file__ must still point at the
repository after files move. A wrong `parents[n]` silently points at the wrong folder."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_database_path_points_at_the_repository():
    from src.core.db import DB_PATH, PROJECT_ROOT

    assert PROJECT_ROOT == REPO
    assert DB_PATH == REPO / "data" / "processed" / "road_risk.duckdb"


def test_ingestion_paths_point_at_the_repository():
    from src.ingestion import ingest_all

    assert ingest_all.PROJECT_ROOT == REPO
    assert ingest_all.RAW_DATA_DIR == REPO / "data" / "raw"
    assert ingest_all.DB_PATH == REPO / "data" / "processed" / "road_risk.duckdb"


def test_exploration_scripts_point_at_the_repository():
    import ast

    for script in (REPO / "scripts" / "exploration").glob("*.py"):
        tree = ast.parse(script.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript) and ast.unparse(node).endswith(".parents[2]"):
                # scripts/exploration/x.py -> parents[2] is the repository root
                assert script.resolve().parents[2] == REPO, script.name
