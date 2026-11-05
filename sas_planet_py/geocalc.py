"""
Geodesic and Distance Calculations
Based on SAS.Planet's GeoCalc subsystem:
- u_DistanceCalculatorByVincentyAlgorithm.pas
- u_PolygonAreaCalculator.pas
- GeographicLib.pas
"""

import math
from typing import List, Tuple, Dict, Any

WGS84_A = 6378137.0
WGS84_B = 6356752.314245
WGS84_F = 1.0 / 298.257223563


def vincenty_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> Dict[str, float]:
    """
    Calculate geodesic distance and azimuth between two points on the WGS-84 ellipsoid
    using Vincenty's inverse formula.
    Returns:
        dict with:
            - distance: meters
            - initial_bearing: degrees (0-360)
            - final_bearing: degrees (0-360)
    """
    if abs(lat1 - lat2) < 1e-12 and abs(lon1 - lon2) < 1e-12:
        return {"distance": 0.0, "initial_bearing": 0.0, "final_bearing": 0.0}

    a = WGS84_A
    b = WGS84_B
    f = WGS84_F

    L = math.radians(lon2 - lon1)
    U1 = math.atan((1 - f) * math.tan(math.radians(lat1)))
    U2 = math.atan((1 - f) * math.tan(math.radians(lat2)))
    sinU1 = math.sin(U1)
    cosU1 = math.cos(U1)
    sinU2 = math.sin(U2)
    cosU2 = math.cos(U2)

    lam = L
    lam_prev = 0.0
    iter_limit = 100

    while abs(lam - lam_prev) > 1e-12 and iter_limit > 0:
        sin_lam = math.sin(lam)
        cos_lam = math.cos(lam)

        sin_sigma = math.sqrt(
            (cosU2 * sin_lam) ** 2 +
            (cosU1 * sinU2 - sinU1 * cosU2 * cos_lam) ** 2
        )
        if sin_sigma == 0:
            return {"distance": 0.0, "initial_bearing": 0.0, "final_bearing": 0.0}

        cos_sigma = sinU1 * sinU2 + cosU1 * cosU2 * cos_lam
        sigma = math.atan2(sin_sigma, cos_sigma)

        sin_alpha = cosU1 * cosU2 * sin_lam / sin_sigma
        cos2_alpha = 1.0 - sin_alpha ** 2

        if cos2_alpha == 0:
            cos2_sigma_m = 0.0
        else:
            cos2_sigma_m = cos_sigma - 2.0 * sinU1 * sinU2 / cos2_alpha

        C = f / 16.0 * cos2_alpha * (4.0 + f * (4.0 - 3.0 * cos2_alpha))
        lam_prev = lam
        lam = L + (1.0 - C) * f * sin_alpha * (
            sigma + C * sin_sigma * (
                cos2_sigma_m + C * cos_sigma * (-1.0 + 2.0 * cos2_sigma_m ** 2)
            )
        )
        iter_limit -= 1

    u2 = cos2_alpha * (a ** 2 - b ** 2) / (b ** 2)
    A = 1.0 + u2 / 16384.0 * (4096.0 + u2 * (-768.0 + u2 * (320.0 - 175.0 * u2)))
    B = u2 / 1024.0 * (256.0 + u2 * (-128.0 + u2 * (74.0 - 47.0 * u2)))
    delta_sigma = B * sin_sigma * (
        cos2_sigma_m + B / 4.0 * (
            cos_sigma * (-1.0 + 2.0 * cos2_sigma_m ** 2) -
            B / 6.0 * cos2_sigma_m * (-3.0 + 4.0 * sin_sigma ** 2) * (-3.0 + 4.0 * cos2_sigma_m ** 2)
        )
    )

    s = b * A * (sigma - delta_sigma)

    # Calculate initial and final bearing
    alpha1 = math.atan2(cosU2 * math.sin(lam), cosU1 * sinU2 - sinU1 * cosU2 * math.cos(lam))
    alpha2 = math.atan2(cosU1 * math.sin(lam), -sinU1 * cosU2 + cosU1 * sinU2 * math.cos(lam))

    init_bearing = (math.degrees(alpha1) + 360.0) % 360.0
    final_bearing = (math.degrees(alpha2) + 360.0) % 360.0

    return {
        "distance": round(s, 3),
        "initial_bearing": round(init_bearing, 2),
        "final_bearing": round(final_bearing, 2)
    }


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Fast Great-Circle spherical distance in meters."""
    R = 6371000.0  # Earth mean radius
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


def calculate_azimuth(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate azimuth / forward azimuth from (lat1, lon1) to (lat2, lon2)."""
    phi1, lam1 = math.radians(lat1), math.radians(lon1)
    phi2, lam2 = math.radians(lat2), math.radians(lon2)
    d_lam = lam2 - lam1
    y = math.sin(d_lam) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lam)
    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360.0) % 360.0


def path_length(coords: List[Tuple[float, float]]) -> float:
    """Calculate total path length in meters from list of (lat, lon) coordinates."""
    if len(coords) < 2:
        return 0.0
    total = 0.0
    for i in range(len(coords) - 1):
        lat1, lon1 = coords[i]
        lat2, lon2 = coords[i + 1]
        dist = vincenty_distance(lat1, lon1, lat2, lon2)["distance"]
        total += dist
    return round(total, 3)


def polygon_area_sq_meters(coords: List[Tuple[float, float]]) -> float:
    """
    Calculate geodesic area of a polygon on the Earth sphere (m^2).
    Coordinates: list of (lat, lon).
    Uses spherical excess (Girard's theorem / Green's theorem on sphere).
    """
    if len(coords) < 3:
        return 0.0

    R = 6378137.0
    area = 0.0

    # Ensure closed ring
    pts = list(coords)
    if pts[0] != pts[-1]:
        pts.append(pts[0])

    num_pts = len(pts)
    for i in range(num_pts - 1):
        p1 = pts[i]
        p2 = pts[i + 1]
        lat1, lon1 = math.radians(p1[0]), math.radians(p1[1])
        lat2, lon2 = math.radians(p2[0]), math.radians(p2[1])
        area += (lon2 - lon1) * (2.0 + math.sin(lat1) + math.sin(lat2))

    area = abs(area * (R ** 2) / 2.0)
    return round(area, 2)


def generate_elevation_profile(coords: List[Tuple[float, float]], num_samples: int = 50, source: str = "terrain", offline: bool = False) -> List[Dict[str, Any]]:
    """
    Generate an elevation profile along a path of coordinates (lat, lon).
    Returns list of samples with distance, lat, lon, elevation (meters).
    Samples real Mapzen terrain tiles; never substitutes procedural heights.
    """
    if len(coords) < 2:
        return []

    # Calculate cumulative distances
    seg_dists = []
    total_dist = 0.0
    for i in range(len(coords) - 1):
        d = haversine_distance(coords[i][0], coords[i][1], coords[i+1][0], coords[i+1][1])
        seg_dists.append(d)
        total_dist += d

    if total_dist == 0:
        return []

    if not isinstance(num_samples, int) or not 2 <= num_samples <= 512:
        raise ValueError("Samples must be an integer between 2 and 512.")
    step = total_dist / (num_samples - 1)
    samples = []

    cur_dist = 0.0
    for idx in range(num_samples):
        target_dist = idx * step
        # find segment
        accum = 0.0
        seg_idx = 0
        for i, sd in enumerate(seg_dists):
            if accum + sd >= target_dist or i == len(seg_dists) - 1:
                seg_idx = i
                break
            accum += sd

        t = 0.0
        if seg_dists[seg_idx] > 0:
            t = (target_dist - accum) / seg_dists[seg_idx]
            t = max(0.0, min(1.0, t))

        p1 = coords[seg_idx]
        p2 = coords[min(seg_idx + 1, len(coords) - 1)]
        cur_lat = p1[0] + (p2[0] - p1[0]) * t
        cur_lon = p1[1] + (p2[1] - p1[1]) * t

        samples.append({
            "index": idx,
            "distance_m": round(target_dist, 1),
            "distance_km": round(target_dist / 1000.0, 3),
            "lat": round(cur_lat, 6),
            "lon": round(cur_lon, 6),
            "elevation_m": 0
        })

    from .terrain import TerrainReader
    elevations = TerrainReader(source, offline).sample_points([(s["lat"], s["lon"]) for s in samples])
    if any(h is None for h in elevations):
        raise ValueError("Profile contains missing elevations.")
    for sample, elevation in zip(samples, elevations):
        sample["elevation_m"] = round(elevation, 2)
    return samples
