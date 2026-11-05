"""Algeria 1:25,000 working sheet grid: 7'30 x 7'30.
Dimensions: JORADP 66/2020 pp.6–7. Generated IDs are NOT INCT inventory names.
Datum and origin are explicit; older map-series layouts may differ.
"""
import json,math
from pathlib import Path
from functools import lru_cache
import numpy as np
from pyproj import Transformer,CRS
from shapely.geometry import shape,Polygon,mapping,box
from shapely.prepared import prep
from .terrain import validate_bbox
from .gis_common import output_file,download
from .nord_sahara import PARAMETERS
STEP=.125
SOURCES={'dimensions':'https://www.joradp.dz/FTP/jo-francais/2020/F2020066.pdf','boundary':'https://www.naturalearthdata.com/'}

@lru_cache(maxsize=1)
def algeria():return shape(json.loads((Path(__file__).parent/'data/algeria_boundary.geojson').read_text(encoding='utf8'))['geometry'])

def grid_crs(datum):
    if datum=='wgs84':return CRS.from_epsg(4326),'WGS84'
    if datum!='nord_sahara':raise ValueError('Select WGS84 or Nord Sahara 1959.')
    return CRS.from_proj4('+proj=longlat +a='+str(PARAMETERS['a'])+' +rf='+str(PARAMETERS['rf'])+' +towgs84='+','.join(map(str,PARAMETERS['towgs84']))+' +no_defs'),'Nord Sahara 1959 / geographic, EPSG:1253 to WGS84'

def angular_label(value,latitude=False):
    seconds=round(abs(value)*3600);degree,rem=divmod(seconds,3600);minute,second=divmod(rem,60);hemisphere=('N' if value>=0 else 'S') if latitude else ('E' if value>=0 else 'W')
    return hemisphere+str(degree).zfill(2 if latitude else 3)+str(minute).zfill(2)+str(second).zfill(2)

def cell_polygon(ix,iy,to_wgs):
    w,s=ix*STEP,iy*STEP;e,n=w+STEP,s+STEP
    # Densify borders so the datum-transformed geographic sheet is retained.
    corners=[(w,s),(e,s),(e,n),(w,n),(w,s)];ring=[]
    for a,b in zip(corners,corners[1:]):
        for t in (0,.25,.5,.75):ring.append(to_wgs.transform(a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])))
    ring.append(ring[0]);return Polygon(ring)

def sheet_grid(bbox,datum='nord_sahara',export=False):
    validate_bbox(bbox)
    if not isinstance(export,bool):raise ValueError('Export must be boolean.')
    crs,label=grid_crs(datum);to_grid=Transformer.from_crs(4326,crs,always_xy=True);to_wgs=Transformer.from_crs(crs,4326,always_xy=True)
    country=algeria();viewport=box(*bbox);overlap=country.intersection(viewport)
    metadata={'scale':25000,'sheet_size_arcseconds':[450,450],'sheet_size_degrees':[STEP,STEP],'grid_datum':label,'origin':'Greenwich longitude 0°, latitude 0°','official_inventory':False,'source_dimensions':SOURCES['dimensions'],'coverage_filter':'Approximate Natural Earth Algeria boundary; full sheet polygons are retained. This does not indicate publication/availability.','naming':'Generated coordinate identifiers, not official INCT sheet names/numbers.'}
    collection={'type':'FeatureCollection','features':[],'properties':metadata}
    if overlap.is_empty:return {'geojson':collection,'statistics':{**metadata,'sheets':0},'overview':False,'files':[]}
    w,s,e,n=overlap.bounds
    samples=[to_grid.transform(x,y) for x in np.linspace(w,e,9) for y in (s,n)]+[to_grid.transform(x,y) for y in np.linspace(s,n,9) for x in (w,e)]
    west,south=min(x for x,y in samples),min(y for x,y in samples);east,north=max(x for x,y in samples),max(y for x,y in samples)
    ix0,iy0=math.floor(west/STEP),math.floor(south/STEP);ix1,iy1=math.ceil(east/STEP)-1,math.ceil(north/STEP)-1
    if (ix1-ix0+1)*(iy1-iy0+1)>3500:
        return {'geojson':{'type':'FeatureCollection','features':[{'type':'Feature','properties':{'name':'Algeria — zoom in for 1:25,000 sheets','overview':True},'geometry':mapping(country)}]},'overview':True,'statistics':{**metadata,'sheets':0},'files':[]}
    prepared=prep(country)
    for iy in range(iy1,iy0-1,-1):
        for ix in range(ix0,ix1+1):
            polygon=cell_polygon(ix,iy,to_wgs)
            if not prepared.intersects(polygon) or not viewport.intersects(polygon):continue
            lon,lat=ix*STEP,iy*STEP;identifier='DZ25-'+angular_label(lat,True)+'-'+angular_label(lon)+'-'+('NS59' if datum=='nord_sahara' else 'W84')
            props={'sheet_id':identifier,'label':identifier,'scale':25000,'grid_datum':datum,'grid_bounds':[lon,lat,lon+STEP,lat+STEP],'wgs84_bbox':list(polygon.bounds),'official_inventory':False,'source_dimensions':SOURCES['dimensions']}
            collection['features'].append({'type':'Feature','id':identifier,'properties':props,'geometry':mapping(polygon)})
    files=[]
    if export and collection['features']:
        path=output_file('algeria_25000_grid','.geojson');path.write_text(json.dumps(collection,ensure_ascii=False),encoding='utf8');files.append({'name':'1:25,000 sheet grid GeoJSON','url':download(path)})
    return {'geojson':collection,'statistics':{**metadata,'sheets':len(collection['features'])},'overview':False,'files':files}
