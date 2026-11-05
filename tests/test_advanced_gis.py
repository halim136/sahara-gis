import io,json,math,sqlite3,tempfile,unittest,zipfile,uuid
from pathlib import Path
from unittest.mock import patch
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.io import MemoryFile
from pyproj import Transformer,CRS
from shapely.geometry import shape
from PIL import Image,ImageDraw
from sas_planet_py import gis_common,dem_catalog
from sas_planet_py.georeference import fit_affine,georeference
from sas_planet_py.buildings import orthogonalize,roof_proposal
from sas_planet_py.studio_analysis import watershed_grid,viewshed_grid,center
from sas_planet_py.geopackage import export_package,read_package
from sas_planet_py.arcgis_export import build_package
from sas_planet_py.map_layout import create_layout

BBOX=(3,36,3.01,36.01)

def fake_grid(self,bbox,rows,cols):
    grid=[[float(100+c*2+r) for c in range(cols)] for r in range(rows)]
    return {'grid':grid,'rows':rows,'cols':cols,'bbox':bbox,'dx':(bbox[2]-bbox[0])/(cols-1),'dy':(bbox[3]-bbox[1])/(rows-1),'nodata_samples':0,'source':'analytic plane','source_pixel_size_m':10,'attribution':'test fixture','min_elevation':100,'max_elevation':max(map(max,grid))}

class AdvancedGIS(unittest.TestCase):
 def setUp(self):
    self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.exports=self.root/'exports';self.exports.mkdir();self.dems=self.root/'dems';self.dems.mkdir()
    self.patches=[patch.object(gis_common,'EXPORTS',self.exports),patch.object(dem_catalog,'ROOT',self.dems)]
    for p in self.patches:p.start()
 def tearDown(self):
    for p in reversed(self.patches):p.stop()
    self.temp.cleanup()
 def test_gcp_residuals_rotation_and_rank(self):
    points=[{'col':c,'row':r,'x':500000+2*c+.3*r,'y':4000000+.2*c-2*r} for c,r in [(0,0),(100,0),(0,100),(100,100)]]
    model,report=fit_affine(points);self.assertLess(report['rmse'],1e-7);self.assertAlmostEqual((model*(25,30))[0],500059)
    with self.assertRaises(ValueError):fit_affine([{'col':i,'row':i,'x':i,'y':i} for i in range(3)])
 def test_registered_tiff_can_be_read_independently(self):
    image=self.root/'scan.png';Image.new('RGB',(40,30),(120,80,40)).save(image)
    points=[{'col':c,'row':r,'x':500000+2*c,'y':4000000-2*r} for c,r in [(0,0),(40,0),(0,30),(40,30)]]
    result=georeference(image,points,'EPSG:32631');path=self.exports/Path(result['files'][0]['url']).name
    with rasterio.open(path) as src:self.assertEqual(src.crs.to_epsg(),32631);self.assertEqual(src.count,4);self.assertAlmostEqual(src.transform.a,2);self.assertEqual(int(src.read(4)[15,20]),255)
 def test_native_dem_grid_sampling_nodata_and_crop(self):
    identifier=uuid.uuid4().hex;path=self.dems/(identifier+'.tif');array=np.arange(100,dtype='float32').reshape(10,10)
    with rasterio.open(path,'w',driver='GTiff',width=10,height=10,count=1,dtype='float32',crs='EPSG:4326',transform=from_bounds(*BBOX,10,10),nodata=-9999) as dst:dst.write(array,1)
    info=dem_catalog.inspect_dem(path,'Plane');self.assertEqual(info['width'],10)
    point=center(4,3,BBOX,10,10);sample=dem_catalog.sample_points(identifier,[(point[1],point[0])]);self.assertAlmostEqual(sample[0],43,places=4)
    grid=dem_catalog.read_grid(identifier,(3.0005,36.0005,3.0095,36.0095),10,10)['grid'];self.assertAlmostEqual(grid[4][3],43,places=3)
    with self.assertRaises(ValueError):dem_catalog.read_grid(identifier,(4,37,4.01,37.01),3,3)
 def test_dem_mosaic_retains_native_pixel_size_and_data(self):
    ids=[]
    for index in (0,1):
        identifier=uuid.uuid4().hex;ids.append(identifier)
        with rasterio.open(self.dems/(identifier+'.tif'),'w',driver='GTiff',width=10,height=10,count=1,dtype='float32',crs='EPSG:4326',transform=from_bounds(3+index*.01,36,3.01+index*.01,36.01,10,10),nodata=-9999) as dst:dst.write(np.full((10,10),100+index,dtype='float32'),1)
    info=dem_catalog.mosaic(ids)
    self.assertEqual(info['width'],20);self.assertEqual(info['height'],10)
    with rasterio.open(dem_catalog.dem_path(info['id'])) as src:self.assertAlmostEqual(src.res[0],.001);self.assertEqual(int(src.read(1)[5,15]),101)
 def test_projected_packages_share_metric_grid_and_wgs84_geojson(self):
    with patch('sas_planet_py.terrain.TerrainReader.grid',new=fake_grid):
      for crs in ('EPSG:32631','EPSG:30731'):
        result=build_package(BBOX,self.exports,resolution=64,hydrology=False,target_crs=crs)
        with zipfile.ZipFile(self.exports/Path(result['download_url']).name) as archive:
          with MemoryFile(archive.read('dem.tif')) as mem,mem.open() as src:
            self.assertTrue(src.crs.is_projected);self.assertGreater(src.bounds.left,400000);self.assertLess(src.transform.a,100);reference=(src.transform,src.width,src.height)
            self.assertTrue(np.isfinite(src.read(1,masked=True).mean()))
          with MemoryFile(archive.read('slope.tif')) as mem,mem.open() as src:self.assertEqual((src.transform,src.width,src.height),reference)
          features=json.loads(archive.read('contours.geojson'))['features'];self.assertTrue(all(abs(pt[0])<180 for f in features for pt in f['geometry']['coordinates']))
          self.assertIn('PROJ',archive.read('contours.prj').decode())
 def test_nord_sahara_operation_matches_known_translation(self):
    crs,_=gis_common.target_crs('EPSG:30731',BBOX);convert=Transformer.from_crs(4326,crs.to_wkt(),always_xy=True)
    from sas_planet_py.nord_sahara import wgs84_to_utm_nord_sahara
    expected=wgs84_to_utm_nord_sahara(36,3,31);x,y=convert.transform(3,36);self.assertAlmostEqual(x,expected['easting'],places=2);self.assertAlmostEqual(y,expected['northing'],places=2)
 def test_watershed_cell_conservation_and_streams(self):
    grid=[[float(10-x) for x in range(7)] for y in range(7)];point=center(3,6,BBOX,7,7)
    mask,basin,streams,stats=watershed_grid(grid,BBOX,point,1,0)
    self.assertEqual(stats['cells'],7);self.assertEqual(stats['upstream_cells']+1,stats['cells']);self.assertTrue(basin['features']);self.assertTrue(streams['features']);self.assertGreater(stats['area_m2'],0)
 def test_viewshed_flat_ridge_nodata_and_range(self):
    grid=[[0.]*9 for _ in range(9)];point=center(4,1,BBOX,9,9)
    flat=viewshed_grid(grid,BBOX,point,2,0,curvature=False);self.assertTrue(np.all(flat==1))
    for row in grid:row[4]=100
    ridge=viewshed_grid(grid,BBOX,point,2,0,curvature=False);self.assertEqual(ridge[4,7],0);self.assertEqual(ridge[4,3],1)
    grid[4][3]=None;unknown=viewshed_grid(grid,BBOX,point,2,0,curvature=False);self.assertTrue(np.isnan(unknown[4,7]))
    limited=viewshed_grid([[0.]*9 for _ in range(9)],BBOX,point,max_distance=1);self.assertEqual(int(np.isfinite(limited).sum()),1)
 def test_building_angles_and_invalid_polygon(self):
    pts=[[3,36],[3.0001,36.000001],[3.000102,36.00008],[3.000001,36.00008]]
    collection=orthogonalize(pts);feature=collection['features'][0];self.assertTrue(shape(feature['geometry']).is_valid);self.assertGreater(feature['properties']['area_m2'],50)
    projection=Transformer.from_crs(4326,32631,always_xy=True);ring=np.array([projection.transform(*p) for p in feature['geometry']['coordinates'][0][:-1]]);edges=np.roll(ring,-1,axis=0)-ring
    self.assertLess(abs(float(np.dot(edges[0],edges[1])))/(np.linalg.norm(edges[0])*np.linalg.norm(edges[1])),1e-6)
    with self.assertRaises(ValueError):orthogonalize([[3,36],[3.1,36.1],[3,36.1],[3.1,36]])
 def test_grabcut_uses_image_content(self):
    image=Image.new('RGB',(160,160),(30,90,25));ImageDraw.Draw(image).rectangle((35,40,125,120),fill=(190,180,150));path=self.root/'roof.png';image.save(path)
    result=roof_proposal(path,BBOX);geom=shape(result['features'][0]['geometry']);self.assertGreater(geom.area,0);self.assertLess(geom.area,shape({'type':'Polygon','coordinates':[[[3,36],[3.01,36],[3.01,36.01],[3,36.01],[3,36]]]}).area*.6)
 def test_geopackage_vectors_and_raster_gdal_readable(self):
    from sas_planet_py.tile_storage import FileSystemStorage
    from sas_planet_py.projections import tile_bounds
    cache=self.root/'cache';storage=FileSystemStorage(cache);buf=io.BytesIO();Image.new('RGB',(256,256),(123,65,21)).save(buf,format='PNG');storage.save_tile('google_sat',3,4,3,buf.getvalue())
    b=tile_bounds(4,3,3);bbox=[b['min_lon']+.1,b['min_lat']+.1,b['max_lon']-.1,b['max_lat']-.1]
    features={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'name':'Test building'},'geometry':{'type':'Polygon','coordinates':[[[3,36],[3.001,36],[3.001,36.001],[3,36.001],[3,36]]]}}]}
    result=export_package(features,'google_sat',bbox,[3],cache);path=self.exports/Path(result['files'][0]['url']).name
    db=sqlite3.connect(path);self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok');self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[]);db.close()
    restored=read_package(path,True,'google_sat',self.root/'restored');self.assertEqual(restored['statistics']['features'],1);self.assertEqual(restored['statistics']['imported_tiles'],1)
    with rasterio.open(path) as src:self.assertEqual(src.crs.to_epsg(),3857);self.assertEqual(src.width,256);self.assertEqual(int(src.read(1)[128,128]),123)
 def test_pdf_arabic_title_and_page_dimensions(self):
    with patch('sas_planet_py.terrain.TerrainReader.grid',new=fake_grid):
      result=create_layout({'bbox':BBOX,'resolution':64,'page':'A4','title':'خريطة اختبار','crs':'EPSG:30731','interval':25})
    raw=(self.exports/Path(result['files'][0]['url']).name).read_bytes();self.assertTrue(raw.startswith(b'%PDF'));self.assertIn(b'/MediaBox',raw);self.assertGreater(result['statistics']['scale'],1000)

if __name__=='__main__':unittest.main()
