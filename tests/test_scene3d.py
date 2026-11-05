import math,unittest
from unittest.mock import patch
import numpy as np
from pyproj import Transformer
from sas_planet_py.scene3d import build_scene
BBOX=[3,36,3.01,36.01]
def plane(self,bbox,rows,cols):
    grid=[[100.+r+c for c in range(cols)] for r in range(rows)]
    return {'grid':grid,'rows':rows,'cols':cols,'bbox':bbox,'source':'test plane','source_pixel_size_m':10,'attribution':'Analytic fixture'}
class Scene3D(unittest.TestCase):
 def test_metric_mesh_extent_uv_winding_and_elevation(self):
    with patch('sas_planet_py.terrain.TerrainReader.grid',new=plane):scene=build_scene(BBOX,resolution=65)
    self.assertEqual(len(scene['positions']),65*65*3);self.assertEqual(scene['metadata']['triangles'],64*64*2)
    self.assertEqual(scene['uv'][:2],[0.,1.]);self.assertEqual(scene['uv'][-2:],[1.,0.])
    vertices=np.array(scene['positions']).reshape(-1,3);self.assertTrue(np.isfinite(vertices).all())
    triangle=scene['indices'][:3];normal=np.cross(vertices[triangle[1]]-vertices[triangle[0]],vertices[triangle[2]]-vertices[triangle[0]]);self.assertGreater(normal[1],0)
    self.assertAlmostEqual(float(vertices[:,1].max())*scene['metadata']['span_m'],128,places=5)
    self.assertEqual(scene['metadata']['crs'],'EPSG:32631')
 def test_nodata_is_a_hole_and_not_fabricated_flat_elevation(self):
    def missing(self,bbox,rows,cols):
        data=plane(self,bbox,rows,cols);data['grid'][32][32]=None;return data
    with patch('sas_planet_py.terrain.TerrainReader.grid',new=missing):scene=build_scene(BBOX,resolution=65)
    self.assertNotIn(32*65+32,scene['indices']);self.assertEqual(scene['metadata']['nodata_samples'],1)
    self.assertLess(scene['metadata']['triangles'],64*64*2)
 def test_buildings_ground_samples_height_and_exclusions(self):
    ring=[[3.004,36.004],[3.005,36.004],[3.005,36.005],[3.004,36.005],[3.004,36.004]]
    marks=[{'type':'polygon','coords':[ring],'name':'Building','height_m':12},{'type':'polygon','coords':[[[5,37],[5.001,37],[5.001,37.001],[5,37]]]}]
    with patch('sas_planet_py.terrain.TerrainReader.grid',new=plane):scene=build_scene(BBOX,resolution=65,buildings=marks)
    self.assertEqual(len(scene['buildings']),1);b=scene['buildings'][0];self.assertEqual(b['height_m'],12)
    self.assertAlmostEqual(b['height']*scene['metadata']['span_m'],12);self.assertEqual(len(b['ground'][0]),5)
    self.assertEqual(scene['metadata']['skipped_buildings'],1);self.assertTrue(all(h<=b['base'] for h in b['ground'][0]))
 def test_invalid_regions_and_unavailable_terrain(self):
    for bbox in ([0,0,1,1],[3,36,3.00000001,36.00000001]):
        with self.assertRaises(ValueError):build_scene(bbox,resolution=65)
    with self.assertRaises(ValueError):build_scene(BBOX,resolution=64)
    with self.assertRaises(ValueError):build_scene(BBOX,building_height=0)
    def empty(self,bbox,rows,cols):return {'grid':[[None]*cols for _ in range(rows)],'source':'empty'}
    with patch('sas_planet_py.terrain.TerrainReader.grid',new=empty),self.assertRaises(ValueError):build_scene(BBOX,resolution=65)
if __name__=='__main__':unittest.main()
