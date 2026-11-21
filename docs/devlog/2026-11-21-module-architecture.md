# 2026-11-21 — Module architecture

## Why now

Seen on the projectViewer map, the biggest block was `spatial`, yet it contained no spatial logic: the ingestion pipeline, five one-off scripts and an empty file. `db.py` sat loose in `src/`. The owner asked for folders that are meaningful modules, and for the map to show the app the same way.

## What we did

- **New layout** ([ADR-0006](../decisions/0006-module-architecture.md)): `core`, `ingestion`, `scoring`, `i18n`, `api`, `ui`, with exploration scripts in `scripts/exploration/`. Done with `git mv`, so history follows the files.
- **The one real trap was path roots.** `db.py` computed the repo root as `parents[1]`. Moved one folder deeper, that has to become `parents[2]`, or the app silently looks for the database in `src/`. Fixed, and guarded by 3 new tests (`tests/test_project_layout.py`).
- **A target module map for the warning system:** `spatial`, `context`, `engine`, `llm` arrive with their phases, and are never created empty ([architecture.md](../architecture.md)).
- **We recorded the AI-review strategy** the owner accepted earlier ([ADR-0005](../decisions/0005-ai-code-review-strategy.md)).
- **Commit messages now carry `Changes:` notes** that projectViewer shows on the changed code (rule added to CLAUDE.md).

## Results

All 49 tests pass (46 before + 3 layout guards).

## Noticed, left alone

`src/agent/` and `src/vision/` exist as **empty, untracked folders**, probably the owner's plans. Git ignores empty folders, so they don't affect anything. Left untouched; to discuss.
