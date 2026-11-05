"""
Coordinate Conversions and Projections
Based on SAS.Planet's CoordConvert subsystem:
- u_ProjectionTypeMercatorOnSphere.pas (EPSG:3857)
- u_ProjectionTypeMercatorOnEllipsoid.pas (EPSG:3395)
- u_ProjectionTypeGeographic.pas (EPSG:4326)
- Proj4.UTM.pas / Proj4.GaussKruger.pas
"""

import math
from typing import Tuple, Dict, Any

# Constants
WGS84_A = 6378137.0          # semi-major axis (meters)
WGS84_F = 1.0 / 298.257223563 # flattening
WGS84_B = WGS84_A * (1.0 - WGS84_F) # semi-minor axis
WGS84_E2 = 1.0 - (WGS84_B * WGS84_B) / (WGS84_A * WGS84_A) # eccentricity squared
WGS84_E = math.sqrt(WGS84_E2)

TILE_SIZE = 256


def lon_lat_to_tile(lon: float, lat: float, zoom: int) -> Tuple[int, int]:
    """Convert longitude and latitude to Tile X, Y at a given zoom level (EPSG:3857)."""
    # Clamp lat to standard Web Mercator limits (-85.05112878 to 85.05112878)
    lat = max(min(lat, 85.0511287798066), -85.0511287798066)
    n = 2.0 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    # Clamp to valid tile range
    max_idx = (1 << zoom) - 1
    x = max(0, min(x, max_idx))
    y = max(0, min(y, max_idx))
    return x, y


def tile_to_lon_lat(x: float, y: float, zoom: int) -> Tuple[float, float]:
    """Convert Tile X, Y at zoom level to NW corner Longitude and Latitude (degrees)."""
    n = 2.0 ** zoom
    lon = x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / n)))
    lat = math.degrees(lat_rad)
    return lon, lat


def tile_bounds(x: int, y: int, zoom: int) -> Dict[str, float]:
    """
    Returns the bounding box coordinates (min_lon, min_lat, max_lon, max_lat)
    for a given tile (x, y, zoom).
    """
    nw_lon, nw_lat = tile_to_lon_lat(x, y, zoom)
    se_lon, se_lat = tile_to_lon_lat(x + 1, y + 1, zoom)
    return {
        "min_lon": nw_lon,
        "max_lon": se_lon,
        "min_lat": se_lat,
        "max_lat": nw_lat
    }


def lon_lat_to_pixel(lon: float, lat: float, zoom: int) -> Tuple[float, float]:
    """Convert lon/lat to world pixel coordinates at given zoom level (256 * 2^zoom)."""
    lat = max(min(lat, 85.0511287798066), -85.0511287798066)
    scale = TILE_SIZE * (2 ** zoom)
    x = (lon + 180.0) / 360.0 * scale
    lat_rad = math.radians(lat)
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * scale
    return x, y


def pixel_to_lon_lat(px: float, py: float, zoom: int) -> Tuple[float, float]:
    """Convert world pixel coordinate to lon/lat."""
    scale = TILE_SIZE * (2 ** zoom)
    lon = px / scale * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1.0 - 2.0 * py / scale)))
    lat = math.degrees(lat_rad)
    return lon, lat


class MercatorProjection:
    """EPSG:3857 (Spherical Mercator - standard Google, OSM, Bing)."""
    NAME = "EPSG:3857 (Spherical Mercator)"
    
    @staticmethod
    def forward(lon: float, lat: float) -> Tuple[float, float]:
        """Convert lon/lat (degrees) to Spherical Mercator meters (x, y)."""
        x = lon * (math.pi * WGS84_A / 180.0)
        lat = max(min(lat, 85.05112878), -85.05112878)
        y = math.log(math.tan((90.0 + lat) * math.pi / 360.0)) * WGS84_A
        return x, y

    @staticmethod
    def inverse(x: float, y: float) -> Tuple[float, float]:
        """Convert Spherical Mercator meters (x, y) to lon/lat (degrees)."""
        lon = (x / (math.pi * WGS84_A)) * 180.0
        lat = 180.0 / math.pi * (2.0 * math.atan(math.exp(y / WGS84_A)) - math.pi / 2.0)
        return lon, lat


class EllipsoidalMercatorProjection:
    """EPSG:3395 (WGS 84 / World Mercator on Ellipsoid - used in Yandex Maps)."""
    NAME = "EPSG:3395 (Ellipsoidal Mercator)"

    @staticmethod
    def forward(lon: float, lat: float) -> Tuple[float, float]:
        x = WGS84_A * math.radians(lon)
        phi = math.radians(lat)
        sin_phi = math.sin(phi)
        con = WGS84_E * sin_phi
        con = ((1.0 - con) / (1.0 + con)) ** (WGS84_E / 2.0)
        ts = math.tan(0.5 * (math.pi * 0.5 - phi)) / con
        y = -WGS84_A * math.log(max(ts, 1e-10))
        return x, y

    @staticmethod
    def inverse(x: float, y: float) -> Tuple[float, float]:
        lon = math.degrees(x / WGS84_A)
        ts = math.exp(-y / WGS84_A)
        phi = math.pi * 0.5 - 2.0 * math.atan(ts)
        for _ in range(15):
            con = WGS84_E * math.sin(phi)
            dphi = math.pi * 0.5 - 2.0 * math.atan(ts * (((1.0 - con) / (1.0 + con)) ** (WGS84_E * 0.5))) - phi
            phi += dphi
            if abs(dphi) < 1e-10:
                break
        return lon, math.degrees(phi)


class GeographicProjection:
    """EPSG:4326 (Plate Carrée / Geographic)."""
    NAME = "EPSG:4326 (WGS 84 Geographic)"

    @staticmethod
    def forward(lon: float, lat: float) -> Tuple[float, float]:
        return lon, lat

    @staticmethod
    def inverse(x: float, y: float) -> Tuple[float, float]:
        return x, y


def lat_lon_to_utm(lat: float, lon: float) -> Dict[str, Any]:
    """Calculate UTM Zone and Easting/Northing coordinates."""
    zone = int((lon + 180) / 6) + 1
    lon0 = (zone - 1) * 6 - 180 + 3
    lon0_rad = math.radians(lon0)
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)

    k0 = 0.9996
    e2 = WGS84_E2
    e_prime2 = e2 / (1.0 - e2)
    n = WGS84_A / math.sqrt(1.0 - e2 * math.sin(lat_rad) ** 2)
    t = math.tan(lat_rad) ** 2
    c = e_prime2 * math.cos(lat_rad) ** 2
    a_term = math.cos(lat_rad) * (lon_rad - lon0_rad)

    m = WGS84_A * (
        (1.0 - e2 / 4.0 - 3.0 * e2 ** 2 / 64.0 - 5.0 * e2 ** 3 / 256.0) * lat_rad
        - (3.0 * e2 / 8.0 + 3.0 * e2 ** 2 / 32.0 + 45.0 * e2 ** 3 / 1024.0) * math.sin(2.0 * lat_rad)
        + (15.0 * e2 ** 2 / 256.0 + 45.0 * e2 ** 3 / 1024.0) * math.sin(4.0 * lat_rad)
        - (35.0 * e2 ** 3 / 3072.0) * math.sin(6.0 * lat_rad)
    )

    easting = 500000.0 + k0 * n * (
        a_term
        + (1.0 - t + c) * a_term ** 3 / 6.0
        + (5.0 - 18.0 * t + t ** 2 + 72.0 * c - 58.0 * e_prime2) * a_term ** 5 / 120.0
    )

    northing = k0 * (
        m
        + n * math.tan(lat_rad) * (
            a_term ** 2 / 2.0
            + (5.0 - t + 9.0 * c + 4.0 * c ** 2) * a_term ** 4 / 24.0
            + (61.0 - 58.0 * t + t ** 2 + 600.0 * c - 330.0 * e_prime2) * a_term ** 6 / 720.0
        )
    )
    if lat < 0:
        northing += 10000000.0

    hemi = "N" if lat >= 0 else "S"
    return {
        "zone": zone,
        "hemisphere": hemi,
        "easting": round(easting, 2),
        "northing": round(northing, 2),
        "formatted": f"{zone}{hemi} {int(easting)}E {int(northing)}N"
    }


def to_dms(deg: float, is_lat: bool = True) -> str:
    """Format decimal degrees into Degrees, Minutes, Seconds (DMS) string."""
    hemi = ("N" if deg >= 0 else "S") if is_lat else ("E" if deg >= 0 else "W")
    deg_abs = abs(deg)
    d = int(deg_abs)
    m = int((deg_abs - d) * 60)
    s = (deg_abs - d - m / 60) * 3600
    return f"{d}°{m:02d}'{s:05.2f}\"{hemi}"
