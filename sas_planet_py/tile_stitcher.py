"""
Tile Stitcher & Georeferencing Engine
Based on SAS.Planet's RegionProcess/Combine:
- u_ImageTileProvider.pas
- u_CalcWFileParams.pas
- u_BmpWriter.pas
- u_BitmapMapCombinerGeoTIFF.pas
Stitches real map tile blocks into georeferenced rasters (JPEG, BMP, PNG, GeoTIFF, WorldFiles).
"""

import os
import io
import random
import urllib.request
from typing import Tuple, List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
import numpy as np
from pyproj import CRS, Transformer
from rasterio.transform import from_bounds
from rasterio.warp import calculate_default_transform, reproject, Resampling
import rasterio

# Disable decompression bomb limit for high-resolution GIS composites
Image.MAX_IMAGE_PIXELS = None

from .projections import lon_lat_to_tile, tile_to_lon_lat, tile_bounds
from .map_sources import get_source
from .tile_storage import FileSystemStorage

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 SAS.Planet/26.08.08"
)


class TileStitcher:
    """Stitches real tiles into a single georeferenced composite image."""

    @staticmethod
    def calculate_world_file_params(transform) -> List[float]:
        """
        Calculates 6 ESRI World File parameters (.jgw, .tfw, .bpw, .pgw, .wld):
        Line 1: A = pixel width in map units
        Line 2: D = rotation about Y axis (0.0)
        Line 3: B = rotation about X axis (0.0)
        Line 4: E = pixel height in map units (negative)
        Line 5: C = X coordinate of center of upper left pixel
        Line 6: F = Y coordinate of center of upper left pixel
        """
        # Affine stores the outer corner, WorldFile stores the centre of pixel 0,0.
        return [transform.a, transform.d, transform.b, transform.e,
                transform.c + (transform.a + transform.b) / 2,
                transform.f + (transform.d + transform.e) / 2]

    @staticmethod
    def write_world_file(filepath: str, params: List[float]):
        """Writes World File (.jgw / .tfw / .bpw / .wld)."""
        with open(filepath, "w", encoding="utf-8") as f:
            for p in params:
                f.write(f"{p:.10f}\n")

    @classmethod
    def stitch_bbox(
        cls,
        source_id: str,
        bbox: Tuple[float, float, float, float],
        zoom: int,
        output_image_path: str,
        cache_dir: Optional[str] = None,
        concurrency: int = 12,
        target_crs: str = "EPSG:3857"
    ) -> Dict[str, Any]:
        """
        Stitches all tiles covering bbox at given zoom level into a real composite raster.
        Loads from disk cache or downloads missing tiles concurrently, pastes real imagery,
        and generates the georeferenced image and ESRI World File.
        """
        min_lon, min_lat, max_lon, max_lat = bbox
        x_min, y_max = lon_lat_to_tile(min_lon, min_lat, zoom)
        x_max, y_min = lon_lat_to_tile(max_lon, max_lat, zoom)

        start_x, end_x = min(x_min, x_max), max(x_min, x_max)
        start_y, end_y = min(y_min, y_max), max(y_min, y_max)

        num_tiles_x = end_x - start_x + 1
        num_tiles_y = end_y - start_y + 1

        width_px = num_tiles_x * 256
        height_px = num_tiles_y * 256

        # Actual geographic bounds of the stitched tile grid
        nw_bounds = tile_bounds(start_x, start_y, zoom)
        se_bounds = tile_bounds(end_x, end_y, zoom)
        actual_min_lon = nw_bounds["min_lon"]
        actual_max_lat = nw_bounds["max_lat"]
        actual_max_lon = se_bounds["max_lon"]
        actual_min_lat = se_bounds["min_lat"]

        storage = FileSystemStorage(base_dir=cache_dir)
        source = get_source(source_id)
        url_template = source.get("url_template", "")
        subdomains = source.get("subdomains", ["0", "1", "2", "3"])
        ext = source.get("format", "jpg")

        tiles_needed = []
        tiles_data: Dict[Tuple[int, int], bytes] = {}

        # 1. First, check cache on disk
        for x in range(start_x, end_x + 1):
            for y in range(start_y, end_y + 1):
                data = None
                # Check preferred ext, then fallback extensions
                for check_ext in (ext, "jpg", "png", "jpeg", "webp"):
                    data = storage.load_tile(source_id, zoom, x, y, check_ext)
                    if data:
                        break
                if data:
                    tiles_data[(x, y)] = data
                else:
                    tiles_needed.append((x, y))

        # 2. Download missing tiles concurrently
        if tiles_needed and url_template:
            def fetch_tile(coord: Tuple[int, int]) -> Tuple[int, int, bytes]:
                tx, ty = coord
                sub = random.choice(subdomains) if subdomains else ""
                url = url_template.format(z=zoom, x=tx, y=ty, s=sub)
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": DEFAULT_USER_AGENT,
                        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                        "Referer": "https://www.google.com/"
                    }
                )
                try:
                    with urllib.request.urlopen(req, timeout=12) as resp:
                        content = resp.read()
                        if content:
                            storage.save_tile(source_id, zoom, tx, ty, content, ext)
                            return tx, ty, content
                except Exception:
                    pass
                return tx, ty, b""

            workers = max(1, min(concurrency, len(tiles_needed)))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(fetch_tile, c) for c in tiles_needed]
                for fut in as_completed(futures):
                    tx, ty, data = fut.result()
                    if data:
                        tiles_data[(tx, ty)] = data

        # 3. Create composite Pillow image
        composite = Image.new("RGB", (width_px, height_px), (24, 28, 38))

        # 4. Paste each real tile at its pixel location (top-to-bottom)
        for x in range(start_x, end_x + 1):
            for y in range(start_y, end_y + 1):
                px = (x - start_x) * 256
                py = (y - start_y) * 256
                data = tiles_data.get((x, y), b"")
                if data:
                    try:
                        tile_img = Image.open(io.BytesIO(data))
                        if tile_img.mode != "RGB":
                            tile_img = tile_img.convert("RGB")
                        composite.paste(tile_img, (px, py))
                    except Exception:
                        pass

        # 5. Correct georeferencing. Web tiles are EPSG:3857, not a linear
        # longitude/latitude image. Reproject pixels before writing a WGS84 or
        # Nord Sahara product; never merely replace values in a WorldFile.
        os.makedirs(os.path.dirname(os.path.abspath(output_image_path)), exist_ok=True)
        out_ext = os.path.splitext(output_image_path)[1].lower()
        allowed_crs = {"EPSG:3857", "EPSG:4326", "EPSG:30729", "EPSG:30730", "EPSG:30731", "EPSG:30732"}
        target_crs = str(target_crs).upper()
        if target_crs not in allowed_crs:
            raise ValueError("Select a supported output coordinate system.")
        source_crs = CRS.from_epsg(3857)
        target = CRS.from_user_input(target_crs)
        mercator = Transformer.from_crs(4326, source_crs, always_xy=True)
        west, south = mercator.transform(actual_min_lon, actual_min_lat)
        east, north = mercator.transform(actual_max_lon, actual_max_lat)
        src_transform = from_bounds(west, south, east, north, width_px, height_px)
        pixels = np.asarray(composite, dtype=np.uint8).transpose(2, 0, 1)
        if target == source_crs:
            output_pixels, output_transform, output_width, output_height = pixels, src_transform, width_px, height_px
        else:
            output_transform, output_width, output_height = calculate_default_transform(source_crs, target, width_px, height_px, west, south, east, north)
            output_pixels = np.zeros((3, output_height, output_width), dtype=np.uint8)
            for band in range(3):
                reproject(source=pixels[band], destination=output_pixels[band], src_transform=src_transform, src_crs=source_crs,
                          dst_transform=output_transform, dst_crs=target, resampling=Resampling.bilinear)
        rendered = Image.fromarray(output_pixels.transpose(1, 2, 0), "RGB")
        if out_ext in (".tif", ".tiff"):
            with rasterio.open(output_image_path, "w", driver="GTiff", width=output_width, height=output_height, count=3,
                               dtype="uint8", crs=target, transform=output_transform, compress="deflate") as dataset:
                dataset.write(output_pixels)
            wf_ext = ".tfw"
        elif out_ext in (".jpg", ".jpeg"):
            rendered.save(output_image_path, "JPEG", quality=90, optimize=True); wf_ext = ".jgw"
        elif out_ext == ".png":
            rendered.save(output_image_path, "PNG"); wf_ext = ".pgw"
        else:
            rendered.save(output_image_path, "BMP"); wf_ext = ".bpw"

        # 6. Write sidecars. GeoTIFF embeds CRS too; .prj lets ArcGIS read the
        # coordinate system alongside BMP/JPEG/PNG WorldFiles.
        wf_path = os.path.splitext(output_image_path)[0] + wf_ext
        wf_params = cls.calculate_world_file_params(output_transform)
        cls.write_world_file(wf_path, wf_params)

        # Also write universal .wld file
        universal_wld = os.path.splitext(output_image_path)[0] + ".wld"
        cls.write_world_file(universal_wld, wf_params)
        prj_path = os.path.splitext(output_image_path)[0] + ".prj"
        with open(prj_path, "w", encoding="utf-8") as prj:
            prj.write(target.to_wkt())

        return {
            "image_path": output_image_path,
            "world_file_path": wf_path,
            "universal_wld_path": universal_wld,
            "width": output_width,
            "height": output_height,
            "num_tiles_x": num_tiles_x,
            "num_tiles_y": num_tiles_y,
            "total_tiles": num_tiles_x * num_tiles_y,
            "downloaded_or_cached": len([d for d in tiles_data.values() if d]),
            "zoom": zoom,
            "format": out_ext.replace(".", ""),
            "crs": target.to_string(),
            "crs_name": target.name,
            "projection_file_path": prj_path,
            "bounds": {
                "min_lon": actual_min_lon,
                "min_lat": actual_min_lat,
                "max_lon": actual_max_lon,
                "max_lat": actual_max_lat
            },
            "world_file_params": wf_params
        }
