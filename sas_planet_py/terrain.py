"""Real DEM sampling: Mapzen Terrarium tiles or local SRTM HGT files.
Terrarium encoding: https://github.com/tilezen/joerd/blob/master/docs/formats.md
Local HGT: north-to-south rows of signed, big-endian int16; -32768 is NoData.
"""
import io
import math
import os
import struct
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent / "cache" / "terrain"
ATTRIBUTION = "Mapzen Terrain Tiles © Mapzen, sources: SRTM, GMTED2010, ETOPO1 and others"
ATTRIBUTION_URL = "https://github.com/tilezen/joerd/blob/master/docs/attribution.md"


def validate_bbox(bbox):
    if (not isinstance(bbox, (list, tuple)) or len(bbox) != 4
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in bbox)):
        raise ValueError("A finite numeric bbox [west, south, east, north] is required.")
    west, south, east, north = bbox
    if not (-180 <= west < east <= 180 and -85 <= south < north <= 85):
        raise ValueError("Invalid region. Use west < east, south < north within ±85° latitude.")


def _pixel(lat, lon, zoom):
    size = 256 * 2 ** zoom
    return ((lon + 180) / 360 * size - 0.5,
            (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * size - 0.5)


@lru_cache(maxsize=96)
def _read_tile(path):
    from PIL import Image
    with Image.open(path) as img:
        if img.size != (256, 256):
            raise ValueError("Invalid terrain tile dimensions.")
        return img.convert("RGB").tobytes()


def _fetch_tile(key):
    zoom, x, y, offline = key
    path = CACHE / "terrarium" / str(zoom) / str(x) / (str(y) + ".png")
    if path.exists():
        try:
            _read_tile(str(path))
            return
        except (OSError, ValueError):
            if offline:
                raise ValueError("Cached terrain tile is damaged. Reconnect to download it again.")
    if offline:
        raise ValueError("Terrain is not cached for this region. Connect once or import local SRTM HGT files.")
    url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{zoom}/{x}/{y}.png"
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            data = response.read(2_000_000)
        from PIL import Image
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            if img.size != (256, 256):
                raise ValueError("Invalid terrain tile dimensions.")
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
            tmp.write(data)
            tmp_name = tmp.name
        os.replace(tmp_name, path)
    except Exception as exc:
        raise ValueError("Cannot load real terrain data. Check the connection or import SRTM HGT files. " + str(exc)) from exc


class TerrainReader:
    def __init__(self, source="terrain", offline=False):
        if source not in ("terrain", "srtm") and not (isinstance(source,str) and source.startswith("dem:")):
            raise ValueError("Unknown elevation source.")
        self.source, self.offline = source, offline
        self.metadata = {}

    def sample_points(self, points, zoom=12):
        if self.source.startswith("dem:"):
            from .dem_catalog import sample_points
            self.metadata={"source":"Local GeoTIFF DEM","source_id":self.source,"offline":True,"attribution":"User supplied elevation raster"}
            return sample_points(self.source,points)
        if self.source == "srtm":
            return self._sample_hgt(points)
        pixels = [_pixel(lat, lon, zoom) for lat, lon in points]
        size = 256 * 2 ** zoom
        keys = set()
        for px, py in pixels:
            for x in (math.floor(px), math.floor(px) + 1):
                for y in (math.floor(py), math.floor(py) + 1):
                    keys.add((zoom, (x % size) // 256, min(size - 1, max(0, y)) // 256, self.offline))
        if len(keys) > 96:
            raise ValueError("Region needs too many terrain tiles. Select a smaller region.")
        requested_zoom=zoom
        if self.offline:
            def covered(candidate_keys):
                for level,x,y,_ in candidate_keys:
                    path=CACHE/'terrarium'/str(level)/str(x)/(str(y)+'.png')
                    if not path.is_file():return False
                    try:_read_tile(str(path))
                    except (OSError,ValueError):return False
                return True
            if not covered(keys):
                # Reuse a complete cached level after mesh/viewport changes.
                # Sampling metadata reports its actual native spacing; no network is used.
                levels=CACHE/"terrarium"
                available=[int(p.name) for p in levels.iterdir() if p.is_dir() and p.name.isdigit() and 0<=int(p.name)<=14] if levels.is_dir() else []
                # A scene at lower mesh detail must also reuse a finer cached DEM.
                for candidate in sorted(available,key=lambda level:(abs(level-zoom),-level)):
                    candidate_pixels=[_pixel(lat,lon,candidate) for lat,lon in points];candidate_size=256*2**candidate;candidate_keys=set()
                    for px,py in candidate_pixels:
                        for x in (math.floor(px),math.floor(px)+1):
                            for y in (math.floor(py),math.floor(py)+1):candidate_keys.add((candidate,(x%candidate_size)//256,min(candidate_size-1,max(0,y))//256,True))
                    if len(candidate_keys)<=96 and covered(candidate_keys):zoom=candidate;pixels=candidate_pixels;size=candidate_size;keys=candidate_keys;break
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(_fetch_tile, sorted(keys)))

        def value(x, y):
            x, y = x % size, min(size - 1, max(0, y))
            path = CACHE / "terrarium" / str(zoom) / str(x // 256) / (str(y // 256) + ".png")
            rgb = _read_tile(str(path))
            offset = ((y % 256) * 256 + x % 256) * 3
            r, g, b = rgb[offset:offset + 3]
            return r * 256 + g + b / 256 - 32768

        result = []
        for px, py in pixels:
            x, y = math.floor(px), math.floor(py)
            tx, ty = px - x, py - y
            vals = [value(x, y), value(x+1, y), value(x, y+1), value(x+1, y+1)]
            weights = [(1-tx)*(1-ty), tx*(1-ty), (1-tx)*ty, tx*ty]
            result.append(None if any(v <= -32767 and w > 1e-12 for v,w in zip(vals,weights))
                          else sum(v*w for v,w in zip(vals,weights)))
        self.metadata = {"source": "Mapzen Terrain Tiles (Terrarium)", "source_id": "terrain",
                         "attribution": ATTRIBUTION, "attribution_url": ATTRIBUTION_URL,
                         "tile_zoom": zoom, "requested_tile_zoom":requested_zoom,"cached_zoom_fallback":zoom!=requested_zoom,"offline": self.offline,
                         "source_pixel_size_m": round(156543.03392 * math.cos(math.radians(points[0][0])) / 2**zoom, 1)}
        return result

    def _sample_hgt(self, points):
        tiles, result, spacings = {}, [], []
        for lat, lon in points:
            # At a tile edge prefer the southern/western tile if only it exists.
            candidates = [(math.floor(lat), math.floor(lon))]
            if lat == math.floor(lat):
                candidates.append((math.floor(lat)-1, math.floor(lon)))
            if lon == math.floor(lon):
                candidates += [(a, b-1) for a, b in list(candidates)]
            for base_lat, base_lon in candidates:
                name = f"{'N' if base_lat >= 0 else 'S'}{abs(base_lat):02d}{'E' if base_lon >= 0 else 'W'}{abs(base_lon):03d}.hgt"
                path = CACHE / "srtm" / name
                if path.exists():
                    break
            else:
                raise ValueError(f"Missing SRTM tile {name}. Import all HGT tiles covering the region.")
            if name not in tiles:
                raw = path.read_bytes()
                side = math.isqrt(len(raw) // 2)
                if side not in (1201, 3601) or len(raw) != side*side*2:
                    raise ValueError("Invalid SRTM HGT file: " + name)
                tiles[name] = raw, side
                spacings.append(111320 / (side - 1))
            raw, side = tiles[name]
            px, py = (lon-base_lon)*(side-1), (base_lat+1-lat)*(side-1)
            x, y = min(side-2, max(0, math.floor(px))), min(side-2, max(0, math.floor(py)))
            tx, ty = px-x, py-y
            vals = [struct.unpack_from('>h', raw, ((y+dy)*side+x+dx)*2)[0]
                    for dx, dy in ((0,0),(1,0),(0,1),(1,1))]
            weights = [(1-tx)*(1-ty), tx*(1-ty), (1-tx)*ty, tx*ty]
            result.append(None if any(v == -32768 and w > 1e-12 for v, w in zip(vals, weights))
                          else sum(v*w for v, w in zip(vals, weights)))
        self.metadata = {"source": "Local SRTM HGT", "source_id": "srtm", "files": sorted(tiles),
                         "source_pixel_size_m": round(max(spacings), 1), "offline": True,
                         "attribution": "SRTM / NASA / USGS — local user supplied data"}
        return result

    def grid(self, bbox, rows, cols):
        validate_bbox(bbox)
        if any(not isinstance(n, int) or isinstance(n, bool) or not 2 <= n <= 1024 for n in (rows, cols)):
            raise ValueError("Grid dimensions must be integers between 2 and 1024.")
        if self.source.startswith("dem:"):
            from .dem_catalog import read_grid
            return read_grid(self.source,bbox,rows,cols)
        west, south, east, north = bbox
        zoom = min(14, max(0, math.ceil(math.log2(360*cols / (256*(east-west))))))
        # Bound downloads independently of requested raster size and region aspect ratio.
        while zoom > 0:
            x0, y0 = _pixel(north, west, zoom)
            x1, y1 = _pixel(south, east, zoom)
            if (int(x1//256)-int(x0//256)+2)*(int(y1//256)-int(y0//256)+2) <= 64:
                break
            zoom -= 1
        dx, dy = (east-west)/(cols-1), (north-south)/(rows-1)
        values = self.sample_points([(north-r*dy, west+c*dx) for r in range(rows) for c in range(cols)], zoom)
        valid = [v for v in values if v is not None]
        if not valid:
            raise ValueError("No valid elevations in this region.")
        return {"bbox": bbox, "rows": rows, "cols": cols, "dx": dx, "dy": dy,
                "grid": [values[r*cols:(r+1)*cols] for r in range(rows)],
                "min_elevation": min(valid), "max_elevation": max(valid),
                "sample_spacing_m": round(max(dx*111320*math.cos(math.radians((south+north)/2)), dy*110574), 1),
                "nodata_samples": len(values)-len(valid), **self.metadata}
