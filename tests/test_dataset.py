"""The database is a versioned release asset, fetched and checksum-verified (known issue #8)."""

import hashlib
import json
import subprocess

import pytest

from src.core import dataset
from src.core.db import DB_PATH, PROJECT_ROOT


def _lock_for(source, tmp_path, *, sha256=None):
    data = source.read_bytes()
    lock = {
        "tag": "data-test",
        "url": source.as_uri(),  # file:// so the test needs no network
        "sha256": sha256 or hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }
    path = tmp_path / "lock.json"
    path.write_text(json.dumps(lock))
    return path


@pytest.fixture
def source(tmp_path):
    src = tmp_path / "published.duckdb"
    src.write_bytes(b"pretend database " * 1000)
    return src


def test_fetch_downloads_and_verifies(source, tmp_path):
    target = tmp_path / "out" / "road_risk.duckdb"
    assert dataset.fetch(_lock_for(source, tmp_path), target) == "downloaded"
    assert target.read_bytes() == source.read_bytes()


def test_fetch_rejects_a_corrupted_download_and_leaves_nothing(source, tmp_path):
    target = tmp_path / "road_risk.duckdb"
    with pytest.raises(dataset.ChecksumError):
        dataset.fetch(_lock_for(source, tmp_path, sha256="0" * 64), target)
    assert not target.exists()
    assert not list(tmp_path.glob("*.part"))


def test_fetch_skips_when_the_file_already_matches(source, tmp_path):
    target = tmp_path / "road_risk.duckdb"
    target.write_bytes(source.read_bytes())
    assert dataset.fetch(_lock_for(source, tmp_path), target) == "up-to-date"


def test_fetch_never_overwrites_a_different_local_database(source, tmp_path):
    """A developer's freshly re-ingested DB differs from the release; replacing it
    silently would lose work. Only --force replaces it."""
    target = tmp_path / "road_risk.duckdb"
    target.write_bytes(b"my local rebuild")
    lock = _lock_for(source, tmp_path)
    with pytest.raises(dataset.LocalDatabaseDiffers):
        dataset.fetch(lock, target)
    assert target.read_bytes() == b"my local rebuild"
    assert dataset.fetch(lock, target, force=True) == "downloaded"


def test_lock_file_describes_a_release_asset():
    lock = json.loads(dataset.LOCK_PATH.read_text())
    assert lock["url"].startswith("https://github.com/")
    assert f"/releases/download/{lock['tag']}/" in lock["url"]
    assert len(lock["sha256"]) == 64


@pytest.mark.integration
def test_local_database_matches_the_lock_file():
    """If this fails, the DB was rebuilt: publish a new release and update the lock file
    (python -m src.core.dataset lock <tag>), or fetch the pinned one."""
    lock = json.loads(dataset.LOCK_PATH.read_text())
    assert dataset.sha256_of(DB_PATH) == lock["sha256"]


def test_database_file_is_not_tracked_by_git():
    tracked = subprocess.run(
        ["git", "ls-files", "data/processed"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True
    ).stdout
    assert tracked == ""


def test_fetch_reports_a_truncated_download_as_such(source, tmp_path):
    lock_path = _lock_for(source, tmp_path)
    lock = json.loads(lock_path.read_text())
    lock["bytes"] += 10  # the server sent fewer bytes than the release holds
    lock_path.write_text(json.dumps(lock))
    with pytest.raises(dataset.ChecksumError, match="incomplete"):
        dataset.fetch(lock_path, tmp_path / "road_risk.duckdb")
