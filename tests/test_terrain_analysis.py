import io
import json
import math
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from sas_planet_py.terrain_analysis import terrain_metrics, drainage, metric_spacing
from sas_planet_py.arcgis_export import geotiff, shapefile, ascii_grid, build_package


class Derivatives(unittest.TestCase):
    def test_analytic_east_rising_plane(self):
        grid=[[c*10 for c in range(5)] for _ in range(5)]
        result=terrain_metrics(grid,10,10)
        self.assertAlmostEqual(result['slope'][2][2],45)
        self.assertAlmostEqual(result['aspect'][2][2],270)
        self.assertAlmostEqual(result['tpi'][2][2],0)
        self.assertAlmostEqual(result['roughness'][2][2],20)
        self.assertGreater(result['hillshade'][2][2],180)
        self.assertTrue(all(v is None for v in result['slope'][0]))

    def test_flat_and_south_rising_plane(self):
        flat=terrain_metrics([[20]*5 for _ in range(5)],10,10)
        self.assertEqual(flat['slope'][2][2],0)
        self.assertEqual(flat['aspect'][2][2],-1)
        self.assertEqual(flat['hillshade'][2][2],180)
        south=terrain_metrics([[r*10]*5 for r in range(5)],10,10)
        self.assertAlmostEqual(south['aspect'][2][2],0)

    def test_nodata_and_exaggeration(self):
        grid=[[c*10 for c in range(5)] for _ in range(5)]
        a=terrain_metrics(grid,10,10,z_factor=1);b=terrain_metrics(grid,10,10,z_factor=3)
        self.assertEqual(a['slope'],b['slope'])
        self.assertNotEqual(a['hillshade'][2][2],b['hillshade'][2][2])
        grid[1][1]=None
        self.assertIsNone(terrain_metrics(grid,10,10)['slope'][2][2])

    def test_metric_spacing_changes_with_latitude(self):
        dx,dy=metric_spacing((3,35,4,37),10,10)
        self.assertGreater(dx[-1],dx[0]);self.assertTrue(all(x>0 for x in dy))


class Hydrology(unittest.TestCase):
    def check_conservation(self,result,valid_cells):
        outlets=[result['flow_accumulation'][r][c]+1 for r,row in enumerate(result['flow_direction']) for c,code in enumerate(row) if code==0]
        self.assertEqual(sum(outlets),valid_cells)

    def test_depression_fill_is_separate_and_conserves_cells(self):
        grid=[[10,10,10],[10,0,10],[10,10,10]]
        result=drainage(grid,10,10)
        self.assertEqual(grid[1][1],0)
        self.assertEqual(result['filled_dem'][1][1],10)
        self.assertEqual(result['fill_depth'][1][1],10)
        self.check_conservation(result,9)

    def test_flat_surface_has_no_cycles(self):
        result=drainage([[4]*7 for _ in range(7)],10,10)
        self.check_conservation(result,49)
        self.assertGreater(max(v for row in result['flow_accumulation'] for v in row),0)

    def test_d8_east_and_nodata_boundary(self):
        grid=[[4,3,2,1],[4,3,2,1],[4,3,2,1],[4,3,2,1]]
        result=drainage(grid,10,10)
        self.assertEqual(result['flow_direction'][1][1],1)
        self.check_conservation(result,16)
        grid[1][1]=None
        result=drainage(grid,10,10)
        self.assertIsNone(result['flow_accumulation'][1][1])
        self.check_conservation(result,15)


class ArcGISFormats(unittest.TestCase):
    def test_geotiff_float_values_crs_and_pixel_registration(self):
        raw=geotiff([[1.25,None],[-20,200]],(3,35,4,36),'DEM','m')
        with Image.open(io.BytesIO(raw)) as image:
            self.assertEqual(image.mode,'F')
            self.assertEqual(list(image.getdata()),[1.25,-9999,-20,200])
            self.assertEqual(tuple(image.tag_v2[33550]),(.5,.5,0))
            self.assertEqual(tuple(image.tag_v2[33922]),(0,0,0,3,36,0))
            self.assertEqual(image.tag_v2[42113],'-9999')
            keys=image.tag_v2[34735];codes={keys[i]:keys[i+3] for i in range(4,len(keys),4)}
            self.assertEqual(codes[2048],4326);self.assertEqual(codes[1025],1)
        try:import tifffile
        except ImportError:return
        with tifffile.TiffFile(io.BytesIO(raw)) as independent:
            self.assertEqual(independent.pages[0].dtype.name,'float32')
            self.assertEqual(independent.asarray()[0,0],1.25)
            self.assertEqual(independent.geotiff_metadata['GeographicTypeGeoKey'],4326)

    def test_polylinez_shx_and_dbf(self):
        contours={'features':[{'properties':{'elevation':125,'is_index':True,'interval':25},'geometry':{'coordinates':[[3,35],[4,36],[5,35]]}}]}
        files=shapefile(contours);shp=files['contours.shp'];shx=files['contours.shx'];dbf=files['contours.dbf']
        self.assertEqual(struct.unpack_from('>i',shp,0)[0],9994)
        self.assertEqual(struct.unpack_from('>i',shp,24)[0]*2,len(shp))
        self.assertEqual(struct.unpack_from('<i',shp,32)[0],13)
        offset,words=struct.unpack_from('>2i',shx,100)
        self.assertEqual(offset,50);self.assertEqual(words*2,len(shp)-108)
        self.assertEqual(struct.unpack_from('<i',shp,108)[0],13)
        self.assertEqual(struct.unpack_from('<3i',shp,144),(1,3,0))
        self.assertEqual(struct.unpack_from('<3d',shp,220),(125,125,125))
        self.assertEqual(struct.unpack_from('<I',dbf,4)[0],1)
        self.assertIn(b'125.000',dbf)
        self.assertIn('GCS_WGS_1984',files['contours.prj'].decode())

    def test_ascii_square_grid_and_orientation(self):
        text=ascii_grid([[1,2],[3,None]],(0,0,1,1)).decode()
        self.assertIn('xllcorner 0.000000000000',text)
        self.assertTrue(text.endswith('1.0000 2.0000\n3.0000 -9999\n'))
        with self.assertRaises(ValueError):ascii_grid([[1,2],[3,4]],(0,0,1,2))

    def test_full_package_uses_one_real_dem_and_contains_products(self):
        def fake_grid(self,bbox,rows,cols):
            grid=[[100+c*2+r for c in range(cols)] for r in range(rows)]
            return {'grid':grid,'rows':rows,'cols':cols,'bbox':bbox,'dx':(bbox[2]-bbox[0])/(cols-1),'dy':(bbox[3]-bbox[1])/(rows-1),'min_elevation':100,'max_elevation':max(map(max,grid)),'nodata_samples':0,'source':'test fixture','source_pixel_size_m':30,'attribution':'fixture'}
        with tempfile.TemporaryDirectory() as temp,patch('sas_planet_py.terrain.TerrainReader.grid',new=fake_grid):
            result=build_package((3,36,3.1,36.05),temp,resolution=64,interval=25)
            path=Path(temp)/Path(result['download_url']).name
            with zipfile.ZipFile(path) as archive:
                self.assertTrue({'dem.tif','relief.tif','slope.tif','aspect.tif','flow_direction.tif','flow_accumulation.tif','contours.shp','contours.dbf','contours.shx','contours.prj','metadata.json','dem.asc','load_in_arcgis.py'}.issubset(archive.namelist()))
                meta=json.loads(archive.read('metadata.json'))
                self.assertEqual(meta['crs'],'EPSG:4326');self.assertEqual(meta['cols'],64);self.assertEqual(meta['rows'],32)
                self.assertEqual(meta['statistics']['dem']['min'],100)
                for key in result['previews']:
                    self.assertTrue((Path(temp)/Path(result['previews'][key]).parent.name/(key+'.png')).exists())


if __name__=='__main__':unittest.main()
