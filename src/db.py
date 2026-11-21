"""Single place where the application opens DuckDB connections.

Why this module exists: DuckDB extensions are stored per DuckDB version
(~/.duckdb/extensions/vX.Y.Z/...). A bare `LOAD spatial` therefore fails on a fresh
server and after every DuckDB upgrade. Every connection must INSTALL before LOAD.
"""

from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "processed" / "road_risk.duckdb"


def connect_spatial(
    db_path: Path = DB_PATH,
    *,
    read_only: bool = True,
    extension_directory: Path | None = None,
) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection with the spatial extension installed and loaded.

    `install_extension` is a no-op when the extension is already present for this
    DuckDB version; otherwise it downloads it once. If that is impossible (offline
    and not installed), this raises instead of failing later on the first spatial query.
    """
    config: dict[str, str] = {}
    if extension_directory is not None:
        config["extension_directory"] = str(extension_directory)

    con = duckdb.connect(str(db_path), read_only=read_only, config=config)
    try:
        con.install_extension("spatial")
        con.load_extension("spatial")
    except Exception:
        con.close()
        raise
    return con
