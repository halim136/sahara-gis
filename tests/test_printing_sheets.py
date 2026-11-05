import io,json,struct,tempfile,unittest,zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
import numpy as np
from sas_planet_py.scene3d import build_scene
from sas_planet_py.print3d import make_solid,stl_bytes,three_mf_bytes
from sas_planet_py.map_sheets import sheet_grid,grid_crs
from sas_planet_py.map_layout import create_layout
from sas_planet_py import gis_common
from pyproj import Transformer
from shapely.geometry import shape
BBOX=[3,36,3.01,36.01]
def terrain(self,bbox,rows,cols):
    grid=[[float(100+r+c) for c in range(cols)] for r in range(rows)]
    return {'grid':grid,'rows':rows,'cols':cols,'bbox':bbox,'dx':(bbox[2]-bbox[0])/(cols-1),'dy':(bbox[3]-bbox[1])/(rows-1),'min_elevation':100,'max_elevation':100+rows+cols-2,'nodata_samples':0,'source':'test plane','source_pixel_size_m':10,'attribution':'Analytic test fixture'}
def scene():
    with patch('sas_planet_py.terrain.TerrainReader.grid',new=terrain):return build_scene(BBOX,resolution=65)
class Printer(unittest.TestCase):
 def test_solid_has_mm_dimensions_positive_volume_and_manifold_edges(self):
    vertices,faces,report=make_solid(scene(),resolution=65,longest_side_mm=150,base_mm=4)
    self.assertAlmostEqual(max(report['dimensions_mm'][:2]),150,places=4);self.assertTrue(report['closed_manifold']);self.assertGreater(report['volume_mm3'],150*100*4)
    # Independent directed-edge incidence using Python tuples, rather than exporter NumPy implementation.
    from collections import Counter
    edges=Counter()
    for a,b,c in faces:
        for edge in ((a,b),(b,c),(c,a)):edges[tuple(map(int,edge))]+=1
    self.assertTrue(all(edges[(b,a)]==count==1 for (a,b),count in edges.items()))
    self.assertEqual(float(vertices[:,2].min()),0)
 def test_stl_record_count_and_3mf_geometry_units_match(self):
    vertices,faces,report=make_solid(scene(),resolution=65)
    raw=stl_bytes(vertices,faces);self.assertEqual(struct.unpack_from('<I',raw,80)[0],len(faces));self.assertEqual(len(raw),84+50*len(faces))
    with zipfile.ZipFile(io.BytesIO(three_mf_bytes(vertices,faces))) as archive:
        self.assertEqual(archive.testzip(),None);root=ET.fromstring(archive.read('3D/3dmodel.model'));self.assertEqual(root.attrib['unit'],'millimeter');ns={'m':'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'};self.assertEqual(len(root.findall('.//m:triangle',ns)),len(faces));points=root.findall('.//m:vertex',ns);self.assertEqual(len(points),len(vertices));self.assertAlmostEqual(max(float(p.attrib['x']) for p in points),report['dimensions_mm'][0],places=4)
 def test_building_is_unioned_into_same_closed_heightfield(self):
    data=scene();data['buildings']=[{'rings':[[[-.1,-.1],[.1,-.1],[.1,.1],[-.1,.1],[-.1,-.1]]],'base':.2,'height':.15}]
    a,faces,with_building=make_solid(data,resolution=65);b,_,without=make_solid(data,resolution=65,include_buildings=False)
    self.assertEqual(with_building['represented_buildings'],1);self.assertGreater(with_building['volume_mm3'],without['volume_mm3']);self.assertTrue(with_building['closed_manifold'])
 def test_exact_scale_and_printer_limits_and_missing_dem(self):
    data=scene();v,f,r=make_solid(data,resolution=65,scale_denominator=25000)
    self.assertAlmostEqual(r['horizontal_scale_denominator'],25000);self.assertLess(max(r['dimensions_mm'][:2]),50)
    with self.assertRaisesRegex(ValueError,'exceeds'):make_solid(data,resolution=65,longest_side_mm=300)
    self.assertFalse(make_solid(data,resolution=65,longest_side_mm=300,allow_oversize=True)[2]['fits_printer'])
    data['elevations'][32]=None
    with self.assertRaisesRegex(ValueError,'missing elevations'):make_solid(data,resolution=65)
class Sheets(unittest.TestCase):
 def test_angular_dimensions_are_exact_and_ids_unique(self):
    result=sheet_grid([3.01,36.51,3.24,36.74],'wgs84');features=result['geojson']['features'];self.assertEqual(len(features),4)
    ids=set()
    for feature in features:
        b=feature['properties']['grid_bounds'];self.assertAlmostEqual((b[2]-b[0])*3600,450);self.assertAlmostEqual((b[3]-b[1])*3600,450);self.assertFalse(feature['properties']['official_inventory']);ids.add(feature['id'])
    self.assertEqual(len(ids),4)
 def test_nord_sahara_grid_is_transformed_and_neighbor_edges_match(self):
    features=sheet_grid([3.001,36.501,3.249,36.749],'nord_sahara')['geojson']['features'];self.assertGreaterEqual(len(features),4)
    crs,_=grid_crs('nord_sahara');to_grid=Transformer.from_crs(4326,crs,always_xy=True)
    for feature in features:
        x,y=feature['geometry']['coordinates'][0][0];gx,gy=to_grid.transform(x,y);west,south,*_=feature['properties']['grid_bounds'];self.assertAlmostEqual(gx,west,places=6);self.assertAlmostEqual(gy,south,places=6)
        self.assertGreater(abs(x-west)+abs(y-south),.0001)
    pair=next((a,b) for a in features for b in features if a['properties']['grid_bounds'][2:3]==b['properties']['grid_bounds'][0:1] and a['properties']['grid_bounds'][1]==b['properties']['grid_bounds'][1]);self.assertAlmostEqual(shape(pair[0]['geometry']).intersection(shape(pair[1]['geometry'])).area,0,places=12)
 def test_outside_algeria_and_country_overview(self):
    self.assertEqual(sheet_grid([30,29,31,30])['statistics']['sheets'],0);self.assertTrue(sheet_grid([-10,18,13,38])['overview'])
    self.assertTrue(sheet_grid([-180,-85,180,85])['overview'])
 def test_full_sheet_pdf_preserves_25000_scale_on_a1(self):
    selected=sheet_grid([3.01,36.51,3.02,36.52],'wgs84')['geojson']['features'][0]
    with tempfile.TemporaryDirectory() as temp,patch.object(gis_common,'EXPORTS',Path(temp)),patch('sas_planet_py.terrain.TerrainReader.grid',new=terrain):
        result=create_layout({'bbox':selected['properties']['wgs84_bbox'],'source':'srtm','offline':True,'resolution':64,'page':'A1','landscape':False,'scale':25000,'crs':'utm_wgs84_auto','title':selected['id'],'sheet':selected})
        self.assertEqual(result['statistics']['scale'],25000);self.assertEqual(result['statistics']['page'],'A1');self.assertTrue((Path(temp)/Path(result['files'][0]['url']).name).read_bytes().startswith(b'%PDF'))
if __name__=='__main__':unittest.main()
