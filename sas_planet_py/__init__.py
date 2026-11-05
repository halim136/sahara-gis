"""
SAS.Planet Python Core Library (sas_planet_py)
==============================================
A pure Python reproduction of the core systems of SAS.Planet:
- Multi-projection conversions (Web Mercator, Ellipsoidal Mercator, WGS84, UTM, UTM Nord Sahara 1959 / Voirol 1960)
- Geodesic calculations (Vincenty distance, initial bearing, geodesic polygon area)
- Topographic modeling (DEM grids, Marching Squares contour generation, Hillshade, Hypsometry)
- Spatial Analysis (Geodesic Buffers, Slope/Aspect hazard ratings, Line of Sight obstruction, Convex Hull)
- Multi-source tile fetching with customizable headers, retry, and rate limiting
- Tile storage engines (SAS hierarchy, OSM/TMS directories, SQLite MBTiles)
- Tile stitching with WorldFile and Baseline GeoTIFF generation
- Vector formats (GPX, KML, GeoJSON)
"""

from .projections import (
    lon_lat_to_tile,
    tile_to_lon_lat,
    tile_bounds,
    MercatorProjection,
    EllipsoidalMercatorProjection,
    GeographicProjection,
    lat_lon_to_utm
)
from .nord_sahara import (
    wgs84_to_utm_nord_sahara,
    utm_nord_sahara_to_wgs84,
    wgs84_to_nord_sahara_geodetic,
    nord_sahara_geodetic_to_wgs84,
    nord_sahara_to_utm,
    utm_to_nord_sahara
)
from .geocalc import (
    vincenty_distance,
    haversine_distance,
    calculate_azimuth,
    polygon_area_sq_meters,
    path_length,
    generate_elevation_profile
)
from .topography import TopographicEngine, get_elevation_at
from .analysis import SpatialAnalysis
from .map_sources import MAP_SOURCES, get_source
from .tile_storage import FileSystemStorage, MBTilesStorage
from .tile_downloader import TileDownloader, DownloadJob
from .tile_stitcher import TileStitcher
from .vector_formats import parse_vector_data, export_vector_data

__version__ = "26.08.08"
__author__ = "SAS.Planet Python Engine"
