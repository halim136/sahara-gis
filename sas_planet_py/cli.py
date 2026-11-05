"""
SAS.Planet Python CLI Tool
Command line interface for batch mapping, downloading, stitching, conversions,
topographic contours, spatial analysis, and UTM Nord Sahara.
"""

import sys
import json
import argparse
from typing import List

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
from .projections import lon_lat_to_tile, tile_bounds, lat_lon_to_utm, to_dms, MercatorProjection
from .nord_sahara import wgs84_to_utm_nord_sahara, utm_nord_sahara_to_wgs84
from .geocalc import vincenty_distance, polygon_area_sq_meters, path_length
from .topography import TopographicEngine
from .analysis import SpatialAnalysis
from .map_sources import list_sources
from .tile_downloader import TileDownloader
from .tile_stitcher import TileStitcher


def parse_bbox(s: str) -> List[float]:
    parts = [float(x.strip()) for x in s.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must be 4 comma-separated numbers: min_lon,min_lat,max_lon,max_lat")
    return parts


def main():
    parser = argparse.ArgumentParser(description="SAS.Planet Python GIS Utility")
    subparsers = parser.add_subparsers(dest="command")

    # Command: sources
    subparsers.add_parser("sources", help="List available map sources and overlays")

    # Command: convert-coord
    conv_p = subparsers.add_parser("convert-coord", help="Convert coordinates across systems")
    conv_p.add_argument("--lat", type=float, required=True, help="Latitude")
    conv_p.add_argument("--lon", type=float, required=True, help="Longitude")
    conv_p.add_argument("--zoom", type=int, default=15, help="Zoom level (default: 15)")

    # Command: utm-nord-sahara
    ns_p = subparsers.add_parser("utm-nord-sahara", help="Convert WGS84 to UTM Nord Sahara (Voirol / Clarke 1880)")
    ns_p.add_argument("--lat", type=float, required=True, help="WGS84 Latitude")
    ns_p.add_argument("--lon", type=float, required=True, help="WGS84 Longitude")
    ns_p.add_argument("--zone", type=int, default=0, help="Force zone (29, 30, 31, 32 or 0 for auto)")

    # Command: contour
    ct_p = subparsers.add_parser("contour", help="Generate topographic contour lines")
    ct_p.add_argument("--bbox", type=str, required=True, help="min_lon,min_lat,max_lon,max_lat")
    ct_p.add_argument("--interval", type=float, default=20.0, help="Contour interval in meters (e.g. 10, 20, 50)")

    # Command: slope
    sl_p = subparsers.add_parser("slope", help="Analyze slope and aspect at coordinate")
    sl_p.add_argument("--lat", type=float, required=True)
    sl_p.add_argument("--lon", type=float, required=True)

    # Command: buffer
    bf_p = subparsers.add_parser("buffer", help="Generate geodesic buffer around coordinate")
    bf_p.add_argument("--lat", type=float, required=True)
    bf_p.add_argument("--lon", type=float, required=True)
    bf_p.add_argument("--radius", type=float, default=1000.0, help="Buffer radius in meters")

    # Command: measure
    meas_p = subparsers.add_parser("measure", help="Measure path or polygon")
    meas_p.add_argument("--coords", type=str, required=True, help="Points: lat,lon;lat,lon;...")

    # Command: download
    dl_p = subparsers.add_parser("download", help="Batch download map tiles")
    dl_p.add_argument("--source", type=str, default="google_sat", help="Source ID (e.g. google_sat, esri_satellite)")
    dl_p.add_argument("--bbox", type=str, required=True, help="Bounding box: min_lon,min_lat,max_lon,max_lat")
    dl_p.add_argument("--zooms", type=str, required=True, help="Comma-separated zoom levels (e.g. 14,15,16)")
    dl_p.add_argument("--storage", type=str, default="gm1", choices=["gm1", "sas", "osm", "tms", "mbtiles"])
    dl_p.add_argument("--output", type=str, default=None, help="Output folder (default: cache_gmt)")
    dl_p.add_argument("--concurrency", type=int, default=4, help="Download threads")

    # Command: stitch
    st_p = subparsers.add_parser("stitch", help="Stitch tiles into single georeferenced raster")
    st_p.add_argument("--source", type=str, default="google_sat")
    st_p.add_argument("--bbox", type=str, required=True)
    st_p.add_argument("--zoom", type=int, required=True)
    st_p.add_argument("--output", type=str, required=True, help="Output image file (.bmp)")

    args = parser.parse_args()

    if args.command == "sources":
        sources = list_sources()
        print(json.dumps(sources, indent=2, ensure_ascii=False))

    elif args.command == "convert-coord":
        lat, lon, z = args.lat, args.lon, args.zoom
        tx, ty = lon_lat_to_tile(lon, lat, z)
        bounds = tile_bounds(tx, ty, z)
        utm = lat_lon_to_utm(lat, lon)
        nord_sahara = wgs84_to_utm_nord_sahara(lat, lon)
        mx, my = MercatorProjection.forward(lon, lat)
        res = {
            "input": {"lat": lat, "lon": lon, "zoom": z},
            "tile": {"x": tx, "y": ty, "zoom": z},
            "tile_bounds": bounds,
            "dms": {"lat": to_dms(lat, True), "lon": to_dms(lon, False)},
            "utm_wgs84": utm,
            "utm_nord_sahara": nord_sahara,
            "spherical_mercator_meters": {"x": round(mx, 2), "y": round(my, 2)}
        }
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "utm-nord-sahara":
        res = wgs84_to_utm_nord_sahara(args.lat, args.lon, force_zone=args.zone)
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "contour":
        bbox = parse_bbox(args.bbox)
        res = TopographicEngine.generate_contour_geojson(tuple(bbox), interval=args.interval)
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "slope":
        res = SpatialAnalysis.analyze_slope_at(args.lat, args.lon)
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "buffer":
        ring = SpatialAnalysis.point_buffer(args.lat, args.lon, args.radius)
        geojson = {
            "type": "Feature",
            "properties": {"radius_m": args.radius, "center": [args.lat, args.lon]},
            "geometry": {"type": "Polygon", "coordinates": [ring]}
        }
        print(json.dumps(geojson, indent=2, ensure_ascii=False))

    elif args.command == "measure":
        raw_pairs = [p.strip().split(",") for p in args.coords.split(";") if p.strip()]
        pts = [(float(p[0]), float(p[1])) for p in raw_pairs if len(p) == 2]
        length_m = path_length(pts)
        area_m2 = polygon_area_sq_meters(pts) if len(pts) >= 3 else 0.0
        res = {
            "num_points": len(pts),
            "path_length_meters": length_m,
            "path_length_km": round(length_m / 1000.0, 3),
            "polygon_area_sq_meters": area_m2,
            "polygon_area_hectares": round(area_m2 / 10000.0, 4),
            "polygon_area_sq_km": round(area_m2 / 1000000.0, 6)
        }
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "download":
        bbox = parse_bbox(args.bbox)
        zooms = [int(z.strip()) for z in args.zooms.split(",")]
        downloader = TileDownloader()
        job = downloader.create_job(
            "cli_job",
            args.source,
            tuple(bbox),
            zooms,
            args.storage,
            args.output,
            args.concurrency
        )
        print(f"Starting batch download for {job.total_tiles} tiles...")

        def on_progress(p):
            sys.stdout.write(f"\rProgress: {p['progress_percent']}% ({p['downloaded'] + p['cached']}/{p['total_tiles']}) | Speed: {p['speed_kb_s']} KB/s")
            sys.stdout.flush()

        downloader.run_job(job, on_progress)
        print("\nDownload finished:", json.dumps(job.to_dict(), indent=2))

    elif args.command == "stitch":
        bbox = parse_bbox(args.bbox)
        res = TileStitcher.stitch_bbox(args.source, tuple(bbox), args.zoom, args.output)
        print("Stitching completed successfully:")
        print(json.dumps(res, indent=2, ensure_ascii=False))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
