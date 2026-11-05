"""Topographic analysis of measured DEM data; no synthetic elevation fallback."""
import math
import os
import struct
from collections import defaultdict
from typing import List, Dict, Any, Tuple, Optional
from .terrain import TerrainReader, validate_bbox


def get_elevation_at(lat: float, lon: float) -> float:
    value = TerrainReader().sample_points([(lat, lon)])[0]
    if value is None:
        raise ValueError("No elevation data at this point.")
    return value


def _join_segments(segments):
    """Join shared endpoints into open paths and closed rings without invented edges."""
    adjacency = defaultdict(list)
    points = {}
    for a, b in segments:
        ka, kb = tuple(round(v, 12) for v in a), tuple(round(v, 12) for v in b)
        if ka == kb:
            continue
        points.setdefault(ka, a)
        points.setdefault(kb, b)
        adjacency[ka].append(kb)
        adjacency[kb].append(ka)
    paths = []

    def walk(start, nxt):
        path = [points[start]]
        previous, current = start, nxt
        while True:
            adjacency[previous].remove(current)
            adjacency[current].remove(previous)
            path.append(points[current])
            if current == start or len(adjacency[current]) != 1:
                break
            previous, current = current, adjacency[current][0]
        return path

    for key in list(adjacency):
        if len(adjacency[key]) != 2:
            while adjacency[key]:
                paths.append(walk(key, adjacency[key][0]))
    for key in adjacency:
        while adjacency[key]:
            paths.append(walk(key, adjacency[key][0]))
    return paths


class TopographicEngine:
    @classmethod
    def generate_dem_grid(cls, bbox, rows=256, cols=256, source="terrain", offline=False):
        return TerrainReader(source, offline).grid(bbox, rows, cols)

    @classmethod
    def generate_contour_geojson(cls, bbox, interval=25.0, rows=256, cols=256,
                                 source="terrain", offline=False, above_sea_only=True, dem=None):
        validate_bbox(bbox)
        if isinstance(interval, bool) or not isinstance(interval, (int, float)) or not math.isfinite(interval) or interval <= 0:
            raise ValueError("Contour interval must be a positive finite number.")
        dem = dem if dem is not None else cls.generate_dem_grid(bbox, rows, cols, source, offline)
        grid, rows, cols = dem["grid"], dem["rows"], dem["cols"]
        west, south, east, north = bbox
        dx, dy = dem["dx"], dem["dy"]
        first = math.ceil(dem["min_elevation"] / interval)
        last = math.floor(dem["max_elevation"] / interval)
        if above_sea_only:
            first = max(1, first)
        count = max(0, last-first+1)
        if count > 512 or count*(rows-1)*(cols-1) > 40_000_000:
            raise ValueError("Too many contour levels. Increase the interval or select a smaller region.")
        features = []
        for k in range(first, last+1):
            level = k*interval
            segments = []
            for r in range(rows-1):
                top, bottom = north-r*dy, north-(r+1)*dy
                for c in range(cols-1):
                    vals = (grid[r][c], grid[r][c+1], grid[r+1][c+1], grid[r+1][c])
                    if any(v is None or not math.isfinite(v) for v in vals):
                        continue
                    if min(vals) >= level or max(vals) < level:
                        continue
                    left, right = west+c*dx, west+(c+1)*dx
                    corners = ((left,top),(right,top),(right,bottom),(left,bottom))
                    crossings = {}
                    for edge, (a, b) in enumerate(((0,1),(1,2),(2,3),(3,0))):
                        if (vals[a] >= level) != (vals[b] >= level):
                            t = (level-vals[a])/(vals[b]-vals[a])
                            crossings[edge] = [corners[a][j]+t*(corners[b][j]-corners[a][j]) for j in (0,1)]
                    if len(crossings) == 2:
                        segments.append(list(crossings.values()))
                    elif len(crossings) == 4:
                        # Asymptotic decider: resolve both saddle branches instead of discarding one.
                        q = (vals[0]-level)*(vals[2]-level)-(vals[1]-level)*(vals[3]-level)
                        pairs = ((0,1),(2,3)) if q >= 0 else ((0,3),(1,2))
                        segments.extend([crossings[a], crossings[b]] for a,b in pairs)
            for path in _join_segments(segments):
                features.append({"type": "Feature", "properties": {
                    "elevation": round(level, 8), "interval": interval, "is_index": k % 5 == 0,
                    "stroke_width": 1.8 if k % 5 == 0 else 0.8,
                    "color": "#92400e" if k % 5 == 0 else "#d97706"},
                    "geometry": {"type": "LineString", "coordinates": path}})
        metadata = {key: value for key, value in dem.items() if key not in ("grid", "dx", "dy")}
        return {"type": "FeatureCollection", "bbox": list(bbox),
                "properties": {**metadata, "interval": interval, "above_sea_only": above_sea_only,
                               "line_count": len(features)}, "features": features}

    @classmethod
    def calculate_hillshade(
        cls,
        grid: List[List[float]],
        dx_meters: float,
        dy_meters: float,
        azimuth_deg: float = 315.0,
        altitude_deg: float = 45.0
    ) -> List[List[int]]:
        """
        Horn's method for shaded relief (Hillshade):
        Light source: Azimuth (315° NW) and Altitude (45°).
        Returns 2D grid of values (0-255).
        """
        rows = len(grid)
        cols = len(grid[0])
        zenith_rad = math.radians(90.0 - altitude_deg)
        azimuth_math = 360.0 - azimuth_deg + 90.0
        if azimuth_math >= 360.0:
            azimuth_math -= 360.0
        azimuth_rad = math.radians(azimuth_math)

        hillshade = []
        for r in range(rows):
            row_hs = []
            for c in range(cols):
                # 3x3 neighborhood
                r_prev = max(0, r - 1)
                r_next = min(rows - 1, r + 1)
                c_prev = max(0, c - 1)
                c_next = min(cols - 1, c + 1)

                a = grid[r_prev][c_prev]
                b = grid[r_prev][c]
                cc = grid[r_prev][c_next]
                d = grid[r][c_prev]
                f = grid[r][c_next]
                g = grid[r_next][c_prev]
                h = grid[r_next][c]
                i = grid[r_next][c_next]

                # Rate of change
                dz_dx = ((cc + 2 * f + i) - (a + 2 * d + g)) / (8.0 * max(dx_meters, 1.0))
                dz_dy = ((g + 2 * h + i) - (a + 2 * b + cc)) / (8.0 * max(dy_meters, 1.0))

                slope_rad = math.atan(math.sqrt(dz_dx**2 + dz_dy**2))
                aspect_rad = math.atan2(dz_dy, -dz_dx) if (dz_dx != 0 or dz_dy != 0) else 0.0

                hs = (math.cos(zenith_rad) * math.cos(slope_rad)) + (
                    math.sin(zenith_rad) * math.sin(slope_rad) * math.cos(azimuth_rad - aspect_rad)
                )
                hs_byte = max(0, min(255, int(hs * 255)))
                row_hs.append(hs_byte)
            hillshade.append(row_hs)

        return hillshade

    @classmethod
    def render_topographic_bmp(
        cls,
        bbox: Tuple[float, float, float, float],
        output_filepath: str,
        width: int = 512,
        height: int = 512,
        source: str = "terrain",
        offline: bool = False
    ) -> Dict[str, Any]:
        """
        Renders a full topographic color relief + hillshade raster as 24-bit BMP with WorldFile.
        """
        validate_bbox(bbox)
        if any(not isinstance(n, int) or isinstance(n, bool) or not 2 <= n <= 1024 for n in (width, height)):
            raise ValueError("Raster size must be between 2 and 1024 pixels.")
        west, south, east, north = bbox
        pw, ph = (east-west)/width, (north-south)/height
        centers_bbox = (west+pw/2, south+ph/2, east-pw/2, north-ph/2)
        dem = cls.generate_dem_grid(centers_bbox, rows=height, cols=width, source=source, offline=offline)
        if dem["nodata_samples"]:
            raise ValueError("Raster contains missing elevations. Select a region with complete DEM coverage.")
        grid = dem["grid"]
        min_e = dem["min_elevation"]
        max_e = dem["max_elevation"]

        # Approximate cell resolution in meters
        min_lon, min_lat, max_lon, max_lat = bbox
        dx_m = ((max_lon - min_lon) * 111320.0 * math.cos(math.radians((min_lat + max_lat) / 2.0))) / width
        dy_m = ((max_lat - min_lat) * 110574.0) / height

        hillshade = cls.calculate_hillshade(grid, dx_m, dy_m)

        row_size = (width * 3 + 3) & ~3
        pixels = bytearray(row_size * height)

        def elevation_color(elev: float, shade_val: int) -> Tuple[int, int, int]:
            # Hypsometric color ramp
            norm = (elev - min_e) / max(1.0, max_e - min_e)
            if norm < 0.2:
                r, g, b = (56, 142, 60)   # Green lowlands
            elif norm < 0.4:
                r, g, b = (139, 195, 74)  # Light green hills
            elif norm < 0.6:
                r, g, b = (255, 213, 79)  # Yellow plateau
            elif norm < 0.8:
                r, g, b = (188, 108, 37)  # Brown mountains
            else:
                r, g, b = (245, 245, 245) # Snow peaks

            # Blend with hillshade
            factor = (shade_val / 255.0) * 1.35
            rf = max(0, min(255, int(r * factor)))
            gf = max(0, min(255, int(g * factor)))
            bf = max(0, min(255, int(b * factor)))
            return rf, gf, bf

        for r in range(height):
            bmp_r = height - 1 - r  # BMP bottom-up
            row_idx = bmp_r * row_size
            for c in range(width):
                elev = grid[r][c]
                hs = hillshade[r][c]
                rf, gf, bf = elevation_color(elev, hs)
                col_idx = row_idx + c * 3
                pixels[col_idx] = bf
                pixels[col_idx + 1] = gf
                pixels[col_idx + 2] = rf

        os.makedirs(os.path.dirname(os.path.abspath(output_filepath)), exist_ok=True)

        # Write 24-bit BMP
        file_size = 54 + len(pixels)
        bmp_header = struct.pack("<2sIHHI", b"BM", file_size, 0, 0, 54)
        dib_header = struct.pack("<IIIHHIIIIII", 40, width, height, 1, 24, 0, len(pixels), 2835, 2835, 0, 0)

        with open(output_filepath, "wb") as f:
            f.write(bmp_header)
            f.write(dib_header)
            f.write(pixels)

        # Write World File
        wf_path = os.path.splitext(output_filepath)[0] + ".bpw"
        pix_w = (max_lon - min_lon) / width
        pix_h = -(max_lat - min_lat) / height
        cx = min_lon + (pix_w / 2.0)
        cy = max_lat + (pix_h / 2.0)
        with open(wf_path, "w", encoding="utf-8") as wf:
            wf.write(f"{pix_w:.10f}\n0.0\n0.0\n{pix_h:.10f}\n{cx:.10f}\n{cy:.10f}\n")

        return {
            "image_path": output_filepath,
            "world_file_path": wf_path,
            "width": width,
            "height": height,
            "min_elevation": min_e,
            "max_elevation": max_e,
            "bbox": bbox,
            "source": dem["source"],
            "attribution": dem.get("attribution"),
            "crs": "EPSG:4326"
        }
