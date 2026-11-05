"""Field-feature API verification in the relocated portable, using only local fixtures."""
import io,json,urllib.request,zipfile
from pathlib import Path
def check(folder,base,request,run):
    fixtures=folder/'data/field-fixtures';fixtures.mkdir(parents=True,exist_ok=True)
    script=fixtures/'fixtures.py';script.write_text("""import sys,json
from pathlib import Path
import numpy as np,rasterio
from rasterio.transform import from_bounds
from PIL import Image
root=Path(sys.argv[1]);data=np.zeros((3,64,64),dtype='uint8');data[0]=50;data[1]=150;data[2]=100
with rasterio.open(root/'map.tif','w',driver='GTiff',height=64,width=64,count=3,dtype='uint8',crs=4326,transform=from_bounds(3,36,3.05,36.05,64,64)) as dst:dst.write(data)
exif=Image.Exif();exif[34853]={1:'N',2:(36.,1.,30.),3:'E',4:(3.,1.,30.),17:90.};Image.new('RGB',(32,32),'green').save(root/'photo.jpg',exif=exif)
""",'utf8')
    run([folder/'runtime/python/python.exe',script,fixtures],folder/'app')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def upload(kind,path):
        req=urllib.request.Request(base+'/api/studio/upload/'+kind,data=path.read_bytes(),headers={'Content-Type':'application/octet-stream','X-File-Name':path.name})
        with opener.open(req,timeout=60) as res:return json.load(res)['result']
    def studio(op,p):return request(base,'/api/studio/'+op,p)['result']
    raster=upload('raster',fixtures/'map.tif');layer=raster['layer'];assert layer['metadata']['display_crs']=='EPSG:3857';assert request(base,layer['url']).startswith(b'\x89PNG')
    photo=upload('photo',fixtures/'photo.jpg');assert abs(photo['lat']-36.025)<1e-7 and abs(photo['lon']-3.025)<1e-7 and photo['direction']==90
    parsed=studio('field_gpx',{'content':'<gpx><trk><name>Field test</name><trkseg><trkpt lon="3.001" lat="36.001"><ele>100</ele><time>2026-11-01T10:00:00Z</time></trkpt><trkpt lon="3.01" lat="36.01"><ele>120</ele><time>2026-11-01T10:10:00Z</time></trkpt></trkseg></trk></gpx>'});mark=parsed['marks'][0]
    stats=studio('field_track',{'mark':mark,'action':'analyze'});assert stats['statistics']['ascent_m']==20 and stats['statistics']['duration_s']==600
    gpx=studio('field_track',{'mark':mark,'action':'export'});restored=studio('field_gpx',{'content':request(base,gpx['files'][0]['url']).decode()});assert restored['marks'][0]['trackSegments']==mark['trackSegments']
    grid=studio('field_grid',{'bbox':[3,36,3.03,36.03],'step_m':1000,'crs':'EPSG:32631'});assert grid['statistics']['lines']>0
    csv=studio('field_coordinates',{'csv':'id,x,y\nP,3.05,36.75','target_crs':'EPSG:30731'});assert csv['statistics']['converted']==1
    coverage=studio('field_coverage',{'geometry':{'type':'Polygon','coordinates':[[[3,36],[3.01,36],[3.01,36.01],[3,36.01],[3,36]]]},'spacing_m':100});assert coverage['marks'][0]['trackSegments']
    roads={'type':'FeatureCollection','features':[{'type':'Feature','properties':{},'geometry':{'type':'LineString','coordinates':[[3,36],[3.01,36],[3.01,36.01]]}}]}
    route=studio('field_route',{'roads':roads,'start':[3.002,36],'end':[3.01,36.008]});assert route['statistics']['distance_m']>1000
    for fmt in ('kmz','zip'):
        out=studio('field_package',{'layer':layer,'marks':[mark],'format':fmt})
        with zipfile.ZipFile(io.BytesIO(request(base,out['files'][0]['url']))) as z:assert 'doc.kml' in z.namelist() and 'tracks.gpx' in z.namelist()
    project=studio('project_save',{'name':'Field integration test','state':{'marks':[mark],'field':{'layers':[layer,{'id':'photo','kind':'photo','url':photo['url'],'lat':photo['lat'],'lon':photo['lon']}],'grid':{'enabled':True,'crs':'EPSG:32631','step_m':1000}}}})['project'];packed=studio('project_pack',{'id':project['id']});file=fixtures/'field.sasgis';file.write_bytes(request(base,packed['files'][0]['url']));up=upload('project',file);imported=studio('project_import',{'id':up['id']})['project'];layers=imported['state']['field']['layers'];assert request(base,layers[0]['url']).startswith(b'\x89PNG');assert len(request(base,layers[0]['original']))>100;assert imported['state']['marks'][0]['trackSegments']==mark['trackSegments']
    print('PASS: local raster/photo EXIF, GPX segments/analysis, UTM grid, CSV, routes, coverage, KMZ/mobile ZIP and project relinking',flush=True)
    return {'localGeoTIFF':True,'photoExifGPS':True,'gpxMetadataRoundTrip':True,'metricGrid':True,'batchCoordinates':True,'offlineRouting':True,'coveragePlanning':True,'garminKMZAndMobileZip':True,'fieldProjectRoundTrip':True}
