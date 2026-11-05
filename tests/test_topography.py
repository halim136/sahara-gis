import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from sas_planet_py.topography import TopographicEngine
from sas_planet_py.terrain import TerrainReader


def dem(grid):
    vals = [v for row in grid for v in row if v is not None]
    rows, cols = len(grid), len(grid[0])
    return {"grid": grid, "rows": rows, "cols": cols, "dx": 1/(cols-1), "dy": 1/(rows-1),
            "min_elevation": min(vals), "max_elevation": max(vals)}


class Contours(unittest.TestCase):
    def extract(self, grid, interval=10, **kwargs):
        return TopographicEngine.generate_contour_geojson((0,0,1,1), interval, dem=dem(grid), **kwargs)

    def test_planar_slope_joins_cells(self):
        data = self.extract([[0,10,20], [0,10,20], [0,10,20]], interval=5)
        paths = [f for f in data['features'] if f['properties']['elevation'] == 5]
        self.assertEqual(len(paths), 1)
        self.assertEqual(len(paths[0]['geometry']['coordinates']), 3)
        for lon, _ in paths[0]['geometry']['coordinates']:
            self.assertAlmostEqual(lon, .25)
        self.assertEqual({p[1] for p in paths[0]['geometry']['coordinates']}, {0,.5,1})

    def test_closed_hill(self):
        data = self.extract([[0,0,0],[0,20,0],[0,0,0]])
        path = data['features'][0]['geometry']['coordinates']
        self.assertEqual(path[0], path[-1])
        self.assertEqual(len(path), 5)

    def test_saddle_preserves_both_branches(self):
        data = self.extract([[20,0],[0,20]], interval=10)
        lines = [f['geometry']['coordinates'] for f in data['features'] if f['properties']['elevation'] == 10]
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(len(p) == 2 for p in lines))
        self.assertEqual({tuple(p) for line in lines for p in line}, {(0.5,1),(1,.5),(.5,0),(0,.5)})

    def test_no_lines_for_flat_sea(self):
        self.assertEqual(self.extract([[0,0],[0,0]])['features'], [])

    def test_decimal_and_negative_levels(self):
        data = self.extract([[-1,1],[-1,1]], interval=.25, above_sea_only=False)
        heights = {f['properties']['elevation'] for f in data['features']}
        self.assertTrue({-.75,-.5,0,.25,.5,.75}.issubset(heights))

    def test_no_lines_across_nodata(self):
        self.assertEqual(self.extract([[0,20],[None,20]])['features'], [])

    def test_invalid_requests(self):
        for value in (0,-1,float('nan'),float('inf'),True):
            with self.assertRaises(ValueError):
                self.extract([[0,20],[0,20]], interval=value)
        with self.assertRaises(ValueError):
            TopographicEngine.generate_contour_geojson((1,0,0,1))


class Terrain(unittest.TestCase):
    def test_hgt_endianness_north_orientation_and_missing_values(self):
        with tempfile.TemporaryDirectory() as temp, patch('sas_planet_py.terrain.CACHE', Path(temp)):
            folder = Path(temp)/'srtm'; folder.mkdir()
            raw = bytearray(struct.pack('>h',100)*1201**2)
            struct.pack_into('>h', raw, 0, 300)
            struct.pack_into('>h', raw, (1200*1201)*2, -25)
            struct.pack_into('>h', raw, (600*1201+600)*2, -32768)
            (folder/'N00E000.hgt').write_bytes(raw)
            reader = TerrainReader('srtm')
            values = reader.sample_points([(1,0),(0,0),(.5,.5),(.25,.25)])
            self.assertEqual(values,[300,-25,None,100])

    def test_tile_decoding_and_seam_interpolation(self):
        with tempfile.TemporaryDirectory() as temp, patch('sas_planet_py.terrain.CACHE', Path(temp)):
            for x in (0,1):
                for y in (0,1):
                    folder = Path(temp)/'terrarium'/'1'/str(x); folder.mkdir(parents=True,exist_ok=True)
                    h = 100 + x*20 + y*40
                    Image.new('RGB',(256,256),((h+32768)//256,(h+32768)%256,128)).save(folder/(str(y)+'.png'))
            self.assertAlmostEqual(TerrainReader(offline=True).sample_points([(0,0)],zoom=1)[0],130.5)

    def test_terrarium_nodata_is_not_interpolated_into_false_heights(self):
        with tempfile.TemporaryDirectory() as temp, patch('sas_planet_py.terrain.CACHE', Path(temp)):
            folder = Path(temp)/'terrarium'/'0'/'0'; folder.mkdir(parents=True)
            Image.new('RGB',(256,256),(0,0,0)).save(folder/'0.png')
            self.assertIsNone(TerrainReader(offline=True).sample_points([(0,0)],zoom=0)[0])

    def test_offline_reuses_coarser_cached_terrain_and_reports_real_spacing(self):
        with tempfile.TemporaryDirectory() as temp,patch('sas_planet_py.terrain.CACHE',Path(temp)),patch('urllib.request.urlopen') as network:
            folder=Path(temp)/'terrarium'/'0'/'0';folder.mkdir(parents=True)
            Image.new('RGB',(256,256),(128,100,0)).save(folder/'0.png')
            reader=TerrainReader(offline=True);self.assertAlmostEqual(reader.sample_points([(36,3)],zoom=12)[0],100)
            self.assertEqual(reader.metadata['tile_zoom'],0);self.assertEqual(reader.metadata['requested_tile_zoom'],12);self.assertTrue(reader.metadata['cached_zoom_fallback']);self.assertGreater(reader.metadata['source_pixel_size_m'],100000);network.assert_not_called()

    def test_offline_reuses_finer_cached_terrain_after_mesh_detail_change(self):
        from sas_planet_py.terrain import _pixel
        import math
        with tempfile.TemporaryDirectory() as temp,patch('sas_planet_py.terrain.CACHE',Path(temp)),patch('urllib.request.urlopen') as network:
            px,py=_pixel(36,3,13)
            for x in (math.floor(px),math.floor(px)+1):
                for y in (math.floor(py),math.floor(py)+1):
                    folder=Path(temp)/'terrarium'/'13'/str(x//256);folder.mkdir(parents=True,exist_ok=True)
                    Image.new('RGB',(256,256),(128,123,0)).save(folder/(str(y//256)+'.png'))
            reader=TerrainReader(offline=True)
            self.assertEqual(reader.sample_points([(36,3)],zoom=12),[123])
            self.assertEqual(reader.metadata['tile_zoom'],13)
            self.assertEqual(reader.metadata['requested_tile_zoom'],12)
            self.assertTrue(reader.metadata['cached_zoom_fallback']);network.assert_not_called()

    def test_offline_never_requests_network(self):
        with tempfile.TemporaryDirectory() as temp, patch('sas_planet_py.terrain.CACHE', Path(temp)), patch('urllib.request.urlopen') as network:
            with self.assertRaisesRegex(ValueError, 'not cached'):
                TerrainReader(offline=True).sample_points([(36,3)])
            network.assert_not_called()

    def test_hgt_missing_tile_does_not_fabricate_heights(self):
        with tempfile.TemporaryDirectory() as temp, patch('sas_planet_py.terrain.CACHE', Path(temp)):
            with self.assertRaisesRegex(ValueError, 'Missing SRTM'):
                TerrainReader('srtm').grid((3,36,3.1,36.1),4,4)

    def test_raster_georeferencing_uses_pixel_centers(self):
        with tempfile.TemporaryDirectory() as temp:
            model = {**dem([[10,20],[30,40]]), 'nodata_samples':0, 'source':'fixture', 'attribution':'fixture'}
            with patch.object(TopographicEngine,'generate_dem_grid',return_value=model) as generate:
                result = TopographicEngine.render_topographic_bmp((0,0,1,1),str(Path(temp)/'test.bmp'),width=2,height=2)
            self.assertEqual(generate.call_args.args[0],(.25,.25,.75,.75))
            self.assertEqual(Path(result['world_file_path']).read_text().splitlines(),['0.5000000000','0.0','0.0','-0.5000000000','0.2500000000','0.7500000000'])
            with Image.open(result['image_path']) as image:
                self.assertEqual(image.size,(2,2))


if __name__ == '__main__':
    unittest.main()
