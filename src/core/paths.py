"""Project paths, in one place. Standard library only (used by build-time tools too)."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # src/core/paths.py -> repository root
DB_PATH = PROJECT_ROOT / "data" / "processed" / "road_risk.duckdb"
LOCK_PATH = PROJECT_ROOT / "data" / "road_risk.lock.json"
