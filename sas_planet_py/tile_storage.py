"""SAS.Planet file caches and MBTiles.
Default: cache_gmt/<NameInCache>/z<XYZ zoom>/<Y>/<X>.<ext> (GM1).
Based on original u_TileFileNameGM1.pas and u_TileFileNameSAS.pas.
"""
import os
import re
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from .map_sources import MAP_SOURCES, OVERLAYS

APP_ROOT = Path(__file__).resolve().parents[1]
_PORTABLE = os.environ.get('SAS_PORTABLE') == '1' or (APP_ROOT.parent/'runtime/python/python.exe').is_file()
DEFAULT_CACHE_DIR = Path(os.environ.get('SAS_MAP_CACHE') or
    ((APP_ROOT.parent if _PORTABLE else APP_ROOT) / 'cache_gmt'))
LEGACY_CACHE_DIR = APP_ROOT / 'cache'
IMAGE_EXTENSIONS = ('jpg', 'png', 'jpeg', 'webp', 'gif')


def cache_layer(layer):
    if not isinstance(layer, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}', layer) or layer in ('.', '..'):
        raise ValueError('Invalid map source.')
    source = MAP_SOURCES.get(layer) or OVERLAYS.get(layer) or {}
    return source.get('cache_name', layer)


def validate_tile(zoom, x, y, ext):
    if any(isinstance(v, bool) or not isinstance(v, int) for v in (zoom, x, y)) or not 0 <= zoom <= 24 or not (0 <= x < 2**zoom and 0 <= y < 2**zoom):
        raise ValueError('Invalid XYZ tile coordinates.')
    if ext not in IMAGE_EXTENSIONS:
        raise ValueError('Invalid tile image extension.')


def image_extension(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'):return 'png'
    if data.startswith(b'\xff\xd8\xff'):return 'jpg'
    if len(data)>=12 and data[:4]==b'RIFF' and data[8:12]==b'WEBP':return 'webp'
    if data[:6] in (b'GIF87a',b'GIF89a'):return 'gif'
    raise ValueError('Source did not return a supported tile image.')


class FileSystemStorage:
    def __init__(self, base_dir=None, format_type='gm1', legacy_dir=None):
        self.base_dir = os.fspath(DEFAULT_CACHE_DIR if base_dir is None else base_dir)
        self.format_type = format_type.lower()
        if self.format_type not in ('gm1', 'sas', 'osm', 'tms'):
            raise ValueError('Unknown tile cache format.')
        # Explicit/custom directories are isolated; only the default cache reads the old app/cache.
        self.legacy_dir = Path(legacy_dir) if legacy_dir is not None else (LEGACY_CACHE_DIR if base_dir is None or Path(base_dir).resolve() == DEFAULT_CACHE_DIR.resolve() else None)
        os.makedirs(self.base_dir, exist_ok=True)

    def get_tile_path(self, layer, zoom, x, y, ext='jpg'):
        validate_tile(zoom, x, y, ext)
        folder = cache_layer(layer)
        if self.format_type == 'gm1':
            parts = (folder, f'z{zoom}', str(y), f'{x}.{ext}')
        elif self.format_type == 'sas':
            # SAS numbering is one higher than XYZ; GM1 uses XYZ directly.
            parts = (folder, f'z{zoom+1}', str(x//1024), f'x{x}', str(y//1024), f'y{y}.{ext}')
        elif self.format_type == 'tms':
            parts = (folder, str(zoom), str(x), f'{(1<<zoom)-1-y}.{ext}')
        else:
            parts = (folder, str(zoom), str(x), f'{y}.{ext}')
        return os.path.join(self.base_dir, *parts)

    def save_tile(self, layer, zoom, x, y, data, ext='jpg'):
        validate_tile(zoom, x, y, ext)
        ext = image_extension(data)
        path = self.get_tile_path(layer, zoom, x, y, ext)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile(dir=os.path.dirname(path), suffix='.tmp', delete=False) as temp:
                temp.write(data)
                temp_name = temp.name
            for attempt in range(6):
                try:
                    os.replace(temp_name, path)
                    break
                except PermissionError:
                    if attempt == 5:raise
                    time.sleep(.01*(attempt+1))
        finally:
            if temp_name and os.path.exists(temp_name):os.unlink(temp_name)
        return path

    def load_tile(self, layer, zoom, x, y, ext='jpg'):
        primary = Path(self.get_tile_path(layer, zoom, x, y, ext))
        paths = [primary]
        if self.format_type == 'gm1':
            # An imported native SAS hierarchy has a distinct shape, so no XYZ ambiguity.
            paths.append(Path(self.base_dir)/cache_layer(layer)/f'z{zoom+1}'/str(x//1024)/f'x{x}'/str(y//1024)/f'y{y}.{ext}')
            if self.legacy_dir is not None:
                # Previous web builds used source IDs and zero-based z in the SAS-shaped path.
                paths.append(self.legacy_dir/layer/f'z{zoom}'/str(x//1024)/f'x{x}'/str(y//1024)/f'y{y}.{ext}')
        for path in paths:
            try:data = path.read_bytes()
            except FileNotFoundError:continue
            if data:
                try:image_extension(data)
                except ValueError:continue
                if path != primary:self.save_tile(layer, zoom, x, y, data, ext)
                return data
        return None

    def tile_exists(self, layer, zoom, x, y, ext='jpg'):
        return self.load_tile(layer, zoom, x, y, ext) is not None

    def get_stats(self):
        count = total = 0
        for root, _, files in os.walk(self.base_dir):
            for file in files:
                if Path(file).suffix.lower().lstrip('.') not in IMAGE_EXTENSIONS:continue
                p = os.path.join(root, file)
                count += 1
                total += os.path.getsize(p)
        return {'total_tiles':count, 'total_size_bytes':total, 'total_size_mb':round(total/1024**2,2),
                'base_dir':os.path.abspath(self.base_dir), 'format':'gm1' if self.format_type=='gm1' else self.format_type}


class MBTilesStorage:
    """
    MBTiles 1.3 SQLite-based single-file offline tile container.
    Standardized format widely used in mobile GIS (OruxMaps, OsmAnd, Mapbox, QGIS).
    """

    def __init__(self, db_path: str, mode: str = "r+"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS metadata (
                    name TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS tiles (
                    zoom_level INTEGER,
                    tile_column INTEGER,
                    tile_row INTEGER,
                    tile_data BLOB,
                    PRIMARY KEY (zoom_level, tile_column, tile_row)
                )
            """)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_tiles ON tiles (zoom_level, tile_column, tile_row)")

    def set_metadata(self, name: str, value: str):
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO metadata (name, value) VALUES (?, ?)",
                (name, str(value))
            )

    def get_metadata(self) -> Dict[str, str]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT name, value FROM metadata")
        return {row[0]: row[1] for row in cursor.fetchall()}

    def save_tile(self, zoom: int, x: int, y: int, data: bytes):
        """MBTiles stores tile_row in TMS format (flipped vertically)."""
        tms_y = (1 << zoom) - 1 - y
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO tiles (zoom_level, tile_column, tile_row, tile_data) VALUES (?, ?, ?, ?)",
                (zoom, x, tms_y, data)
            )

    def load_tile(self, zoom: int, x: int, y: int) -> Optional[bytes]:
        tms_y = (1 << zoom) - 1 - y
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
            (zoom, x, tms_y)
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def get_tile_count(self) -> int:
        cursor = self.conn.cursor()
        cursor.execute("SELECT count(*) FROM tiles")
        return cursor.fetchone()[0]

    def get_zooms(self) -> List[int]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT DISTINCT zoom_level FROM tiles ORDER BY zoom_level")
        return [row[0] for row in cursor.fetchall()]

    def close(self):
        self.conn.close()
