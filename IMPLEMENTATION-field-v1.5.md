# Field GIS additions to existing v1.5

Authorized: all proposed OkMap-inspired features, UTM grid and batch coordinate conversion. Preserve portable user data; update same version.

- [x] Local georeferenced raster layers; ordered persistent layer manager
- [x] GPX metadata/segments, editing, statistics and linked profile
- [x] Real NMEA serial reception with quality and recording
- [x] Configurable WMS/WMTS layers
- [x] Offline field packages and Garmin KMZ
- [x] Geotagged field photos
- [x] Road/path routing and polygon coverage planning
- [x] Metric UTM grid and batch CSV coordinates
- [x] Numerical, UI and portable update verification

Validation in progress: 17 new Python field tests, 4 NMEA protocol tests; local APIs pass for rasters, EXIF, GPX round trips, routes, coverage, grids, CSV, KMZ/mobile ZIP and asset relinking. Real USB hardware and physical Garmin transfer are not available to test. WMS/WMTS targets supported 3857 matrix configurations; other service grids are not auto-reprojected.

Verified: 93 Python tests, 38 Node tests; local browser import of georeferenced GeoTIFF, GPX metadata import, track statistics/profile selection, slope layer and coordinate conversion/grid controls. Full relocated portable EXE/API suite passed, including field asset relinking and clean archive checks. USB GPS and physical Garmin transfer remain hardware validation tasks, not claimed tested.

Browser NMEA replay verified four valid GGA/RMC sentences, two recorded fixes, receiver timestamps, MSL heights, HDOP/satellite count and no rejected frames. CSV conversion and 1 km Nord Sahara grid visible.
