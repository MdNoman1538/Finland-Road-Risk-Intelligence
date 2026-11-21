# 2026-11-22: Merging the Phase 0 stack, protecting main, hiding internal errors

## Merging a stack of PRs

PRs #1–#4 were *stacked*: each one's base was the previous branch, not `main`. They were merged in order. After each merge, the next PR's base was switched to `main` (`gh pr edit N --base main`), and it was merged only after its CI was green. All four used **merge commits** rather than squash, so each commit's `Changes:` note survives on `main` for projectViewer to show. The same reasoning is in projectViewer's ADR-0007.

**Why the order matters:** if #1 had been squash-merged, #2's branch would still contain #1's original commits. GitHub would then show them again as "new" in #2, and they could conflict with the squashed copy. Merge commits avoid this, because the original commits stay part of `main`'s history.

PR #1 had no CI run, because the CI workflow itself only arrives in #2.

## Branch protection

`main` now requires a PR, plus the checks **Lint & dependency checks** and **Tests**, with "branch must be up to date" (`strict`) turned on.
- **Required approvals is 0:** GitHub doesn't let the author approve their own PR. Human review is enforced by the process instead (ADR-0004).
- **Why `strict`:** two PRs can each pass CI alone and still break `main` once combined. Requiring the branch to be up to date makes CI run on the combined result.

## Known issue #10: internal errors leaked to clients

**Test first.** A new test points the engine at a database file that doesn't exist, then calls all three risk endpoints. Before the fix, the POST endpoint's 500 response contained the **full filesystem path** of the database, copied from DuckDB's error text through `HTTPException(detail=str(exc))`. The GET and route endpoints had no handler at all.

**Fix.** One app-wide `@app.exception_handler(Exception)`:
- **Server log:** the full traceback, under a random 12-character `error_id`.
- **Client:** only `{"detail": "Internal server error", "error_id": "…"}`.

This is the standard pattern (OWASP, "Improper Error Handling"):
- **The operator** still gets everything needed to debug.
- **The user** gets an id to quote in a bug report.
- **An attacker** learns nothing about paths, SQL or library versions.

Deliberate choices:
- **One handler instead of try/except in each endpoint.** New endpoints are covered automatically, and a forgotten `try` can't reintroduce the leak.
- **`exc_info=exc` passed explicitly** instead of `logger.exception()`. `logger.exception` reads Python's "currently handled exception", and that isn't guaranteed to be set when an async handler runs. A second test checks that the log record really carries the original exception.
- **`HTTPException` (e.g. the 400 for an empty route) is unchanged.** FastAPI handles it before this handler, so deliberate client errors keep their messages.

## Also verified

The projectViewer Claude Code hook now works in real use: edits made in this session appeared live in the viewer's activity feed.

## Known issues #4, #5, #6, #11: engine and API cleanups

**Safety net first.** Before touching the scoring loop, the *complete* output of 5 queries was saved to JSON with key order kept:
- Oulu 250 m and Helsinki 2 km
- winter + Finnish
- cyclist filter in Tampere
- an empty area

After the change, the files were byte-for-byte identical. The characterization tests only pin the score and count. The snapshot also catches changes in labels, counts, tie order and dict order, which matters because the counting code was rewritten.

**Fixes (each test-first):**
- **#4, reference year.** The default is now `None`, meaning "the newest year in the data". A hard-coded `2025` would have frozen time decay when 2026 data arrives, quietly over-weighting old crashes. The value is read once per engine, because the DB is read-only while the app runs.
- **#5, naming.** `nearest_incidents` became `highest_weighted_incidents`. The old name was wrong: the list is sorted by severity × recency × proximity, not by distance. This renames an API field. The dashboard is the only known consumer, so I renamed it rather than keeping a deprecated alias. With outside users, the industry practice would be to keep both for a release and announce the change.
- **#6.** GET point accepts `lang`, typed as `Literal["en","fi"]` so FastAPI rejects other values with 422. `classify_tier` is now public, because a second module uses it. Calling `_private` methods from outside a class couples you to internals that may change.
- **#11, speed.** Only the 15 returned incidents are turned into objects with translations, using `heapq.nlargest`. Its documentation guarantees the same result as `sorted(..., reverse=True)[:15]`, including ties. Counting happens on the Finnish values; each distinct value is translated once, and counts are summed when two spellings share a label.

**Surprise: the #11 diagnosis was wrong.** The status file said the slowness was "in Python, not SQL". That came from reading the code, not from a profile. Measurements (median of 15 runs, Helsinki 2 km, 4,659 rows):

| What | Time |
|---|---|
| `evaluate_point` before | 135 ms |
| `evaluate_point` after | 124 ms |
| the SQL alone | 107 ms |
| SQL with the point passed as fixed bounds (experiment, not applied) | 95 ms |

`EXPLAIN` shows the R-tree index is used, so this isn't a missing index. Returning 4,659 rows and computing their distances simply costs that much. I didn't optimize further: Phases 1–2 replace radius queries with precomputed tiles (ADR-0003), where a lookup is a memory access.

**Lesson:** a performance claim without a profile is a guess. CLAUDE.md already says "measure, don't guess"; this time the guess had slipped in while the status file was being written.

### What the code review caught

`/code-review medium` on this branch reported 8 findings. All were checked, all were real, and all were fixed in a second commit, test-first where they were bugs:

| Finding | Why it matters | Fix |
|---|---|---|
| The response didn't say which reference year was used | A score could change after a data refresh with no visible reason, so it can't be reproduced | `RiskProfile.reference_year` |
| `MAX(year)` is NULL for an empty table | `None - None` raises a TypeError, which becomes a 500; and the cache never fills | Fall back to the calendar year; cache only an int |
| `close()` kept the cached year | Reconnecting to rebuilt data still used the old year | Reset it in `close()` |
| A breaking field rename while the API still said 1.0.0 | Clients get no signal | API version 2.0.0 |
| Route endpoint had no `lang` | Same gap as #6, missed on the second endpoint | `RouteCorridorRequest.lang` |
| Tests pinned 2025 | They would fail on correct code once 2026 data arrives: the very thing #4 removed | Compare against `MAX(year)` |
| **`reference_year=2018` still counted 2019–2025 crashes, at full weight** | "Risk as of 2018" was inflated by the future | SQL now excludes `year > reference_year` |
| Winter values spliced into the SQL text | Safe today, but one quote in a future label breaks every winter query | Passed as a list parameter (`= ANY($n)`) |

The future-crash bug existed before this branch (`max(0, age)` quietly turned negative ages into "brand new"). Making `reference_year` easier to see made it worth fixing now.

**Lesson:** the reviewer saw *consequences across time* (data refreshes, a future 2026 load), which the snapshot test can't, because it only compares today's data.

## Known issue #8: the database moves out of git ([ADR-0007](../decisions/0007-database-as-versioned-release-asset.md))

The owner chose option A, a GitHub Release asset. What was built:
- **`data/road_risk.lock.json`** pins tag, URL, SHA-256 and size. It's the data equivalent of `uv.lock`: the code names the exact bytes it expects.
- **`src/core/dataset.py`** (standard library only, so it runs before anything else is installed):
  - `fetch` downloads to a `.part` file, verifies the checksum, then renames it into place. A crash or a bad download can therefore never leave a half-written DB where the app would open it.
  - It skips the download if the local file already matches.
  - It **refuses to overwrite a different local DB**, such as a fresh re-ingest, unless given `--force`.
  - `lock <tag>` pins a rebuilt DB and prints the `gh release create` command.
- **`src/core/paths.py`:** the project paths now live in one file, because both `db.py` and the downloader need them.
- **Render** runs `python -m src.core.dataset` after `pip install`. **CI** caches the DB under `hashFiles(lock file)`, so a new data version invalidates the cache automatically.
- **Tests** use `file://` URLs, so they run without network.
  - Unit tests: download, corrupted download, already up to date, and refusing to overwrite.
  - Integration test: the local DB matches the lock. If someone rebuilds the DB and forgets to publish it, this test says so.
  - A test that git doesn't track `data/processed/`.

**Why not rewrite history to remove the old 38 MB?** It would need a force-push to a public repository. Every existing clone would then diverge, and every fork would keep the file anyway. That's destructive, for a small gain.

**Order matters when shipping this:** the Release must exist *before* the PR's CI runs, or the fetch step fails with 404.
