# SAS.Planet source assets

Extracted without modification from the user supplied sas.planet.src-v.260808.zip:

- icon64.png — Resources/MainIcon/icon64.png
- TrackProfile.svg — Resources/Icons/TrackProfile.svg
- YLW-PUSHPIN.png, ARROW.png, MAINMAP.png, VRULLER.png — Resources/Common/

Copyright (C) 2007–Present, SAS.Planet development team. The archive's GNU GPL v3 license is included verbatim as LICENSE.txt.
Original project: https://github.com/sasgis/sas.planet.src

Archive references reviewed for the new web functionality:
- Src/Terrain/External/u_ElevationReaderRAW.pas — row major elevation reader
- Src/MainForm/frm_Main.dfm — favorite maps and navigation actions
- Src/MainForm/FavoriteMapSet/ — favorite map configuration

The web favorites, navigation history and Python DEM/contour code are new implementations. SRTM HGT is explicitly decoded as big-endian signed int16. The original Delphi RAW reader uses its configured/native layout and is not copied as an HGT parser.

Terrain data uses separate source attribution; see https://github.com/tilezen/joerd/blob/master/docs/attribution.md.
