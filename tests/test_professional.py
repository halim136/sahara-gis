import io,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from shapely.geometry import box,mapping
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A1
from pypdf import PdfReader
from sas_planet_py import projects,sheet_catalog,pro_quality,gis_common
from sas_planet_py.atlas import tile_pdf
from sas_planet_py.print_split import split_print
from test_printing_sheets import scene
class Professional(unittest.TestCase):
 def setUp(self):
    self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.export=self.root/'exports';self.export.mkdir()
    self.patches=[patch.object(gis_common,'EXPORTS',self.export),patch.object(projects,'EXPORTS',self.export),patch.object(projects,'ROOT',self.root/'projects'),patch.object(sheet_catalog,'ROOT',self.root/'catalogs')]
    for p in self.patches:p.start()
 def tearDown(self):
    for p in reversed(self.patches):p.stop()
    self.temp.cleanup()
 def catalog(self):
    return {'geojson':{'type':'FeatureCollection','features':[{'type':'Feature','properties':{'sheet_id':'TEST-01','name':'Fixture only','edition':'A','year':2020},'geometry':mapping(box(3,36,3.125,36.125))}]},'provenance':{'publisher':'Test fixture, not INCT','source':'Analytic polygon'}}
 def test_catalog_preserves_source_and_editions(self):
    d=sheet_catalog.import_catalog(self.catalog());q=sheet_catalog.query_catalog({'id':d['id'],'bbox':[3,36,4,37],'search':'fixture','edition':'A'})
    self.assertEqual(q['statistics']['sheets'],1);self.assertFalse(q['metadata']['independently_verified']);self.assertEqual(q['geojson']['features'][0]['properties']['sheet_id'],'TEST-01')
    self.assertFalse(sheet_catalog.query_catalog({'id':d['id'],'bbox':[3,36,4,37],'edition':'B'})['geojson']['features'])
 def test_catalog_rejects_duplicates_and_missing_provenance(self):
    p=self.catalog();p['geojson']['features']*=2
    with self.assertRaisesRegex(ValueError,'Duplicate'):sheet_catalog.import_catalog(p)
    p=self.catalog();p['provenance']={}
    with self.assertRaisesRegex(ValueError,'Publisher'):sheet_catalog.import_catalog(p)
 def test_project_roundtrip_assets_camera_and_backups(self):
    asset=self.export/'analysis.json';asset.write_text('{"test":true}')
    p=projects.save_project({'name':'Test','state':{'marks':[],'camera3D':{'camera':[1,2,3]},'analyses':[{'url':'/exports/analysis.json'}]}})['project']
    projects.save_project({'id':p['id'],'name':'Test 2','state':p['state']});self.assertEqual(len(projects.backups({'id':p['id']})['backups']),1)
    result=projects.pack_project({'id':p['id']});archive=self.export/Path(result['files'][0]['url']).name;asset.unlink()
    imported=projects.unpack_project(archive)['project'];url=imported['state']['analyses'][0]['url'];self.assertTrue((self.export/url.removeprefix('/exports/')).is_file());self.assertEqual(imported['state']['camera3D']['camera'],[1,2,3]);self.assertNotEqual(imported['id'],p['id'])
 def test_project_rejects_zip_escape_and_bad_checksum(self):
    file=self.root/'bad.sasgis'
    with zipfile.ZipFile(file,'w') as z:z.writestr('assets/../evil','x')
    with self.assertRaisesRegex(ValueError,'Unsafe'):projects.unpack_project(file)
    with zipfile.ZipFile(file,'w') as z:
      z.writestr('project.json',json.dumps({'schema':'sasgis-project','version':1,'name':'test','state':{}}));z.writestr('checksums.json',json.dumps({'assets/x':'bad'}));z.writestr('assets/x','x')
    with self.assertRaisesRegex(ValueError,'checksum'):projects.unpack_project(file)
 def test_checkpoints_known_345_and_vertical_policy(self):
    p={'crs':'EPSG:32631','metric_crs':'EPSG:32631','bbox':[3,36,4,37],'points':[{'observed_x':500003,'observed_y':4000004,'reference_x':500000,'reference_y':4000000,'observed_z':12,'reference_z':10}]*3}
    d=pro_quality.checkpoints(p)['statistics'];self.assertAlmostEqual(d['horizontal_rmse_m'],5);self.assertIsNone(d['vertical_rmse_m'])
    p.update(observed_vertical='EGM96',reference_vertical='EGM96');self.assertEqual(pro_quality.checkpoints(p)['statistics']['vertical_rmse_m'],2)
 def test_dem_quality_reports_nodata_and_oversampling(self):
    grid=[[100.]*8 for _ in range(8)];grid[0][0]=None;grid[4][4]=500
    with patch.object(pro_quality,'analysis_grid',return_value={'grid':grid,'source':'Fixture','source_pixel_size_m':1000}):
      d=pro_quality.dem_quality({'bbox':[3,36,3.001,36.001]})['statistics']
    self.assertEqual(d['nodata_samples'],1);self.assertTrue(d['oversampled']);self.assertGreater(d['possible_spikes'],0)
 def test_topology_detects_overlap_and_coverage_gap(self):
    features=[{'type':'Feature','geometry':mapping(box(3,36,3.01,36.01))},{'type':'Feature','geometry':mapping(box(3.005,36,3.015,36.01))}]
    d=pro_quality.topology({'features':features,'bbox':[3,36,3.02,36.02],'check_gaps':True})['statistics']
    self.assertEqual(len(d['overlaps']),1);self.assertGreater(d['candidate_gap_area_m2'],0)
    with self.assertRaises(ValueError):pro_quality.validate_edit({'mark':{'type':'polygon','coords':[[3,36],[3.01,36.01],[3,36.01],[3.01,36],[3,36]]}})
 def test_atlas_tiles_preserve_scale_and_cover_page(self):
    source=self.root/'source.pdf';c=canvas.Canvas(str(source),pagesize=A1);c.line(0,0,100,100);c.save();target=self.root/'tiles.pdf'
    tiles=tile_pdf(source,target,'A4',10);self.assertGreater(len(tiles),1);self.assertEqual(len(PdfReader(target).pages),len(tiles));self.assertTrue(all(t['content_scale']==1 for t in tiles))
    self.assertAlmostEqual(max(t['source_window_points'][2] for t in tiles),A1[0],places=2);self.assertAlmostEqual(max(t['source_window_points'][3] for t in tiles),A1[1],places=2);self.assertEqual(min(t['source_window_points'][1] for t in tiles),0)
 def test_split_pieces_fit_and_are_closed(self):
    result=split_print({'scene':scene(),'resolution':65,'longest_side_mm':300,'base_mm':4,'bed_mm':[180,180,250]});report=result['statistics']
    self.assertEqual(len(report['pieces']),4);self.assertEqual(report['pins_to_print'],8)
    with zipfile.ZipFile(self.export/Path(result['files'][0]['url']).name) as archive:
      for piece in report['pieces']:
        self.assertTrue(all(v<=b for v,b in zip(piece['dimensions_mm'],[180,180,250])));self.assertGreater(piece['volume_mm3'],0);self.assertIn(piece['name']+'.stl',archive.namelist())
        with zipfile.ZipFile(io.BytesIO(archive.read(piece['name']+'.3mf'))) as model:self.assertIsNone(model.testzip())
 def test_pin_walls_require_sufficient_base(self):
    with self.assertRaisesRegex(ValueError,'base thickness'):split_print({'scene':scene(),'resolution':65,'longest_side_mm':300,'base_mm':2,'bed_mm':[180,180,250]})
