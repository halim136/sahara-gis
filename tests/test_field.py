import io,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from PIL import Image
from shapely.geometry import Polygon,LineString,mapping
from sas_planet_py import field_tracks as tracks,field_planning as planning,field_raster as rasters,gis_common
from sas_planet_py.vector_formats import parse_vector_data,export_vector_data
GPX='<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1"><trk><name>A &amp; B</name><trkseg><trkpt lat="36" lon="3"><ele>100</ele><time>2026-11-01T10:00:00Z</time></trkpt><trkpt lat="36" lon="3.001"><ele>110</ele><time>2026-11-01T10:01:00Z</time></trkpt></trkseg><trkseg><trkpt lat="36.1" lon="3.1"><ele>300</ele><time>2026-11-01T11:00:00Z</time></trkpt><trkpt lat="36.1" lon="3.101"><ele>295</ele><time>2026-11-01T11:01:00Z</time></trkpt></trkseg></trk></gpx>'
class Field(unittest.TestCase):
 def setUp(self):
    self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.patch=patch.object(gis_common,'EXPORTS',self.root);self.patch.start();self.patch2=patch.object(rasters,'EXPORTS',self.root);self.patch2.start()
 def tearDown(self):self.patch2.stop();self.patch.stop();self.tmp.cleanup()
 def track(self):return parse_vector_data(GPX)['marks'][0]
 def test_gpx_roundtrip_preserves_time_height_segments_and_escaped_names(self):
    mark=self.track();out=export_vector_data([mark],'gpx');restored=parse_vector_data(out)['marks'][0];self.assertEqual(restored['name'],'A & B');self.assertEqual(restored['trackSegments'],mark['trackSegments']);self.assertEqual(len(restored['trackSegments']),2)
 def test_route_and_waypoint_gpx_are_not_lost(self):
    marks=tracks.parse_gpx('<gpx><wpt lat="36" lon="3"><name>P</name><ele>50</ele></wpt><rte><name>R</name><rtept lat="36" lon="3"/><rtept lat="36" lon="3.01"/></rte></gpx>')['marks']
    self.assertEqual([m['gpxKind'] for m in marks],['wpt','rte']);self.assertEqual(tracks.parse_gpx(tracks.export_gpx(marks))['marks'][0]['trackSegments'][0][0]['ele'],50)
 def test_analysis_does_not_bridge_gaps_or_count_gap_time_and_height(self):
    d=tracks.analysis(self.track())['statistics'];self.assertTrue(175<d['distance_m']<190);self.assertEqual(d['duration_s'],120);self.assertEqual(d['ascent_m'],10);self.assertEqual(d['descent_m'],5)
 def test_invalid_timing_does_not_invent_speed(self):
    mark=self.track();mark['trackSegments'][0][1]['time']=mark['trackSegments'][0][0]['time'];d=tracks.analysis(mark);self.assertEqual(d['statistics']['invalid_time_intervals'],1);self.assertIsNone(d['profile'][1]['speed_kmh'])
 def test_generic_geometry_edit_drops_stale_gpx_coordinates(self):
    mark=self.track();mark['coords'][0]=[4,37];self.assertEqual(tracks.segments_of(mark)[0][0]['lon'],4);self.assertNotIn('time',tracks.segments_of(mark)[0][0])
 def test_clean_splits_jumps_without_deleting_samples(self):
    mark=self.track();mark['trackSegments'][0][1]['time']='2026-11-01T10:00:01Z';d=tracks.operate({'mark':mark,'action':'clean','max_speed_kmh':20});self.assertEqual(d['statistics']['segments_after'],3);self.assertEqual(len(d['marks'][0]['coords']),4)
 def test_split_and_merge_preserve_segment_metadata(self):
    mark=self.track();d=tracks.operate({'mark':mark,'action':'split','index':1})['marks'];self.assertEqual(len(d),2);self.assertEqual(d[0]['trackSegments'][0][-1]['time'],'2026-11-01T10:01:00Z');merged=tracks.operate({'action':'merge','mark':d[0],'marks':d})['marks'][0];self.assertGreaterEqual(len(merged['trackSegments']),2)
 def test_csv_nord_sahara_forward_inverse_and_bad_rows(self):
    d=planning.batch_coordinates({'csv':'id,x,y\nP,3.05,36.75\nBAD,abc,36\n','target_crs':'EPSG:30731'});self.assertEqual(d['statistics']['converted'],1);self.assertEqual(d['statistics']['failed'],1);self.assertIn('44 m',d['statistics']['nord_sahara_operation'])
    import csv
    rows=list(csv.DictReader((self.root/Path(d['files'][0]['url']).name).read_text('utf-8-sig').splitlines()));r=rows[0];d=planning.batch_coordinates({'csv':'x,y\n'+r['output_x']+','+r['output_y'],'source_crs':'EPSG:30731','target_crs':'EPSG:4326'});row=d['preview'][0];self.assertAlmostEqual(float(row['output_x']),3.05,places=6);self.assertAlmostEqual(float(row['output_y']),36.75,places=6)
 def test_nord_sahara_csv_keeps_outside_area_as_failed_rows(self):
    result=planning.batch_coordinates({'csv':'x,y\n2,49','target_crs':'EPSG:30731'});self.assertEqual(result['statistics']['failed'],1);self.assertEqual(result['statistics']['converted'],0)
 def test_metric_grid_spacing_and_density_limit(self):
    d=planning.metric_grid({'bbox':[3,36,3.03,36.03],'crs':'EPSG:32631','step_m':1000});self.assertGreater(len(d['geojson']['features']),1)
    from pyproj import Transformer
    convert=Transformer.from_crs(4326,32631,always_xy=True)
    for f in d['geojson']['features']:
      point=convert.transform(*f['geometry']['coordinates'][12]);self.assertAlmostEqual(point[0 if f['properties']['axis']=='E' else 1],f['properties']['value_m'],places=5)
    with self.assertRaisesRegex(ValueError,'Zoom'):planning.metric_grid({'bbox':[0,30,10,38],'step_m':1000})
 def roads(self,oneway=None):
    return {'type':'FeatureCollection','features':[{'type':'Feature','properties':{'oneway':oneway} if oneway else {},'geometry':{'type':'LineString','coordinates':[[3,36],[3.01,36],[3.01,36.01]]}}]}
 def test_route_snaps_inside_edges_and_uses_connected_network(self):
    d=planning.route({'roads':self.roads(),'start':[3.002,36],'end':[3.01,36.008],'mode':'walk'});self.assertTrue(1550<d['statistics']['distance_m']<1650);self.assertLess(d['statistics']['start_snap_m'],1);self.assertAlmostEqual(d['marks'][0]['coords'][0][0],3.002,places=6)
 def test_routing_honors_oneway_and_rejects_disconnected_endpoints(self):
    with self.assertRaisesRegex(ValueError,'No connected'):planning.route({'roads':self.roads('yes'),'start':[3.01,36.008],'end':[3.002,36],'mode':'car'})
    d=planning.route({'roads':self.roads('yes'),'start':[3.01,36.008],'end':[3.002,36],'mode':'walk'});self.assertGreater(d['statistics']['distance_m'],0)
    with self.assertRaisesRegex(ValueError,'too far'):planning.route({'roads':self.roads(),'start':[4,37],'end':[4.01,37],'mode':'walk'})
 def test_coverage_excludes_holes_and_does_not_plan_transit(self):
    polygon=Polygon([(3,36),(3.01,36),(3.01,36.01),(3,36.01)],holes=[[(3.004,36.004),(3.006,36.004),(3.006,36.006),(3.004,36.006)]])
    result=planning.coverage({'geometry':mapping(polygon),'spacing_m':50,'angle_deg':20});mark=result['marks'][0];self.assertFalse(result['statistics']['connections_planned']);self.assertGreater(len(mark['trackSegments']),10)
    for seg in mark['trackSegments']:
      line=LineString([(p['lon'],p['lat']) for p in seg]);self.assertTrue(polygon.buffer(1e-8).covers(line))
 def raster(self):
    path=self.root/'fixture.tif';data=np.zeros((4,48,64),dtype='uint8');data[0]=220;data[1]=130;data[2]=60;data[3]=255;data[3,:,0]=0
    with rasterio.open(path,'w',driver='GTiff',height=48,width=64,count=4,dtype='uint8',crs=4326,transform=from_bounds(3,36,3.01,36.01,64,48)) as dst:dst.write(data)
    return path
 def test_local_raster_display_is_warped_and_original_is_retained(self):
    d=rasters.raster_import(self.raster(),'Fixture');layer=d['layer'];self.assertEqual(d['statistics']['display_crs'],'EPSG:3857');self.assertTrue(rasters.local_export(layer['original']).exists())
    with Image.open(rasters.local_export(layer['url'])) as im:self.assertEqual(im.mode,'RGBA');self.assertLessEqual(max(im.size),2048);self.assertLess(np.array(im)[:,:,3].min(),255)
 def test_garmin_tiles_have_geographic_bounds_and_pixel_limits(self):
    layer=rasters.raster_import(self.raster(),'Fixture')['layer'];d=rasters.field_package({'layer':layer,'format':'kmz','marks':[self.track()]})
    import xml.etree.ElementTree as ET
    with zipfile.ZipFile(self.root/Path(d['files'][0]['url']).name) as z:
      self.assertIn('tracks.gpx',z.namelist());root=ET.fromstring(z.read('doc.kml'));ns={'k':'http://www.opengis.net/kml/2.2'};self.assertAlmostEqual(float(root.find('.//k:west',ns).text),3,places=5)
      for name in z.namelist():
        if name.endswith('.jpg'):
          with Image.open(io.BytesIO(z.read(name))) as im:self.assertLessEqual(max(im.size),1024)
 def test_photo_without_gps_requires_manual_location(self):
    path=self.root/'photo.jpg';Image.new('RGB',(20,20),'red').save(path);d=rasters.photo_import(path,'Test');self.assertIsNone(d['lat']);self.assertIsNone(d['lon']);self.assertTrue(rasters.local_export(d['url']).exists())
 def test_export_path_traversal_is_rejected(self):
    with self.assertRaises(ValueError):rasters.local_export('/exports/../../README.md')
