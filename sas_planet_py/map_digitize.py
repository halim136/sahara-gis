"""Semi-automatic raster->vector digitizing of scanned maps with OpenCV.

Pick a feature by colour (or a preset: water/vegetation/contours/roads); the
mask is cleaned and traced to georeferenced polygons or lines. Works on a
georeferenced GeoTIFF (uses its CRS/transform) or on a plain image plus a bbox.
"""
import math
import numpy as np
import cv2
import rasterio

MAX_DIM = 2500          # downscale very large scans for speed
MAX_FEATURES = 6000

_PRESETS = {
    # name: (lower HSV, upper HSV) in OpenCV RGB2HSV space (H 0-179)
    "water":      ((90, 40, 40), (130, 255, 255)),
    "vegetation": ((33, 30, 30), (90, 255, 255)),
    "contours":   ((5, 45, 40), (25, 255, 255)),
}


def _hex_to_hsv(hexs):
    h = str(hexs or "#1e90ff").lstrip("#")
    if len(h) != 6:
        h = "1e90ff"
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    hsv = cv2.cvtColor(np.uint8([[[r, g, b]]]), cv2.COLOR_RGB2HSV)[0][0]
    return int(hsv[0]), int(hsv[1]), int(hsv[2])


def _read_raster(path):
    """Return (rgb uint8 HxWx3, px2geo(col,row)->[lon,lat], W, H)."""
    with rasterio.open(path) as ds:
        bands = ds.read()
        crs, transform = ds.crs, ds.transform
    if bands.shape[0] >= 3:
        rgb = np.dstack([bands[0], bands[1], bands[2]]).astype(np.uint8)
    else:
        g = bands[0].astype(np.uint8)
        rgb = np.dstack([g, g, g])
    H, W = rgb.shape[:2]
    if crs is not None:
        from pyproj import Transformer
        if crs.to_epsg() == 4326:
            conv = lambda x, y: (x, y)
        else:
            conv = Transformer.from_crs(crs, 4326, always_xy=True).transform

        def px2geo(col, row):
            x, y = transform * (col, row)
            lon, lat = conv(x, y)
            return [lon, lat]
        return rgb, px2geo, W, H
    return rgb, None, W, H


def digitize(p):
    path = p["path"]
    rgb, px2geo, W, H = _read_raster(path)

    if px2geo is None:
        bbox = p.get("bbox")
        if not bbox or len(bbox) != 4:
            raise ValueError("The image is not georeferenced; georeference it first, or pass a bbox.")
        w, s, e, n = [float(v) for v in bbox]

        def px2geo(col, row):  # noqa: F811 (bbox fallback, north-up linear)
            return [w + col / max(1, W - 1) * (e - w), n - row / max(1, H - 1) * (n - s)]

    # Downscale large rasters; remember scale so coordinates map back to full pixels.
    scale = 1.0
    m = max(W, H)
    if m > MAX_DIM:
        scale = MAX_DIM / m
        rgb = cv2.resize(rgb, (max(1, int(W * scale)), max(1, int(H * scale))), interpolation=cv2.INTER_AREA)

    mode = p.get("mode", "color")
    if mode == "roads":
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        thr = int(p.get("dark_threshold", 80))
        mask = (gray < thr).astype(np.uint8) * 255
    else:
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        if mode in _PRESETS:
            lo, hi = _PRESETS[mode]
            mask = cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
        else:  # colour pick
            h0, s0, v0 = _hex_to_hsv(p.get("color"))
            tol = max(2, int(p.get("tolerance", 20)))
            lo = np.array([max(0, h0 - tol), max(25, s0 - 2 * tol), max(25, v0 - 2 * tol)], np.uint8)
            hi = np.array([min(179, h0 + tol), 255, 255], np.uint8)
            mask = cv2.inRange(hsv, lo, hi)

    # Morphological clean-up.
    k = max(1, int(p.get("clean", 2)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    geometry = p.get("geometry", "polygon")
    simplify_px = float(p.get("simplify", 2.0))
    min_px = float(p.get("min_size", 40))
    inv = 1.0 / scale

    def ring_geo(cnt):
        return [px2geo(int(pt[0][0] * inv), int(pt[0][1] * inv)) for pt in cnt]

    feats = []
    if geometry == "polygon":
        contours, _ = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            if cv2.contourArea(c) < min_px * min_px:
                continue
            approx = cv2.approxPolyDP(c, simplify_px, True)
            if len(approx) < 3:
                continue
            ring = ring_geo(approx)
            ring.append(ring[0])
            feats.append({"type": "Feature", "properties": {"source": mode},
                          "geometry": {"type": "Polygon", "coordinates": [ring]}})
            if len(feats) >= MAX_FEATURES:
                break
    else:  # line
        contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            if cv2.arcLength(c, False) < min_px:
                continue
            approx = cv2.approxPolyDP(c, simplify_px, False)
            if len(approx) < 2:
                continue
            feats.append({"type": "Feature", "properties": {"source": mode},
                          "geometry": {"type": "LineString", "coordinates": ring_geo(approx)}})
            if len(feats) >= MAX_FEATURES:
                break

    if not feats:
        raise ValueError("No features matched. Adjust the colour/tolerance or clean level.")
    return {"geojson": {"type": "FeatureCollection", "features": feats},
            "statistics": {"features": len(feats), "mode": mode, "geometry": geometry,
                           "raster_px": [W, H], "georeferenced": p.get("bbox") is None or px2geo is not None}}
