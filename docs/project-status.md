# Project Status

**As of:** 2026-11-22 · Module structure: see [architecture.md](architecture.md). · **Current phase:** [Phase 0](roadmap.md#phase-0--engineering-foundations), in progress. PRs #1–#4 (workflow/docs, tooling/CI, spatial-extension fix, module refactor) are merged; `main` is protected and requires the checks *Lint & dependency checks* and *Tests*. 65 tests passing. API version 2.0.0 (renamed field, see issue #5).

## Summary

We have a working **analytics prototype**: 12 years of Finnish crash data (2014–2025) in a spatial DuckDB database, a risk-scoring engine, a REST API, and a bilingual (Finnish/English) map dashboard.

The goal is an **in-car, real-time, context-aware alert system**. Measured against that goal:

- **The data foundation and the choice of DuckDB are right.** Keep them.
- **The way risk is calculated must change.** It counts crashes in a circle; it needs to estimate risk per road segment, normalised by traffic and conditioned on current lighting, surface and weather.
- **The in-car runtime does not exist yet.** It is a different kind of program from the dashboard (see [ADR-0003](decisions/0003-duckdb-as-data-factory-precomputed-tiles-in-car.md)).

## 1. What exists today

| Component | File | What it does | Verdict vs goal | Changes in |
|---|---|---|---|---|
| Data ingestion | [src/ingestion/ingest_all.py](../src/ingestion/ingest_all.py) | Merges the 2014–21 and 2022+ file formats, handles 3 text encodings, converts coordinates EPSG:3067 → WGS84, builds the R-tree spatial index. | **Keep.** Solid base. Needs more columns and data checks. | Phase 1 |
| Risk engine | [src/scoring/risk_engine.py](../src/scoring/risk_engine.py) | Crashes within a radius, weighted by severity (10/5/3/1) × 5-year half-life decay × distance. Adjusted for search area and squashed to 0–100. | **Replace the method, keep the interface idea.** Counts are not risk (no traffic exposure), circles are not roads, and there is no "right now" conditioning. | Phases 1, 2, 4 |
| REST API | [src/api/main.py](../src/api/main.py) | `/health`, point risk (GET/POST), route risk. | **Keep FastAPI.** Endpoints will change as the engine changes. | Phases 0, 3 |
| Dashboard | [src/ui/app.py](../src/ui/app.py) | Region and municipality dropdowns, top-10 hotspots on a 250 m grid, click-to-evaluate map, winter and road-user filters. | **Keep as a dev / analysis / demo tool.** It is not the in-car interface. | Phases 2, 5 (drive-replay simulator) |
| Translations | [src/i18n/translator.py](../src/i18n/translator.py) | Finnish → English labels for severity, surface, lighting, vehicle and ~75 crash types. | **Keep.** Later also feeds the LLM's Finnish/English output. | — |
| Helper scripts | `scripts/exploration/` | One-off exploration scripts, moved out of `src/` ([ADR-0006](decisions/0006-module-architecture.md)); empty `init_db.py` deleted. | Keep as scripts; turn the useful checks into data-quality tests in Phase 1. | Phase 1 |
| Deployment | [render.yaml](../render.yaml) | Two free Render services (dashboard + API). | Fine for a portfolio demo. Not the product deployment. | Phase 0 |

## 2. Data inventory (verified)

| Table | Rows | Notes |
|---|---|---|
| `road_accidents` | 180,734 | 2014–2025 (2025 is preliminary). 173 rows were skipped at ingestion. **All of them had no coordinates** (checked per year against the raw CSVs), so no data was lost to parse errors. |
| `accident_participants` | 309,834 | Vehicle or road-user type, vehicle age and mass. |

**Data facts that shape the design:**

1. **No time of day.** No year has an hour field. `Luovpvm` (2014–21) is the *road record's* creation date (values such as 1965), not the crash time. We use the `Valoisuus` (lighting) field plus sun position instead → [ADR-0002](decisions/0002-lighting-from-sun-position-instead-of-clock-time.md).
2. **The recording rules changed between years.** Yearly counts fall from 28,327 (2014) to 8,610 (2025), and the "severe injury" category only exists from 2022 onward (260 rows). Roads did not get 3× safer. Raw trends and the time decay must be corrected.
3. **No traffic exposure is used yet.** The 2014–21 files contain `Kvl` (average daily traffic), which is not ingested.
4. **Useful columns that are not ingested yet:** weekday, temperature, urban/rural, winter maintenance class, sight distance (`Nakos150/300/460`), road width, roadworks, pavement, road address (`Tie/Aosa/Aet`).
5. **"Missing" is written several ways:** `Ei arvoa`, `-`, `Unknown`. There is also 1 duplicate `accident_id`.
6. **The data is sparse.** Most locations have 0–2 crashes in 12 years, so statistical shrinkage (Empirical Bayes) is needed.

## 3. Performance baseline

Measured 2026-11-21 on an Apple M3 with 16 GB, DuckDB 2.0.0, on a scratch copy of the DB. Median of 25 lookups at 5 Finnish city points.

| Approach | Latency per point |
|---|---|
| Current `evaluate_point`, 250 m radius | 78 ms (max 118 ms) |
| Current `evaluate_point`, 2 km radius | 124 ms (max 239 ms) |
| …of which: open a connection + `LOAD spatial` on every call | ~56 ms |
| Same SQL with one persistent connection | 12.5 ms |
| In-memory numpy scan of all 180k points (2.9 MB) | 0.3 ms |
| In-memory KD-tree lookup | 0.004 ms |

**After the spatial-extension fix** (persistent connection + cursor per call; same machine and method, DuckDB 2.0.1):

| Approach | Latency |
|---|---|
| `evaluate_point`, 250 m | **15.3 ms** (max 26 ms), was 78 ms |
| `evaluate_point`, 2 km | **79.8 ms** (max 136 ms), was 124 ms; the remaining cost is Python-side (known issue #11) |
| 100-waypoint route, 150 m radius | **1.16 s** measured; before: ~8 s *estimated* (100 × 78 ms), not measured |

**How to read this:**
- The R-tree index *is* used. The main cost is reconnecting to the database on every request.
- A 100-waypoint route currently takes about 8 s.
- **Quick win (Phase 0):** reuse one connection, for about 6× faster.
- **Real fix (Phases 1, 2, 8):** precompute risk per road segment. The car then does an in-memory lookup that takes microseconds. Speed comes from the architecture, not from tuning the query → [ADR-0003](decisions/0003-duckdb-as-data-factory-precomputed-tiles-in-car.md).

## 4. Known issues

| # | Issue | Evidence | Severity | Fix in |
|---|---|---|---|---|
| 1 | ✅ **Fixed in the spatial-extension PR** (`src/db.py` installs before loading; regression test `tests/test_spatial_extension.py`). Original issue: **the API fails on a fresh server.** The engine only runs `LOAD spatial`. The last commit (7a0dd11) added `INSTALL` only to the dashboard's hotspot function. | Bare `LOAD spatial` against an empty extension directory → `IO Error: Extension ... not found`. `/health` still passes because it never touches the DB, so Render shows the service as healthy while `/api/v1/risk/*` errors. Also reproduced locally after a DuckDB 2.0.0 → 2.0.1 upgrade, because extensions are stored per version. | High (deployed demo is broken) | Phase 0, first task |
| 2 | ✅ **Fixed** (the dashboard now uses the engine's shared connection; smoke test `tests/test_dashboard.py`). Original issue: the dashboard works on Render only by luck of ordering. The hotspot function happens to install the extension before the engine runs. | Code order in `app.py`. | Medium | Phase 0 |
| 3 | ✅ **Fixed:** one persistent connection, one cursor per request (thread-safe; tested with 8 threads). 250 m lookup 78 → 15 ms. | Benchmark above. | Medium | Phase 0 |
| 4 | ✅ **Fixed:** `reference_year` defaults to `None` = the newest year in the data (`SpatialRiskEngine.latest_data_year()`, read once per engine). Original issue: hard-coded to 2025, so time decay would stop ageing old crashes once 2026 data arrives. | `RiskQuery` default. | Low | Phase 0 |
| 5 | ✅ **Fixed:** renamed to `highest_weighted_incidents` (an API field rename; the dashboard is the only known consumer and is updated). Original issue: `nearest_incidents` actually held the 15 highest-*weighted* incidents, not the nearest. | `risk_engine.py`. | Low (naming) | Phase 0 |
| 6 | ✅ **Fixed:** GET point takes `lang=en\|fi` (422 otherwise); `classify_tier` is public. Original issue: GET had no `lang`, and the route endpoint called the private `_classify_tier`. | `api/main.py`. | Low | Phase 0 |
| 7 | ✅ ~~No tests, no CI, no lint.~~ Addressed by the tooling/CI PR (uv, ruff, pytest, pre-commit, GitHub Actions). The fix PR adds integration tests: characterization tests, concurrency, health check, dashboard smoke test. 46 tests total. | Repo, git history. | High (for an industry goal) | Phase 0 ([ADR-0004](decisions/0004-development-workflow.md)) |
| 8 | The 38 MB `.duckdb` file is committed to git. | `git ls-files`. | Medium | Phase 0 |
| 9 | The code license is CC BY-NC (non-commercial), which blocks industry use. | `LICENSE`. | Decision needed before approaching industry | Phase 10 |
| 10 | ✅ **Fixed:** one app-wide handler logs the full error under a 12-character id and returns only `{"detail": "Internal server error", "error_id": …}` (tests `test_internal_errors_do_not_leak_details`, `test_internal_error_details_go_to_the_server_log`). Original issue: `POST /api/v1/risk/point` returned the raw exception text in its 500 response, including the full database path. | Reproduced: the response contained `…/missing.duckdb" in read-only mode: database does not exist`. | Medium (security hygiene) | Phase 0 |
| 11 | **Diagnosis corrected (2026-11-22).** Large radii are slow because of the **SQL query**, not Python. Measured at Helsinki 2 km (4,659 crashes, median of 15): whole call 135 ms; SQL alone 107 ms (R-tree index *is* used). Building only the 15 returned objects instead of all 4,659 saved ~11 ms (→ 124 ms). Passing the point as fixed bounds instead of a join saved another ~12 ms in an experiment; not applied. Original claim ("Python, not SQL") was wrong: it came from code inspection, not a profile. | cProfile + SQL timing, see devlog 2026-11-22. | Low: the radius engine is replaced by precomputed tiles in Phases 1–2 (ADR-0003) | Phase 2 |

## 5. Gap analysis: what the goal needs vs what we have

| Capability needed for the in-car product | Have it? | Phase |
|---|---|---|
| Clean, unified historical crash data | ✅ Mostly | 1 (enrich) |
| Spatial lookup | ✅ (radius) | 1 (road-segment based) |
| Road network + map-matching (which road and direction the car is on) | ❌ | 1, 5 |
| Traffic exposure (traffic volume) | ❌ | 1 |
| Statistically sound risk per segment (Empirical Bayes) | ❌ | 2 |
| Risk under conditions (dark / icy / winter, relative to exposure) | ❌ | 2, 4 |
| Live context: sun position, road weather, forecasts, traffic messages | ❌ (sun position demonstrated) | 3 |
| Calibrated ML model, ONNX export | ❌ | 4 |
| GPS pipeline, look-ahead along the road, alert logic | ❌ | 5 |
| Small LLM for explanations, Q&A, traffic-message extraction | ❌ (Qwen3.5 4B/9B MLX downloaded, not served) | 6 |
| LoRA fine-tuned small model | ❌ | 7 |
| On-device runtime, offline, over-the-air updates | ❌ | 8 |
| Automated retraining / knowledge updates | ❌ | 9 |
| Tests, CI, safety/privacy documentation | ❌ | 0, 10 |

## 6. Keep / change / add

- **Keep:** DuckDB + spatial as the offline "data factory", FastAPI, Pydantic models, Streamlit as an internal tool, the ingestion work, translations.
- **Change now (Phase 0):** connection handling, the extension install bug, hard-coded values, project tooling.
- **Change soon (Phases 1–2):** radius search → road segments; count-based score → exposure-normalised, condition-aware risk.
- **Add (Phases 3–10):** live data, ML model, alert engine, LLM layer, edge runtime, MLOps.

## Next steps

Start **Phase 0**: fix issue #1 together with a regression test (a test that would have caught it), then set up project tooling (pyproject + uv, ruff, pytest, CI).
