# Sahara GIS — developer guide (for Claude & humans)

SAS.Planet-style offline mapping + a Python GIS studio, focused on Algeria
(Nord Sahara 1959 datum, 1:25,000 sheet grids, surveying/field tools).

## Stack
- **UI**: React + TypeScript + Vite + Tailwind + Leaflet — in `src/`.
- **Server**: Node/Express tile-cache + API — `server.ts` and `server/*.ts`.
  Serves the built UI and proxies/caches map tiles; spawns Python for GIS ops.
- **GIS engine**: Python package `sas_planet_py/` (numpy, shapely, pyproj,
  rasterio, Pillow). Pure modules, called by the server via stdin/stdout JSON
  (`python -m sas_planet_py.studio <operation>`), plus `-m sas_planet_py.cli`.

## Commands
```bash
npm install                     # install JS deps (first run)
pip install -r requirements-gis.txt   # Python deps for the GIS engine
npm run dev                     # dev server (tsx server.ts) + Vite middleware
npm run build                   # build the UI to dist/
npm run lint                    # tsc --noEmit (type check)
python tests/test_vector_import.py    # run a Python test file directly
```
- Server env: `PORT` (default 3000), `HOST` (default 127.0.0.1),
  `SAS_PYTHON` (path to a Python; otherwise a bundled runtime or `python`/`python3`).
- There is **no `tests/__init__.py`** — run each test file directly
  (`python tests/<file>.py`), not `python -m unittest tests...`.

## How the API runs Python
- `server.ts` exposes `/api/...` routes. GIS operations POST to
  `/api/studio/:operation`, dispatched in `sas_planet_py/studio.py` →
  the matching module. A new op needs: the function, a branch in
  `studio.py`'s `dispatch`, and the op name added to the `studioOperations`
  Set in `server.ts`.
- Vector import/export: `/api/python/vector/*` → `sas_planet_py/vector_formats.py`.

## Key modules (`sas_planet_py/`)
- `projections.py`, `nord_sahara.py` — Web Mercator / UTM / Nord Sahara 1959 (Clarke 1880).
- `map_sheets.py`, `sheet_catalog.py` — Algeria 1:25,000 grid + imported sheet catalogs.
- `vector_formats.py` — KML/KMZ/GPX/GeoJSON/Shapefile + SAS.Planet `.sml`/`.db3`
  import; GeoJSON/GPX/KML/**DXF** export.
- `tile_downloader.py`, `tile_stitcher.py`, `tile_storage.py` — tiles & stitching.
- `terrain*.py`, `scene3d.py`, `studio_analysis.py` — DEM, slope/aspect/hillshade,
  watershed, viewshed, **cut/fill volume**, **RGB vegetation index (VARI/GLI)**.
- `studio.py` — the JSON dispatcher used by the server.

## Recent features (2026-11)
SAS.Planet `.sml`/`.db3` marks import (keeps only id/nom/type/n_50000/coup/num),
attribute table + CSV in the Marks manager, DXF / DXF-NS export, custom map
sources (XYZ/TMS/WMS) in Settings, swipe compare on the map, cut/fill volume
and the VARI/GLI vegetation index in the Advanced GIS tools.

## Deploying to the portable app (local only)
The portable release keeps three trees: **`sources/`** (this repo, the only
buildable one), **`app/`** (the runtime that actually runs — embedded Python
loads `app/sas_planet_py`, the server is the compiled `app/server.mjs`, the UI
is `app/dist`), and **`source/`** (a shipped mirror). After editing here:
1. `npm run build`, then copy `dist/` → `app/dist`.
2. Rebuild `app/server.mjs` with esbuild (same options as
   `scripts/build-portable.mjs`) when `server.ts`/`server/*` change.
3. Copy changed `sas_planet_py/*.py` → `app/sas_planet_py/` (and `source/` mirror).

A cloud session has only `sources/` — build and open a PR here; pull, build and
deploy to `app/` on the local machine.
