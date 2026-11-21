"""The crash database as a versioned, checksum-verified release asset (known issue #8).

Why: a 38 MB binary in git grows the repository by its full size on every rebuild,
forever. Instead each data version is uploaded to a GitHub Release, and
`data/road_risk.lock.json` pins the exact file (URL + SHA-256), the way `uv.lock` pins
packages. Render and CI run `python -m src.core.dataset` at build time.

    python -m src.core.dataset              # fetch the pinned DB (no-op if already correct)
    python -m src.core.dataset --force      # replace a local DB that differs
    python -m src.core.dataset lock <tag>   # after re-ingesting: pin the local DB as <tag>

Standard library only, so it runs before (or without) the app's dependencies.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

from src.core.paths import DB_PATH, LOCK_PATH, PROJECT_ROOT

REPO_URL = "https://github.com/MdNoman1538/Finland-Road-Risk-Intelligence"


class ChecksumError(RuntimeError):
    """The downloaded file is not the one the lock file pins."""


class LocalDatabaseDiffers(RuntimeError):
    """A different database already exists locally (e.g. a fresh re-ingest)."""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(lock_path: Path = LOCK_PATH, target: Path = DB_PATH, *, force: bool = False) -> str:
    """Make `target` the pinned database. Returns "up-to-date" or "downloaded"."""
    lock = json.loads(lock_path.read_text())
    if target.exists():
        if sha256_of(target) == lock["sha256"]:
            return "up-to-date"
        if not force:
            raise LocalDatabaseDiffers(
                f"{target} differs from release {lock['tag']}. Keep it, publish it "
                "(`lock <tag>`), or replace it with --force."
            )

    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    try:
        # Download to a side file, verify, then rename: a crash or a bad download can
        # never leave a half-written database where the app would open it.
        with urllib.request.urlopen(lock["url"], timeout=60) as response, part.open("wb") as out:
            for chunk in iter(lambda: response.read(1 << 20), b""):
                digest.update(chunk)
                out.write(chunk)
        if digest.hexdigest() != lock["sha256"]:
            raise ChecksumError(f"SHA-256 mismatch for {lock['url']}: got {digest.hexdigest()}")
        os.replace(part, target)  # atomic on the same filesystem
    finally:
        part.unlink(missing_ok=True)
    return "downloaded"


def write_lock(tag: str, db: Path = DB_PATH, lock_path: Path = LOCK_PATH) -> dict:
    """Pin the local database as release `tag` (upload it to that release separately)."""
    lock = {
        "tag": tag,
        "url": f"{REPO_URL}/releases/download/{tag}/{db.name}",
        "sha256": sha256_of(db),
        "bytes": db.stat().st_size,
    }
    lock_path.write_text(json.dumps(lock, indent=2) + "\n")
    return lock


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m src.core.dataset")
    sub = ap.add_subparsers(dest="cmd")
    ap.add_argument("--force", action="store_true", help="replace a local database that differs")
    lock_cmd = sub.add_parser("lock", help="pin the local database as a new release tag")
    lock_cmd.add_argument("tag")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "lock":
            lock = write_lock(args.tag)
            print(f"Pinned {lock['sha256'][:12]}… as {lock['tag']}. Now upload it:")
            print(
                f"  gh release create {lock['tag']} {DB_PATH.relative_to(PROJECT_ROOT)} --title {lock['tag']}"
            )
            return 0
        print(f"{fetch(force=args.force)}: {DB_PATH.relative_to(PROJECT_ROOT)}")
        return 0
    except (ChecksumError, LocalDatabaseDiffers, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
