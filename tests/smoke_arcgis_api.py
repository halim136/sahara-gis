"""Integration check: running server, cached real terrain, ArcGIS package."""
import io,json,urllib.request,urllib.error,zipfile
from PIL import Image
BASE='http://localhost:3000'
def post(body):
    req=urllib.request.Request(BASE+'/api/python/topo/arcgis',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=90) as response:return response.status,json.load(response)
    except urllib.error.HTTPError as error:return error.code,json.load(error)
body={'bbox':[5,36.6,5.05,36.65],'resolution':128,'interval':25,'offline':True}
for change in ({'resolution':2048},{'azimuth':361},{'z_factor':0},{'hydrology':'true'},{'bbox':[5,36,4,37]}):
    status,data=post({**body,**change});assert status==400 and not data['success'],(status,data)
status,data=post(body);assert status==200 and data['success'],(status,data)
result=data['result']
with urllib.request.urlopen(BASE+result['download_url']) as response:raw=response.read()
with zipfile.ZipFile(io.BytesIO(raw)) as archive:
    files=archive.namelist();assert 'contours.shp' in files and 'slope.tif' in files and 'load_in_arcgis.py' in files
    for filename in [f for f in files if f.endswith('.tif')]:
        with Image.open(io.BytesIO(archive.read(filename))) as image:
            assert image.size==(128,128),filename
            assert image.tag_v2[34735][0]==1
            assert tuple(image.tag_v2[33922])==(0,0,0,5,36.65,0)
    metadata=json.loads(archive.read('metadata.json'));assert metadata['statistics']['aspect']['mean'] is None
with urllib.request.urlopen(BASE+result['previews']['slope']) as response:assert response.read(8)==b'\x89PNG\r\n\x1a\n'
print(json.dumps({'status':'passed','package':result['download_url'],'contours':result['metadata']['contour_lines'],'size_mb':result['size_mb'],'source':result['metadata']['source']}))
