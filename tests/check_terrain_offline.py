"""Targeted offline terrain APIs using isolated synthetic fixtures; no personal cache."""
import base64,json,math,os,shutil,sys,time,urllib.error
from pathlib import Path
from PIL import Image
from smoke_portable import start_server,request,closed
ROOT=Path(__file__).resolve().parents[1]
RELEASE=ROOT/'releases/SASPlanet-Portable-win-x64-v1.5'
if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf8')
def link(source,target):
    try:os.link(source,target)
    except OSError:shutil.copy2(source,target)
def main():
    folder=ROOT/'build/offline-terrain-review'/('اختبار معزول '+str(time.time_ns()));folder.mkdir(parents=True)
    for part in ('node','python'):shutil.copytree(RELEASE/'runtime'/part,folder/'runtime'/part,copy_function=link,ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(RELEASE/'app',folder/'app',copy_function=link,ignore=shutil.ignore_patterns('cache','exports','__pycache__'))
    (folder/'data').mkdir()
    bbox=[3.001,36.001,3.041,36.041]
    zoom=14;size=2**zoom
    def tile(lon,lat):return (lon+180)/360*size,(1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*size
    x0,y0=tile(bbox[0],bbox[3]);x1,y1=tile(bbox[2],bbox[1])
    for x in range(math.floor(x0)-1,math.floor(x1)+2):
        for y in range(math.floor(y0)-1,math.floor(y1)+2):
            target=folder/'app/cache/terrain/terrarium/14'/str(x)/(str(y)+'.png');target.parent.mkdir(parents=True,exist_ok=True)
            Image.new('RGB',(256,256),(128,100,0)).save(target)
            image=folder/'cache_gmt/sat/z14'/str(y)/(str(x)+'.png');image.parent.mkdir(parents=True,exist_ok=True)
            Image.new('RGB',(256,256),'#dec58f').save(image)
    settings={'sas:settings:v1':json.dumps({'language':'ar','theme':'classic','rememberView':True,'terrainSource':'terrain'}),'sas:last-view:v1':json.dumps({'lat':36.021,'lon':3.021,'zoom':14}),'sas_offline_mode':'true'}
    (folder/'data/settings.json').write_text(json.dumps(settings),'utf8')
    process,base=start_server(folder);succeeded=False
    try:
        payload={'bbox':bbox,'source':'terrain','offline':True,'resolution':65}
        ready=request(base,'/api/studio/terrain_prepare',payload)['result']
        assert ready['ready'] and ready['metadata']['nodata_samples']==0
        assert abs(ready['metadata']['min_elevation_m']-100)<1e-6
        scene=request(base,'/api/studio/scene3d',{**payload,'resolution':129})['result']
        assert len(scene['positions'])==129*129*3 and abs(scene['metadata']['min_elevation_m']-100)<1e-6
        for changed in ({'bbox':[6,39,6.01,39.01]},{'resolution':True}):
            try:request(base,'/api/studio/terrain_prepare',{**payload,**changed});raise AssertionError('Invalid/missing elevations accepted')
            except urllib.error.HTTPError as error:assert error.code==422
        raw=b'\x00\xc8'*(1201*1201)
        assert request(base,'/api/python/topo/import-hgt',{'name':'N36E003.hgt','content':base64.b64encode(raw).decode()})['success']
        local=request(base,'/api/studio/scene3d',{**payload,'source':'srtm'})['result']
        assert abs(local['metadata']['min_elevation_m']-200)<1e-6
        report={'syntheticFixtures':True,'offlinePrepare':True,'finerCachedTerrainReuse':True,'offlineScene':True,'missingDataRejected':True,'invalidRequestRejected':True,'srtmImportAndScene':True,'base':base,'folder':str(folder),'serverPid':process.pid}
        destination=ROOT/'build/offline-terrain-review';(destination/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
        succeeded=True
        print(json.dumps(report,ensure_ascii=False),flush=True)
    finally:
        if '--serve' not in sys.argv or not succeeded:
            process.terminate();process.communicate(timeout=10);assert closed(int(base.rsplit(':',1)[1]))
if __name__=='__main__':main()
