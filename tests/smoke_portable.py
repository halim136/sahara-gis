"""Verify the shipped Windows ZIP, with no installed Node/Python on PATH.
Run on Windows: python tests/smoke_portable.py
All generated test data stays in build/portable-smoke, never the release.
"""
import array
import io
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

if hasattr(sys.stdout, 'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'releases' / 'SAS.Planet-Portable-Windows-x64-v1.5.zip'
DEST = ROOT / 'build' / 'portable-smoke' / ('نسخة محمولة مع مسافات ' + str(time.time_ns()))
ENV = dict(os.environ, PATH=str(Path(os.environ['WINDIR'])/'System32'),
           PYTHONHOME='Z:/not-installed', PYTHONPATH='Z:/not-installed',
           NODE_PATH='Z:/not-installed', NODE_OPTIONS='--invalid-host-option')
FLAGS = subprocess.CREATE_NO_WINDOW
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def run(args, cwd, env=ENV):
    result = subprocess.run([str(a) for a in args], cwd=cwd, env=env,
                            creationflags=FLAGS, capture_output=True, timeout=120)
    output = result.stdout.decode('utf-8', errors='replace')
    error = result.stderr.decode('utf-8', errors='replace')
    assert result.returncode == 0, (result.returncode, output, error)
    return output + error


def request(base, route, body=None, headers=None):
    raw = None if body is None else json.dumps(body).encode('utf-8')
    req = urllib.request.Request(base+route, data=raw,
          headers={'Content-Type':'application/json', **(headers or {})})
    with OPENER.open(req, timeout=90) as response:
        data=response.read()
        return json.loads(data) if 'json' in response.headers.get('Content-Type','') else data


def closed(port):
    with socket.socket() as s:
        s.settimeout(.5)
        return s.connect_ex(('127.0.0.1',port)) != 0


def start_server(folder):
    ready=folder/'data'/'integration-session.json'
    if ready.exists(): ready.unlink()
    env=dict(ENV, NODE_ENV='production', HOST='127.0.0.1', PORT='0', SAS_PORTABLE='1',
             SAS_PYTHON=str(folder/'runtime'/'python'/'python.exe'), SAS_READY_FILE=str(ready),
             SAS_INSTANCE_ID='relocated-integration', PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    for key in ('NODE_OPTIONS','NODE_PATH','PYTHONHOME','PYTHONPATH'):env.pop(key,None)
    process=subprocess.Popen([str(folder/'runtime'/'node'/'node.exe'),str(folder/'app'/'server.mjs')],
               cwd=folder/'app', env=env, creationflags=FLAGS, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    for _ in range(400):
        if ready.exists():return process,json.loads(ready.read_text('utf-8'))['url'].rstrip('/')
        if process.poll() is not None:raise AssertionError(process.communicate())
        time.sleep(.1)
    process.kill()
    raise AssertionError('Bundled server readiness timeout')


def main():
    with zipfile.ZipFile(ARCHIVE) as archive:
        names=archive.namelist()
        assert not any('/.env' in n or '__pycache__' in n for n in names)
        assert all(n.endswith('/') or not n.startswith('SASPlanet-Portable-v1.5/app/dist/') or n.startswith(('SASPlanet-Portable-v1.5/app/dist/assets/','SASPlanet-Portable-v1.5/app/dist/fonts/')) or n=='SASPlanet-Portable-v1.5/app/dist/index.html' for n in names), 'Unexpected file in UI build'
        assert not any(n.startswith(('SASPlanet-Portable-v1.5/data/','SASPlanet-Portable-v1.5/app/cache/',
                                    'SASPlanet-Portable-v1.5/app/public/exports/','SASPlanet-Portable-v1.5/cache_gmt/')) and not n.endswith('/') for n in names)
        archive.extractall(DEST)
    folder=DEST/'SASPlanet-Portable-v1.5'
    exe=folder/'Sahara GIS.exe' if (folder/'Sahara GIS.exe').exists() else folder/'SAS.Planet Portable.exe'
    run([exe,'--self-test'],folder)
    report=json.loads((folder/'data'/'self-test.json').read_text('utf-8-sig'))
    assert report['success'] and report['jobObject'],report
    assert Path(report['python']['python']).resolve()==(folder/'runtime'/'python'/'python.exe').resolve()
    assert report['health']['node'].startswith('v24.'),report
    assert not (folder/'data'/'self-test-session.json').exists()
    print('PASS: EXE launcher, embedded Python/Pillow/SQLite/SSL, isolated PATH and job cleanup',flush=True)
    output=run([folder/'runtime'/'python'/'python.exe','-m','unittest','discover','-s',folder/'source'/'tests','-v'],folder/'app')
    assert re.search(r'Ran (?:5[2-9]|[6-9]\d|\d{3,}) tests',output) and '\nOK' in output,output
    print('PASS: all map cache, terrain, hydrology and ArcGIS tests with embedded Python',flush=True)
    process,base=start_server(folder)
    state={'sas:settings:v1':json.dumps({'language':'ar','theme':'classic','coordinateSystem':'utm_nord_sahara','nordSaharaZone':31}),
           'sas:last-view:v1':json.dumps({'lat':36.75,'lon':3.05,'zoom':12}),
           'sas:saved-views:v1':json.dumps([{'name':'بجاية'}],ensure_ascii=False)}
    try:
        html=request(base,'/').decode('utf-8')
        assert 'fonts.googleapis.com' not in html and 'unpkg.com/leaflet' not in html
        assets=re.findall(r'(?:src|href)="(/assets/[^\"]+)"',html)
        assert len(request(base,'/fonts/NotoSansArabic.ttf'))>10000
        assert len(assets)>=2
        for asset in assets:assert len(request(base,asset))>100
        assert request(base,'/api/portable/state')['portable']
        assert request(base,'/api/portable/state',state)['success']
        assert request(base,'/api/portable/state')['state']==state
        try:
            request(base,'/api/python/run',{'code':'print(1)'},{'Origin':'https://example.com'})
            raise AssertionError('Cross-origin request accepted')
        except urllib.error.HTTPError as error:assert error.code==403
        reference=json.loads((folder/'source/tests/fixtures/nord_sahara_reference.json').read_text())['points'][0]
        converted=request(base,'/api/python/nord-sahara/convert',{'lat':reference['lat'],'lon':reference['lon'],'zone':31})
        assert converted['success'] and converted['data']['epsg']==30731,converted
        assert abs(converted['data']['easting']-reference['easting'])<.02
        inverse=request(base,'/api/python/nord-sahara/inverse',{'easting':converted['data']['easting'],'northing':converted['data']['northing'],'zone':31})
        assert inverse['success'] and abs(inverse['data']['wgs84_lat']-reference['lat'])<.000002,inverse
        print('PASS: Nord Sahara EPSG:30731 forward/inverse API and saved coordinate preferences',flush=True)
        # Round-trip browser tile persistence, native copied GM1 tiles, and batch reuse.
        import base64
        code="import io,base64;from PIL import Image;s=io.BytesIO();Image.new('RGB',(256,256),(20,90,150)).save(s,'PNG');print(base64.b64encode(s.getvalue()).decode())"
        encoded=run([folder/'runtime'/'python'/'python.exe','-c',code],folder/'app').strip()
        image=base64.b64decode(encoded)
        assert request(base,'/api/cache/tile',{'source':'google_sat','z':3,'x':4,'y':2,'content':encoded})['success']
        assert (folder/'cache_gmt'/'sat'/'z3'/'2'/'4.png').read_bytes()==image
        assert request(base,'/api/maps/tile?source=google_sat&z=3&x=4&y=2&offline=1')==image
        imported=folder/'cache_gmt'/'ArcGIS.Imagery'/'z3'/'2'/'4.png'
        imported.parent.mkdir(parents=True,exist_ok=True);imported.write_bytes(image)
        assert request(base,'/api/maps/tile?source=esri_satellite&z=3&x=4&y=2&offline=1')==image
        try:
            request(base,'/api/maps/tile?source=google_sat&z=3&x=5&y=2&offline=1')
            raise AssertionError('Offline cache miss accepted')
        except urllib.error.HTTPError as error:assert error.code==404
        stats=request(base,'/api/cache/stats')
        assert Path(stats['base_dir'])==folder/'cache_gmt' and stats['format']=='gm1'
        assert stats['total_tiles']==2,stats
        download=request(base,'/api/python/download-batch',{'source_id':'google_sat','bbox':[10,50,11,51],'zooms':[3]})
        for _ in range(100):
            job=request(base,'/api/python/download-status/'+download['jobId'])
            if job['status'] in ('completed','error'):break
            time.sleep(.1)
        assert job['status']=='completed' and job['cached']==1 and job['downloaded']==0,job
        print('PASS: shared cache_gmt GM1 browsing, imported SAS.Planet files and batch download reuse',flush=True)
        hgt=folder/'app'/'cache'/'terrain'/'srtm'/'N36E003.hgt'
        hgt.parent.mkdir(parents=True,exist_ok=True)
        samples=array.array('h',(100+r+c for r in range(1201) for c in range(1201)))
        if sys.byteorder=='little':samples.byteswap()
        hgt.write_bytes(samples.tobytes())
        result=request(base,'/api/python/topo/arcgis',{'bbox':[3.1,36.1,3.2,36.2],
                       'source':'srtm','offline':True,'resolution':64,'interval':25,'hydrology':True})
        assert result['success'],result
        data=request(base,result['result']['download_url'])
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            assert {'dem.tif','slope.tif','contours.shp','contours.dbf','contours.prj',
                    'flow_direction.tif','flow_accumulation.tif','metadata.json'}.issubset(package.namelist())
            meta=json.loads(package.read('metadata.json'))
            assert meta['crs']=='EPSG:4326' and meta['source']=='Local SRTM HGT',meta
        assert list((folder/'app'/'public'/'exports').glob('*.zip'))
        print('PASS: offline SRTM analysis and ArcGIS export through packaged server',flush=True)
        from advanced_portable_checks import check
        advanced=check(folder,base,request,run)
        from field_portable_checks import check as field_check
        field_checks=field_check(folder,base,request,run)
        print('PASS: all advanced GIS APIs, DEM crop/mosaic, Arabic PDF, buildings, GCP, GeoPackage and cache queue',flush=True)
    finally:
        process.terminate();process.communicate(timeout=10)
    port=int(base.rsplit(':',1)[1]);assert closed(port)
    process,base=start_server(folder)
    try:
        assert request(base,'/api/portable/state')['state']==state
        queue=request(base,'/api/cache/jobs')['jobs'];assert any(j['job_id']==advanced['persistentQueueId'] and j['status']=='paused' for j in queue)
        job=request(base,'/api/cache/jobs/'+advanced['persistentQueueId']+'/resume',{})['job']
        for _ in range(100):
            job=next(j for j in request(base,'/api/cache/jobs')['jobs'] if j['job_id']==job['job_id'])
            if job['status']=='completed':break
            time.sleep(.1)
        assert job['status']=='completed' and job['cached']==1

    finally:process.terminate();process.communicate(timeout=10)
    report['integration']={'unitTests':int(re.search(r'Ran (\d+) tests',output).group(1)),'advancedGIS':advanced,'fieldGIS':field_checks,'offlineArcGIS':True,'portableStateRestart':True,
                           'sharedGM1DiskCache':True,'localAssets':True,'crossOriginRejected':True,'pathWithoutInstalledRuntimes':True}
    report['testedArchive']=str(ARCHIVE)
    (DEST/'test-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print('PASS: portable settings survive server restart; release contains no user data',flush=True)
    print('Report: '+str(DEST/'test-report.json'),flush=True)


if __name__=='__main__':main()
