# Finland Spatial Road Risk Intelligence System (2014–2025)

A spatial, bilingual (EN / FI) road safety analytics platform built on official open crash data from Väylävirasto (Finnish Transport Infrastructure Agency). Unifies 180,734 geocoded accidents and 309,834 participant records (2014–2025) in an embedded DuckDB R-Tree spatial warehouse, exposed via a FastAPI REST service and an interactive Streamlit + Folium map dashboard.

## Data Source

- Provider: Väylävirasto (Finnish Transport Infrastructure Agency) — Aineistonvälitysalusta (AVA)
- Dataset Portal: https://aineistot.vayla.fi/spa/ava/Tie/Tieliikenneonnettomuudet/
- Coverage: 2014–2025 (including 2025 preliminary records)
- Data License: Creative Commons Attribution 4.0 International (CC BY 4.0)

## Features

- Multi-Schema Spatial Ingestion (src/spatial/ingest_all.py): Harmonizes legacy (2014–2021) and modern (2022–2025) Väylävirasto schemas across UTF-8, ISO-8859-1, and UTF-16 LE encodings, projecting ETRS-TM35FIN (EPSG:3067) metric geometries alongside WGS84 (EPSG:4326) coordinates with an R-Tree spatial index.
- Deterministic Spatial Risk Engine (src/scoring/risk_engine.py): Evaluates radial buffers using severity weights, 5-year half-life exponential temporal decay, linear distance attenuation, and area-normalized 0–100 risk calibration.
- Bilingual Taxonomy Layer (src/i18n/translator.py): Preserves canonical Finnish keys in DuckDB while translating severities, road surfaces, lighting, participant types, and all 80+ Väylävirasto collision mechanisms into English.
- FastAPI Backend (src/api/main.py): Provides /health, /api/v1/risk/point, and /api/v1/risk/route endpoints.
- Interactive Map Explorer (src/ui/app.py): Supports cascading Finnish Region (Maakunta) and Municipality (Kunta) filtering, top-10 250m grid hotspot auto-jump, winter/road-user filters, and click-anywhere map evaluation.

## Quick Start

1. Activate environment and install dependencies:
   conda activate ailearn
   pip install -r requirements.txt

2. Rebuild the DuckDB spatial warehouse (optional — pre-built data/processed/road_risk.duckdb is included):
   Download the 2014–2025 CSV datasets from https://aineistot.vayla.fi/spa/ava/Tie/Tieliikenneonnettomuudet/, place them in data/raw/, and run:
   python src/spatial/ingest_all.py

3. Start the FastAPI backend:
   uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

4. Start the Streamlit map explorer (in a second terminal):
   PYTHONPATH=. python -m streamlit run src/ui/app.py

## License

- Source Code: Licensed under CC BY-NC 4.0 (Non-Commercial use only — see LICENSE).
- Underlying Dataset: Väylävirasto open data licensed under CC BY 4.0.
