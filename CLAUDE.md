# CLAUDE.md

Instructions for AI coding agents working in this repository. Humans: see [CONTRIBUTING.md](CONTRIBUTING.md).

## Project

**Finland Road Risk Intelligence.** It is evolving from a crash-data analytics dashboard into an **in-car, offline-first, context-aware road-risk alert system**. Read these before non-trivial work:
- [docs/roadmap.md](docs/roadmap.md): goal, architecture, phases
- [docs/project-status.md](docs/project-status.md): what exists now, known issues
- [docs/decisions/](docs/decisions/): accepted architecture decisions (do not contradict them silently)

The owner is learning AI engineering through this project. **Explain the why, what, how and where** of new concepts, tools and decisions, not only the code.

## Non-negotiable design rules

1. **The LLM never makes the safety decision.** Risk scoring and alert triggering are deterministic or calibrated statistical/ML code. LLMs only explain, extract, converse and phrase. ([ADR-0001](docs/decisions/0001-llm-is-not-the-risk-decision-maker.md))
2. **Only use features with a live counterpart in the car.** No feature may be used in training if the car cannot know it while driving.
3. **Lighting comes from sun position, not clock time.** The open data has no time of day. ([ADR-0002](docs/decisions/0002-lighting-from-sun-position-instead-of-clock-time.md))
4. **DuckDB is the offline data factory.** The in-car runtime uses precomputed in-memory risk tiles, not live DB queries. ([ADR-0003](docs/decisions/0003-duckdb-as-data-factory-precomputed-tiles-in-car.md))
5. **Risk means crashes relative to exposure** (traffic volume), never raw counts alone.

## Workflow rules for agents

- Follow [CONTRIBUTING.md](CONTRIBUTING.md): GitHub Flow, Conventional Commits, one purpose per PR, the Definition of Done.
- **Never commit directly to `main`.** Create a branch named `<type>/<short-description>`.
- **Bug fixes are test-first:** write the failing test, show it fails, then fix.
- **Measure, don't guess:** any performance or data claim must come from a measurement you ran; record how.
- Ask the owner before pushing, opening or merging PRs, changing GitHub settings, or any other outward-facing action.
- Never commit secrets, `.env` files, raw data (`data/raw/` is git-ignored) or personal data.

## Documentation duty (every session)

- Add or extend a devlog entry: `docs/devlog/YYYY-MM-DD-topic.md`. Record the reasoning, the surprises and the dead ends.
- Write an ADR (`docs/decisions/NNNN-title.md`, from `template.md`) for any significant or hard-to-reverse decision. Never rewrite an accepted ADR; supersede it with a new one.
- Update `docs/project-status.md` when status, known issues or measurements change.

## Codebase map

| Path | Purpose |
|---|---|
| `src/spatial/ingest_all.py` | Raw Väylävirasto CSVs → `data/processed/road_risk.duckdb` (two schema eras: 2014–21 and 2022+) |
| `src/scoring/risk_engine.py` | `SpatialRiskEngine`: radius-based risk scoring (to be replaced in Phases 1–2) |
| `src/api/main.py` | FastAPI service |
| `src/ui/app.py` | Streamlit + Folium dashboard (dev/demo tool, not the in-car interface) |
| `src/i18n/translator.py` | Finnish → English labels; Finnish values are the canonical keys in the DB |

## Data facts to remember

- Coordinates are stored in EPSG:3067 (ETRS-TM35FIN, metres) as `geom_3067`, plus WGS84 `lat`/`lon`. Do distance math in 3067.
- Category values are Finnish (for example `Kuolemaan johtanut`, `päivänvalo`). Translate only at the output layer.
- "Missing" currently appears as `Ei arvoa`, `-` or `Unknown` (cleanup planned in Phase 0).
- Yearly counts are not comparable over time: recording rules changed. "Severe injury" exists only from 2022.

## Commands

Environment: conda env `ailearn` (Python 3.12). Being migrated to `uv` in Phase 0; this section will be updated.

```bash
uvicorn src.api.main:app --reload                      # API on :8000
PYTHONPATH=. python -m streamlit run src/ui/app.py      # dashboard on :8501
python src/spatial/ingest_all.py                         # rebuild DB (needs data/raw/)
```
