"""End-to-end GIS API checks in an isolated, relocated portable package."""
import io,json,time,urllib.request,urllib.error,zipfile
from pathlib import Path

def check(folder,base,request,run):
    python=folder/'runtime/python/python.exe';app=folder/'app';fixtures=folder/'data/gis-fixtures';fixtures.mkdir(parents=True,exist_ok=True)
    script=fixtures/'make.py'
    script.write_text('''from pathlib import Path
import numpy as np,rasterio
from rasterio.transform import from_bounds
from PIL import Image,ImageDraw
root=Path(__file__).parent
for index in (0,1):
    with rasterio.open(root/('dem'+str(index)+'.tif'),'w',driver='GTiff',width=100,height=100,count=1,dtype='float32',crs='EPSG:4326',transform=from_bounds(3+index*.01,36,3.01+index*.01,36.01,100,100),nodata=-9999) as dst:dst.write(np.fromfunction(lambda r,c:100+r+c,(100,100),dtype=float).astype('float32'),1)
image=Image.new('RGB',(160,160),(30,90,25));ImageDraw.Draw(image).rectangle((35,40,125,120),fill=(190,180,150));image.save(root/'scan.png')
''',encoding='utf8')
    run([python,script],app)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def upload(kind,path):
        req=urllib.request.Request(base+'/api/studio/upload/'+kind,data=path.read_bytes(),headers={'Content-Type':'application/octet-stream','X-File-Name':path.name})
        with opener.open(req,timeout=60) as response:return json.load(response)['result']
    def studio(operation,body):
        try:return request(base,'/api/studio/'+operation,body)['result']
        except urllib.error.HTTPError as error:raise AssertionError(operation+': '+error.read().decode('utf8')) from error
    first=upload('dem',fixtures/'dem0.tif');second=upload('dem',fixtures/'dem1.tif')
    assert first['id'].startswith('dem:')
    crop=studio('dem_crop',{'id':first['id'],'bbox':[3.002,36.002,3.008,36.008]});assert crop['width']==60 and crop['height']==60,crop
    mosaic=studio('dem_mosaic',{'ids':[first['id'],second['id']]});assert mosaic['width']>=199,mosaic
    assert len(studio('dem_list',{})['dems'])==4
    print('PASS: DEM GeoTIFF upload, native crop and mosaic APIs',flush=True)
    options={'bbox':[3.001,36.001,3.009,36.009],'source':first['id'],'offline':True,'resolution':64}
    for operation in ('watershed','viewshed'):
        result=studio(operation,{**options,'point':[3.006,36.004],'threshold_cells':5,'max_distance':10000})
        assert result['files'] and request(base,result['preview']).startswith(b'\x89PNG')
        for item in result['files']:
            content=request(base,item['url'])
            if item['name'].endswith('.geojson'):assert (content if isinstance(content,dict) else json.loads(content))['type']=='FeatureCollection'
            else:assert len(content)>100
    scene=studio('scene3d',{**options,'resolution':65,'buildings':[{'name':'Test building','type':'polygon','coords':[[[3.004,36.004],[3.005,36.004],[3.005,36.005],[3.004,36.005],[3.004,36.004]]]}],'building_height':12})
    assert scene['metadata']['triangles']>0 and len(scene['positions'])==65*65*3
    assert len(scene['buildings'])==1 and scene['buildings'][0]['height_m']==12
    print('PASS: watershed, area viewshed and 3D terrain/building APIs',flush=True)
    arcgis=request(base,'/api/python/topo/arcgis',{**options,'target_crs':'EPSG:30731','hydrology':False})['result']
    with zipfile.ZipFile(io.BytesIO(request(base,arcgis['download_url']))) as archive:
        meta=json.loads(archive.read('metadata.json'));assert meta['crs']=='EPSG:30731' and meta['datum_operation']['accuracy_m']==44
    layout=studio('layout',{**options,'title':'خريطة طبوغرافية','crs':'EPSG:30731','page':'A3','scale':0});assert request(base,layout['files'][0]['url']).startswith(b'%PDF')
    print('PASS: projected ArcGIS and Arabic PDF APIs',flush=True)
    scan=upload('scan',fixtures/'scan.png')
    registered=studio('georeference',{'id':scan['id'],'crs':'EPSG:32631','gcps':[{'col':c,'row':r,'x':500000+c,'y':4000000-r} for c,r in [(0,0),(160,0),(0,160),(160,160)]]});assert registered['statistics']['rmse']<1e-6
    points=[[3,36],[3.0001,36.000001],[3.000102,36.00008],[3.000001,36.00008]]
    building=studio('buildings',{'points':points});assert building['statistics']['review_required']
    accepted=studio('buildings',{'method':'validate','geojson':building['geojson']});assert not accepted['statistics']['review_required']
    roof=studio('buildings',{'method':'image','id':scan['id'],'bbox':[3,36,3.0002,36.0002]});assert roof['statistics']['review_required']
    package=studio('gpkg_export',{'features':accepted['geojson']});gpkg_path=fixtures/'project.gpkg';gpkg_path.write_bytes(request(base,package['files'][0]['url']));uploaded=upload('gpkg',gpkg_path);restored=studio('gpkg_import',{'id':uploaded['id']});assert restored['statistics']['features']==1
    print('PASS: GCP registration, building drafting/GrabCut and GeoPackage APIs',flush=True)
    # New professional APIs are exercised in the relocated, isolated portable runtime.
    qa=studio('qa_dem',{**options,'vertical_datum':'unknown'});assert qa['statistics']['valid_samples']>0
    qa=studio('qa_checkpoints',{'bbox':options['bbox'],'crs':'EPSG:32631','metric_crs':'EPSG:32631','points':[{'observed_x':500003,'observed_y':4000004,'reference_x':500000,'reference_y':4000000}]*3});assert qa['statistics']['horizontal_rmse_m']==5
    topology=studio('qa_topology',{'bbox':options['bbox'],'features':accepted['geojson']['features']});assert not topology['statistics']['invalid']
    sheet={'type':'Feature','properties':{'sheet_id':'TEST ONLY','name':'Analytic test sheet','wgs84_bbox':options['bbox']},'geometry':{'type':'Polygon','coordinates':[[[3.001,36.001],[3.009,36.001],[3.009,36.009],[3.001,36.009],[3.001,36.001]]]}}
    catalog=studio('catalog_import',{'geojson':{'type':'FeatureCollection','features':[sheet]},'provenance':{'publisher':'Test fixture, not INCT','source':'Integration test'}})
    query=studio('catalog_query',{'id':catalog['id'],'bbox':options['bbox'],'search':'Analytic'});assert query['statistics']['sheets']==1
    grid=studio('sheets25k',{'bbox':options['bbox'],'datum':'nord_sahara'});assert grid['statistics']['sheets']>0
    atlas=studio('atlas',{'sheets':[sheet],**options,'resolution':64,'paper':'A3','overlap_mm':10});assert atlas['statistics']['rescaling_applied'] is False
    for file in atlas['files']:
        content=request(base,file['url']);assert isinstance(content,dict) or len(content)>100
    prints=studio('print3d',{'scene':scene,'resolution':65});assert prints['statistics']['closed_manifold']
    split=studio('print_split',{'scene':scene,'resolution':65,'longest_side_mm':300,'base_mm':4,'bed_mm':[180,180,250]});assert len(split['statistics']['pieces'])==4
    with zipfile.ZipFile(io.BytesIO(request(base,split['files'][0]['url']))) as archive:assert 'alignment_pin.stl' in archive.namelist()
    project=studio('project_save',{'name':'Portable integration','state':{'marks':[],'catalogId':catalog['id'],'settings':{'terrainSource':first['id']},'camera3D':{'camera':[1,2,3]},'analyses':[atlas]}})['project']
    studio('project_save',{'id':project['id'],'state':project['state']});assert studio('project_backups',{'id':project['id']})['backups']
    packed=studio('project_pack',{'id':project['id'],'dem_ids':[first['id']]});file=fixtures/'portable.sasgis';file.write_bytes(request(base,packed['files'][0]['url']));up=upload('project',file);restored=studio('project_import',{'id':up['id']});assert restored['statistics']['imported_dems']==1 and restored['statistics']['catalogs']==1
    assert restored['project']['state']['settings']['terrainSource']!=first['id']
    print('PASS: project backup/package/import, catalog, topology, QA, atlas, print3d and split/pins APIs',flush=True)
    queue=request(base,'/api/cache/jobs',{'source_id':'google_sat','bbox':[10,50,11,51],'zooms':[3],'paused':True})['job']
    assert queue['status']=='paused'
    coverage=request(base,'/api/cache/coverage',{'source_id':'google_sat','bbox':[10,50,11,51],'zooms':[3]});assert coverage['levels'][0]['cached']==1
    scan=studio('cache_scan',{'source_id':'google_sat','bbox':[10,50,11,51],'zooms':[3]});assert scan['statistics']['damaged']==0
    return {'professionalSuite':True,'localDemCropMosaic':True,'projectedArcGIS':True,'watershed':True,'areaViewshed':True,'terrain3D':True,'arabicA3PDF':True,'gcpRegistration':True,'buildingEditingAndGrabCut':True,'geoPackageRoundTrip':True,'persistentQueueId':queue['job_id'],'cacheCoverageAndScan':True}
