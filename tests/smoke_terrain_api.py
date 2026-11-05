"""Integration check against a running local server and previously cached real tiles."""
import json
import math
import urllib.error
import urllib.request

BASE = 'http://localhost:3000'
def post(route, body):
    req = urllib.request.Request(BASE+route, data=json.dumps(body).encode(), headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)

bbox = [5.0,36.6,5.05,36.65]
for change in ({'interval':0}, {'bbox':[5,37,4,36]}, {'resolution':9999}, {'source':'unknown'}):
    status, data = post('/api/python/topo/contour', {'bbox':bbox,**change})
    assert status == 400 and not data['success'], (status, data)
status, data = post('/api/python/topo/import-hgt', {'name':'../N36E005.hgt','content':'AAAA'})
assert status == 400 and not data['success']
status, data = post('/api/python/topo/contour', {'bbox':bbox,'resolution':128,'interval':25,'offline':True})
assert status == 200 and data['success'], (status,data)
contours = data['contours']
assert len(contours['features']) > 0
for feature in contours['features']:
    assert feature['geometry']['type'] == 'LineString'
    for lon,lat in feature['geometry']['coordinates']:
        assert math.isfinite(lon) and math.isfinite(lat)
        assert bbox[0]-1e-9 <= lon <= bbox[2]+1e-9 and bbox[1]-1e-9 <= lat <= bbox[3]+1e-9
status, raster = post('/api/python/topo/render', {'bbox':bbox,'width':128,'height':128,'offline':True})
assert status == 200 and raster['success'], (status,raster)
with urllib.request.urlopen(BASE+raster['result']['download_url']) as response:
    assert response.read(2) == b'BM'
with urllib.request.urlopen(BASE+raster['result']['world_file_url']) as response:
    assert len(response.read().decode().splitlines()) == 6
status, profile = post('/api/python/elevation', {'coords':[[36.61,5.01],[36.64,5.04]],'samples':10,'offline':True})
assert status == 200 and profile['success'] and len(profile['profile']) == 10, (status, profile)
status, missing = post('/api/python/topo/contour', {'bbox':bbox,'source':'srtm','resolution':32})
assert status == 422 and not missing['success'], (status,missing)
print(json.dumps({'api':'passed','contour_lines':len(contours['features']), 'metadata':contours['properties'],
                  'raster':raster['result']['download_url'],'profile_samples':len(profile['profile'])},ensure_ascii=True))
