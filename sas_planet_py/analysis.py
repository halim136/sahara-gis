"""
Spatial Data Analysis Models (GIS Analytics)
Implements:
1. Geodesic Buffer Analysis (Points, Polylines, Polygons)
2. Slope & Aspect Analysis (Slope degrees, percent, hazard rating)
3. Line of Sight (LOS) & Terrain Viewshed Obstruction
4. Convex Hull & Spatial Envelope (Graham Scan)
5. Proximity & Distance Matrix
"""

import math
from typing import List, Tuple, Dict, Any, Optional
from .geocalc import vincenty_distance, haversine_distance, calculate_azimuth, polygon_area_sq_meters
from .topography import get_elevation_at


class SpatialAnalysis:
    """Core spatial and geodetic analysis models."""

    @classmethod
    def point_buffer(cls, lat: float, lon: float, radius_meters: float, num_points: int = 48) -> List[List[float]]:
        """
        Creates a circular geodesic buffer around a point (lat, lon).
        Returns GeoJSON coordinates list [[lon, lat], ...].
        """
        coords = []
        r_earth = 6378137.0
        d_rad = radius_meters / r_earth
        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)

        for i in range(num_points):
            bearing = 2.0 * math.pi * i / num_points
            lat_p = math.asin(
                math.sin(lat_rad) * math.cos(d_rad) +
                math.cos(lat_rad) * math.sin(d_rad) * math.cos(bearing)
            )
            lon_p = lon_rad + math.atan2(
                math.sin(bearing) * math.sin(d_rad) * math.cos(lat_rad),
                math.cos(d_rad) - math.sin(lat_rad) * math.sin(lat_p)
            )
            coords.append([round(math.degrees(lon_p), 6), round(math.degrees(lat_p), 6)])

        # Close ring
        coords.append(coords[0])
        return coords

    @classmethod
    def path_buffer(cls, points: List[Tuple[float, float]], radius_meters: float) -> List[List[float]]:
        """
        Creates a corridor buffer around a polyline.
        points: list of (lat, lon).
        """
        if len(points) < 2:
            return cls.point_buffer(points[0][0], points[0][1], radius_meters)

        left_side = []
        right_side = []
        r_earth = 6378137.0
        d_rad = radius_meters / r_earth

        for i in range(len(points)):
            lat, lon = points[i]
            lat_rad = math.radians(lat)
            lon_rad = math.radians(lon)

            # Determine segment orientation
            if i < len(points) - 1:
                bearing = math.radians(calculate_azimuth(lat, lon, points[i+1][0], points[i+1][1]))
            else:
                bearing = math.radians(calculate_azimuth(points[i-1][0], points[i-1][1], lat, lon))

            # Left perpendicular
            b_left = bearing - math.pi / 2.0
            lat_l = math.asin(math.sin(lat_rad) * math.cos(d_rad) + math.cos(lat_rad) * math.sin(d_rad) * math.cos(b_left))
            lon_l = lon_rad + math.atan2(math.sin(b_left) * math.sin(d_rad) * math.cos(lat_rad), math.cos(d_rad) - math.sin(lat_rad) * math.sin(lat_l))
            left_side.append([round(math.degrees(lon_l), 6), round(math.degrees(lat_l), 6)])

            # Right perpendicular
            b_right = bearing + math.pi / 2.0
            lat_r = math.asin(math.sin(lat_rad) * math.cos(d_rad) + math.cos(lat_rad) * math.sin(d_rad) * math.cos(b_right))
            lon_r = lon_rad + math.atan2(math.sin(b_right) * math.sin(d_rad) * math.cos(lat_rad), math.cos(d_rad) - math.sin(lat_rad) * math.sin(lat_r))
            right_side.append([round(math.degrees(lon_r), 6), round(math.degrees(lat_r), 6)])

        polygon = left_side + list(reversed(right_side)) + [left_side[0]]
        return polygon

    @classmethod
    def analyze_slope_at(cls, lat: float, lon: float, delta_meters: float = 30.0) -> Dict[str, Any]:
        """
        Calculates terrain slope and aspect at a coordinate.
        Returns:
            slope_degrees, slope_percent, aspect_degrees, hazard_category.
        """
        d_deg_lat = delta_meters / 110574.0
        d_deg_lon = delta_meters / (111320.0 * math.cos(math.radians(lat)))

        z_center = get_elevation_at(lat, lon)
        z_north = get_elevation_at(lat + d_deg_lat, lon)
        z_south = get_elevation_at(lat - d_deg_lat, lon)
        z_east = get_elevation_at(lat, lon + d_deg_lon)
        z_west = get_elevation_at(lat, lon - d_deg_lon)

        dz_dx = (z_east - z_west) / (2.0 * delta_meters)
        dz_dy = (z_north - z_south) / (2.0 * delta_meters)

        slope_rad = math.atan(math.sqrt(dz_dx**2 + dz_dy**2))
        slope_deg = math.degrees(slope_rad)
        slope_pct = math.tan(slope_rad) * 100.0

        aspect_rad = math.atan2(dz_dy, -dz_dx)
        aspect_deg = (math.degrees(aspect_rad) + 360.0) % 360.0

        # Classification
        if slope_deg < 5.0:
            hazard = "Flat / Gentle (مستوٍ / انحدار خفيف)"
            color = "#22c55e"
        elif slope_deg < 15.0:
            hazard = "Moderate (انحدار متوسط)"
            color = "#eab308"
        elif slope_deg < 30.0:
            hazard = "Steep (انحدار حاد)"
            color = "#f97316"
        else:
            hazard = "Extreme / Cliff (انحدار شديد الخطورة / جرف)"
            color = "#ef4444"

        return {
            "latitude": lat,
            "longitude": lon,
            "elevation_m": z_center,
            "slope_degrees": round(slope_deg, 2),
            "slope_percent": round(slope_pct, 2),
            "aspect_degrees": round(aspect_deg, 1),
            "hazard_category": hazard,
            "hazard_color": color
        }

    @classmethod
    def line_of_sight(
        cls,
        observer: Tuple[float, float],
        target: Tuple[float, float],
        obs_height_m: float = 2.0,
        target_height_m: float = 2.0,
        samples: int = 50
    ) -> Dict[str, Any]:
        """
        Line of Sight (LOS) analysis along the terrain profile.
        Determines whether the target is visible from the observer,
        and identifies the highest terrain obstruction point if blocked.
        """
        lat1, lon1 = observer
        lat2, lon2 = target

        total_dist = haversine_distance(lat1, lon1, lat2, lon2)
        z_obs = get_elevation_at(lat1, lon1) + obs_height_m
        z_tgt = get_elevation_at(lat2, lon2) + target_height_m

        is_visible = True
        obstruction_point = None
        max_obstruction_depth = 0.0

        profile = []
        for i in range(samples + 1):
            t = i / samples
            cur_lat = lat1 + (lat2 - lat1) * t
            cur_lon = lon1 + (lon2 - lon1) * t
            cur_dist = total_dist * t

            # Ray elevation at this point
            ray_elev = z_obs + (z_tgt - z_obs) * t
            terrain_elev = get_elevation_at(cur_lat, cur_lon)

            # Earth curvature drop: d^2 / (2 * R)
            curv_drop = (cur_dist * (total_dist - cur_dist)) / (2.0 * 6371000.0)
            terrain_effective = terrain_elev + curv_drop

            profile.append({
                "distance_m": round(cur_dist, 1),
                "lat": round(cur_lat, 6),
                "lon": round(cur_lon, 6),
                "terrain_elevation": round(terrain_elev, 1),
                "sightline_elevation": round(ray_elev, 1),
                "is_blocked": terrain_effective > ray_elev if (0 < i < samples) else False
            })

            # Check interior points
            if 0 < i < samples and terrain_effective > ray_elev:
                is_visible = False
                depth = terrain_effective - ray_elev
                if depth > max_obstruction_depth:
                    max_obstruction_depth = depth
                    obstruction_point = {
                        "distance_m": round(cur_dist, 1),
                        "lat": round(cur_lat, 6),
                        "lon": round(cur_lon, 6),
                        "elevation_m": round(terrain_elev, 1),
                        "obstruction_height_m": round(depth, 1)
                    }

        return {
            "visible": is_visible,
            "total_distance_m": round(total_dist, 1),
            "total_distance_km": round(total_dist / 1000.0, 3),
            "observer_elevation_m": round(z_obs, 1),
            "target_elevation_m": round(z_tgt, 1),
            "obstruction": obstruction_point,
            "profile_samples": profile
        }

    @classmethod
    def convex_hull(cls, points: List[Tuple[float, float]]) -> List[List[float]]:
        """
        Computes the Convex Hull for a set of points (lat, lon) using Graham's scan.
        Returns GeoJSON polygon ring [[lon, lat], ...].
        """
        pts = list(set((p[1], p[0]) for p in points)) # (lon, lat)
        if len(pts) <= 3:
            res = [[p[0], p[1]] for p in pts]
            if res and res[0] != res[-1]:
                res.append(res[0])
            return res

        # Sort points lexicographically (by lon, then lat)
        pts.sort()

        def cross(o, a, b):
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

        # Lower hull
        lower = []
        for p in pts:
            while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
                lower.pop()
            lower.append(p)

        # Upper hull
        upper = []
        for p in reversed(pts):
            while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
                upper.pop()
            upper.append(p)

        hull = lower[:-1] + upper
        return [[p[0], p[1]] for p in hull]
