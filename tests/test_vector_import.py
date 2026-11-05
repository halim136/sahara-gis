import binascii
import io
import math
import struct
import tempfile
import unittest
import shutil
import uuid
import zipfile
from pathlib import Path

from PIL import Image

from sas_planet_py.projections import lon_lat_to_tile
from sas_planet_py.tile_storage import FileSystemStorage
from sas_planet_py.tile_stitcher import TileStitcher
from sas_planet_py.vector_formats import parse_vector_data, parse_vector_file


def _extended80(value: float) -> bytes:
    """Encode a Python float as a 10-byte x87 Extended, as SAS.Planet stores it."""
    if value == 0:
        return (0).to_bytes(8, "little") + (0).to_bytes(2, "little")
    sign = 1 if value < 0 else 0
    value = abs(value)
    mantissa_fraction, exponent = math.frexp(value)
    mantissa = int(mantissa_fraction * (1 << 64))
    return mantissa.to_bytes(8, "little") + (((sign << 15) | (exponent - 1 + 16383))).to_bytes(2, "little")


def _sml_point(lon: float, lat: float) -> bytes:
    return _extended80(lon) + _extended80(lat) + (0).to_bytes(4, "little")


def _sml_document(descr_text: str, ring, name: str = "NI-30-XXIV.6") -> bytes:
    """Build a minimal SAS.Planet DATAPACKET .sml with one geometry row."""
    blob = b"".join(_sml_point(lon, lat) for lon, lat in ring)
    geom_hex = binascii.hexlify(blob).decode()
    descr_hex = binascii.hexlify(descr_text.encode("utf-16-le")).decode()
    return (
        '<?xml version="1.0" standalone="yes"?>'
        '<DATAPACKET Version="2.0"><METADATA><FIELDS>'
        '<FIELD attrname="id" fieldtype="i4"/>'
        '<FIELD attrname="name" fieldtype="string.uni" WIDTH="2048"/>'
        '<FIELD attrname="descr" fieldtype="bin.hex" SUBTYPE="WideText"/>'
        '<FIELD attrname="lonlatarr" fieldtype="bin.hex" SUBTYPE="Binary"/>'
        '</FIELDS><PARAMS/></METADATA><ROWDATA>'
        f'<ROW id="177" name="{name}" descr="{descr_hex}" lonlatarr="{geom_hex}"/>'
        '</ROWDATA></DATAPACKET>'
    ).encode("utf-8")


class WorkspaceTemp:
    def __enter__(self):
        self.path = Path.cwd() / 'build' / 'vector-import-tests' / uuid.uuid4().hex
        self.path.mkdir(parents=True, exist_ok=False)
        return self.path
    def __exit__(self, *_):
        shutil.rmtree(self.path, ignore_errors=True)


class VectorImportTests(unittest.TestCase):
    def test_kml_polygon_and_gpx_route(self):
        kml = '<kml xmlns="http://www.opengis.net/kml/2.2"><Placemark><name>BOU HANIFIA</name><Polygon><outerBoundaryIs><LinearRing><coordinates>-0.5,35.3,0 -0.4,35.3,0 -0.4,35.4,0 -0.5,35.3,0</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></kml>'
        imported = parse_vector_data(kml)
        self.assertEqual(imported['format'], 'kml')
        self.assertEqual(imported['marks'][0]['type'], 'polygon')
        self.assertEqual(imported['marks'][0]['name'], 'BOU HANIFIA')
        gpx = '<gpx><rte><name>route</name><rtept lat="35.3" lon="-0.5"/><rtept lat="35.4" lon="-0.4"/></rte></gpx>'
        self.assertEqual(parse_vector_data(gpx)['marks'][0]['type'], 'linestring')

    def test_kmz_and_zipped_shape_with_prj(self):
        with WorkspaceTemp() as root:
            kmz = root / 'selection.kmz'
            with zipfile.ZipFile(kmz, 'w') as archive:
                archive.writestr('doc.kml', '<kml><Placemark><name>sheet</name><Point><coordinates>-0.5,35.3,0</coordinates></Point></Placemark></kml>')
            self.assertEqual(parse_vector_file(kmz)['marks'][0]['type'], 'point')

            # A minimal point Shapefile + DBF packaged exactly as users should upload it.
            header = bytearray(100); struct.pack_into('>I', header, 0, 9994); struct.pack_into('>I', header, 24, 64); struct.pack_into('<I', header, 28, 1000); struct.pack_into('<I', header, 32, 1)
            record = struct.pack('>II', 1, 10) + struct.pack('<Idd', 1, -0.50003, 35.374983)
            dbf = bytearray(65); dbf[0] = 3; struct.pack_into('<I', dbf, 4, 1); struct.pack_into('<H', dbf, 8, 65); struct.pack_into('<H', dbf, 10, 21); dbf[32:36] = b'NAME'; dbf[43] = ord('C'); dbf[48] = 20; dbf[64] = 13
            dbf.extend(b' ' + b'BOU HANIFIA'.ljust(20)); dbf.extend(b'\x1a')
            bundle = root / 'sheets.zip'
            with zipfile.ZipFile(bundle, 'w') as archive:
                archive.writestr('sheets.shp', bytes(header) + record)
                archive.writestr('sheets.dbf', bytes(dbf))
                archive.writestr('sheets.shx', b'')
                archive.writestr('sheets.prj', 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]')
            shape = parse_vector_file(bundle)
            self.assertEqual(shape['format'], 'shapefile')
            self.assertEqual(shape['marks'][0]['name'], 'BOU HANIFIA')
            self.assertAlmostEqual(shape['marks'][0]['coords'][0], -0.50003, places=5)

    def test_sasplanet_sml_sheet_grid_keeps_only_requested_fields(self):
        with WorkspaceTemp() as root:
            descr = ('id = 177\r\nnom = BOU HANIFIA\r\ntype = NI-30-XXIV.6\r\n'
                     'n_50000 = 108\r\ncoup = 1\r\nnum = 1\r\nsit = finale\r\nLong_dec = -0.50003')
            ring = [(-0.5, 35.25), (-0.375, 35.25), (-0.375, 35.375), (-0.5, 35.375), (-0.5, 35.25)]
            sml = root / '108.sml'
            sml.write_bytes(_sml_document(descr, ring))
            result = parse_vector_file(sml)
            self.assertEqual(result['format'], 'sml')
            mark = result['marks'][0]
            self.assertEqual(mark['type'], 'polygon')
            self.assertEqual(mark['name'], 'BOU HANIFIA')  # name comes from the "nom" field
            self.assertEqual(mark['properties']['n_50000'], '108')
            # Only the six requested fields are retained; everything else is dropped.
            self.assertNotIn('sit', mark['properties'])
            self.assertNotIn('Long_dec', mark['properties'])
            self.assertEqual([k for k in ('id', 'nom', 'type', 'n_50000', 'coup', 'num')
                              if k in mark['properties']], ['id', 'nom', 'type', 'n_50000', 'coup', 'num'])
            self.assertAlmostEqual(mark['coords'][0][0], -0.5, places=9)
            self.assertAlmostEqual(mark['coords'][0][1], 35.25, places=9)

    def test_sasplanet_sml_html_table_description_and_point(self):
        with WorkspaceTemp() as root:
            descr = '<table><tr><td>id</td><td>5</td></tr><tr><td>nom</td><td>TEST</td></tr><tr><td>obs</td><td>skip</td></tr></table>'
            sml = root / 'pt.sml'
            sml.write_bytes(_sml_document(descr, [(3.0, 36.75)]))
            mark = parse_vector_file(sml)['marks'][0]
            self.assertEqual(mark['type'], 'point')
            self.assertEqual(mark['name'], 'TEST')
            self.assertEqual(mark['properties']['id'], '5')
            self.assertNotIn('obs', mark['properties'])

    def test_sasplanet_db3_sqlite_marks_keep_only_requested_fields(self):
        import sqlite3
        from shapely.geometry import Polygon
        from shapely import wkb as shapely_wkb
        with WorkspaceTemp() as root:
            db3 = root / 'grid.db3'
            ring = [(-0.5, 35.25), (-0.375, 35.25), (-0.375, 35.375), (-0.5, 35.375), (-0.5, 35.25)]
            geo_wkb = shapely_wkb.dumps(Polygon(ring))
            descr = ('id = 177\r\nnom = BOU HANIFIA\r\ntype = NI-30-XXIV.6\r\n'
                     'n_50000 = 108\r\ncoup = 1\r\nnum = 1\r\nsit = finale')
            connection = sqlite3.connect(db3)
            try:
                connection.execute('CREATE TABLE Mark (ID INTEGER PRIMARY KEY, mName TEXT, mDesc TEXT, '
                                   'mGeoType INTEGER, mGeoWKB BLOB)')
                connection.execute('INSERT INTO Mark (mName, mDesc, mGeoType, mGeoWKB) VALUES (?,?,?,?)',
                                   ('NI-30-XXIV.6', descr, 3, sqlite3.Binary(geo_wkb)))
                connection.commit()
            finally:
                connection.close()
            result = parse_vector_file(db3)
            self.assertEqual(result['format'], 'db3')
            mark = result['marks'][0]
            self.assertEqual(mark['type'], 'polygon')
            self.assertEqual(mark['name'], 'BOU HANIFIA')
            self.assertEqual(mark['properties']['n_50000'], '108')
            self.assertNotIn('sit', mark['properties'])
            self.assertEqual([k for k in ('id', 'nom', 'type', 'n_50000', 'coup', 'num')
                              if k in mark['properties']], ['id', 'nom', 'type', 'n_50000', 'coup', 'num'])
            self.assertAlmostEqual(mark['coords'][0][0], -0.5, places=9)
            self.assertAlmostEqual(mark['coords'][0][1], 35.25, places=9)


class StitchProjectionTests(unittest.TestCase):
    def test_nord_sahara_geotiff_is_reprojected(self):
        with WorkspaceTemp() as root:
            cache = root / 'cache'; bbox = (-0.50, 35.30, -0.45, 35.35); zoom = 10
            x0, y1 = lon_lat_to_tile(bbox[0], bbox[1], zoom); x1, y0 = lon_lat_to_tile(bbox[2], bbox[3], zoom)
            image = Image.new('RGB', (256, 256), (30, 120, 180)); raw = io.BytesIO(); image.save(raw, 'JPEG')
            storage = FileSystemStorage(cache)
            for x in range(min(x0, x1), max(x0, x1) + 1):
                for y in range(min(y0, y1), max(y0, y1) + 1): storage.save_tile('google_sat', zoom, x, y, raw.getvalue(), 'jpg')
            output = root / 'north_sahara.tif'
            result = TileStitcher.stitch_bbox('google_sat', bbox, zoom, str(output), cache_dir=str(cache), target_crs='EPSG:30730')
            import rasterio
            with rasterio.open(output) as dataset:
                self.assertEqual(dataset.crs.to_epsg(), 30730)
                self.assertGreater(dataset.width, 0)
            self.assertEqual(result['crs'], 'EPSG:30730')
            self.assertTrue((root / 'north_sahara.tfw').is_file())
            self.assertTrue((root / 'north_sahara.prj').is_file())


if __name__ == '__main__':
    unittest.main()
