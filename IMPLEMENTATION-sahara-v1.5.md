# Sahara GIS desktop portability fixes (same v1.5)

- [x] Self-contained native desktop window with bundled Electron 45.2.1
- [x] Sahara GIS — صحارى GIS branding and original icon
- [x] Bounded single-line footer and viewport sizing
- [x] Portable cache discovery, native folder opening/selection and copy for transfer
- [x] Relocated Arabic/spaced-path launch with isolated PATH and 63 synthetic offline tiles
- [x] Native Explorer open, cache copy and desktop/server shutdown verified
- [x] Existing v1.5 release updated without writing settings, cache or projects

Native proof: build/sahara-desktop-review/proofs/native-window.jpg
Cache transfer proof: build/sahara-desktop-review/cache-copy-report.json
Archive integration verification: tests/smoke_portable.py (report under build/portable-smoke).

## Offline terrain follow-up

- Reuse complete finer as well as coarser Terrarium cache levels after mesh detail changes.
- Added explicit region elevation preparation with an offline verification pass, and direct SRTM HGT import in the 3D viewer.
- Clarified that cache_gmt imagery is independent from app/cache/terrain elevations. Missing DEM samples remain holes.
- Base map tiles now use native image elements with a one-pixel overlap and normal compositing. Faint seams remain in the IAB preview; no claim of complete seam elimination.
- Validation: TypeScript/build, 15 topography tests, 4 scene tests, and isolated HTTP terrain preparation/scene/SRTM/invalid-input checks.
- Integration report: build/offline-terrain-review/report.json (synthetic fixtures only).
