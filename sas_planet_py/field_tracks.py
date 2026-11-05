"""Segment-aware GPX and geodesic track operations; retain original time/elevation."""
import math,uuid,copy,statistics
import xml.etree.ElementTree as ET
from datetime import datetime
from geographiclib.geodesic import Geodesic
from .gis_common import output_file,download
def child(node,name):
    return next((e for e in node if e.tag.split('}')[-1]==name),None)
def text(node,name,default=''):
    e=child(node,name);return e.text if e is not None and e.text is not None else default
def coordinate(lon,lat):
    lon=float(lon);lat=float(lat)
    if not math.isfinite(lon+lat) or not -180<=lon<=180 or not -85<=lat<=85:raise ValueError('Invalid GPS coordinate.')
    return lon,lat
def sample(node):
    lon,lat=coordinate(node.get('lon'),node.get('lat'));p={'lon':lon,'lat':lat}
    for k in ('ele','hdop'):
        raw=text(node,k)
        if raw:
            v=float(raw)
            if not math.isfinite(v):raise ValueError('Invalid GPX elevation/HDOP.')
            p[k]=v
    if text(node,'time'):p['time']=text(node,'time')
    return p
def parse_gpx(content):
    if len(content)>32*1024**2:raise ValueError('GPX exceeds 32 MB.')
    root=ET.fromstring(content);marks=[]
    for node in root:
        kind=node.tag.split('}')[-1]
        if kind not in ('wpt','trk','rte'):continue
        if kind=='wpt':segments=[[sample(node)]]
        elif kind=='rte':segments=[[sample(p) for p in node if p.tag.split('}')[-1]=='rtept']]
        else:segments=[[sample(p) for p in seg if p.tag.split('}')[-1]=='trkpt'] for seg in node if seg.tag.split('}')[-1]=='trkseg']
        segments=[s for s in segments if s];points=[p for s in segments for p in s]
        if not points:continue
        if len(points)>100000:raise ValueError('Limit each track to 100,000 points.')
        marks.append({'id':uuid.uuid4().hex,'name':text(node,'name',kind),'description':text(node,'desc'),'type':'point' if kind=='wpt' else 'linestring','coords':[points[0]['lon'],points[0]['lat']] if kind=='wpt' else [[p['lon'],p['lat']] for p in points],'gpxKind':kind,'trackSegments':segments,'color':'#0b8a87','category':'GPS'})
    return {'format':'gpx','marks':marks}
def segments_of(mark):
    segments=mark.get('trackSegments')
    if segments:
        flat=[p for s in segments for p in s];coords=mark['coords']
        expected=[coords] if mark.get('type')=='point' else coords
        # A generic vector edit must not silently leave stale GPS geometry/times.
        if len(flat)==len(expected) and all(p['lon']==v[0] and p['lat']==v[1] for p,v in zip(flat,expected)):return copy.deepcopy(segments)
    coords=[mark['coords']] if mark.get('type')=='point' else mark['coords']
    return [[dict(zip(('lon','lat'),coordinate(v[0],v[1]))) for v in coords]]
def export_gpx(marks):
    root=ET.Element('gpx',version='1.1',creator='SAS.Planet GIS Studio',xmlns='http://www.topografix.com/GPX/1/1')
    for mark in marks:
        if mark.get('type') not in ('point','linestring','line'):continue
        segments=segments_of(mark);kind='wpt' if mark['type']=='point' else 'rte' if mark.get('gpxKind')=='rte' else 'trk'
        first=segments[0][0] if segments and segments[0] else None
        if not first:continue
        node=ET.SubElement(root,kind,**({'lat':str(first['lat']),'lon':str(first['lon'])} if kind=='wpt' else {}))
        ET.SubElement(node,'name').text=mark.get('name','GPS');ET.SubElement(node,'desc').text=mark.get('description','')
        groups=[(node,[first],'wpt')] if kind=='wpt' else [(node,[p for s in segments for p in s],'rtept')] if kind=='rte' else [(ET.SubElement(node,'trkseg'),seg,'trkpt') for seg in segments]
        for parent,points,tag in groups:
            for p in points:
                pt=parent if tag=='wpt' else ET.SubElement(parent,tag,lat=str(p['lat']),lon=str(p['lon']))
                for key in ('ele','time','hdop'):
                    if p.get(key) is not None:ET.SubElement(pt,key).text=str(p[key])
    return ET.tostring(root,encoding='unicode',xml_declaration=True)
def seconds(value):
    try:return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
    except (ValueError,TypeError,AttributeError):return None
def distance(a,b):return Geodesic.WGS84.Inverse(a['lat'],a['lon'],b['lat'],b['lon'])['s12']
def analysis(mark):
    segments=segments_of(mark);total=ascent=descent=elapsed=moving=0.;invalid_time=missing_time=0;profile=[];features=[];maximum=0.;elevations=[]
    for si,segment in enumerate(segments):
        previous=None
        for i,p in enumerate(segment):
            speed=slope=None
            if previous:
                d=distance(previous,p);total+=d
                if p.get('ele') is not None and previous.get('ele') is not None:
                    dz=p['ele']-previous['ele'];ascent+=max(0,dz);descent+=max(0,-dz);slope=100*dz/d if d>.01 else None
                ta,tb=seconds(previous.get('time')),seconds(p.get('time'))
                if ta is not None and tb is not None:
                    dt=tb-ta
                    if dt>0:
                        elapsed+=dt;speed=d/dt*3.6;maximum=max(maximum,speed)
                        if speed>=1:moving+=dt
                    else:invalid_time+=1
                else:missing_time+=1
                features.append({'type':'Feature','properties':{'slope_percent':slope,'speed_kmh':speed},'geometry':{'type':'LineString','coordinates':[[previous['lon'],previous['lat']],[p['lon'],p['lat']]]}})
            if p.get('ele') is not None:elevations.append(p['ele'])
            profile.append({**p,'distance_m':total,'segment':si,'index':i,'speed_kmh':speed,'slope_percent':slope});previous=p
    return {'statistics':{'points':len(profile),'segments':len(segments),'distance_m':total,'ascent_m':ascent,'descent_m':descent,'duration_s':elapsed,'moving_s':moving,'stopped_s':elapsed-moving,'max_speed_kmh':maximum,'average_speed_kmh':total/elapsed*3.6 if elapsed and missing_time==0 and invalid_time==0 else None,'invalid_time_intervals':invalid_time,'missing_time_intervals':missing_time,'min_elevation_m':min(elevations) if elevations else None,'max_elevation_m':max(elevations) if elevations else None,'elevation_note':'Recorded heights; noise affects ascent/descent. Segments are not bridged.'},'profile':profile,'geojson':{'type':'FeatureCollection','features':features}}
def mark_with(mark,segments,name=None):
    if not segments or not any(segments):raise ValueError('Operation removed all points.')
    return {**mark,'id':uuid.uuid4().hex,'name':name or mark.get('name','GPS'),'trackSegments':segments,'coords':[[p['lon'],p['lat']] for s in segments for p in s]}
def operate(p):
    mark=p['mark'];segments=segments_of(mark);op=p.get('action','analyze')
    if op=='analyze':return analysis(mark)
    if op=='export':
        path=output_file('gps','.gpx');path.write_text(export_gpx(p.get('marks') or [mark]),'utf8');return {'files':[{'name':'GPX','url':download(path)}]}
    if op=='split':
        index=int(p.get('index',0));flat=[v for s in segments for v in s]
        if not 1<=index<len(flat)-1:raise ValueError('Choose an interior point to split.')
        left=[];right=[];offset=0
        for seg in segments:
            if offset+len(seg)<=index:left.append(seg)
            elif offset>index:right.append(seg)
            else:
                cut=index-offset;left.append(seg[:cut+1]);right.append(seg[cut:])
            offset+=len(seg)
        return {'marks':[mark_with(mark,[s for s in left if s],mark['name']+' A'),mark_with(mark,[s for s in right if s],mark['name']+' B')]}
    if op=='merge':
        marks=p.get('marks',[])
        if not 2<=len(marks)<=100:raise ValueError('Select 2–100 tracks.')
        return {'marks':[mark_with(mark,[s for m in marks for s in segments_of(m)],'Merged tracks')]}
    if op=='clean':
        limit=float(p.get('max_speed_kmh',160))
        if not 1<=limit<=1500:raise ValueError('Invalid speed threshold.')
        # Flag time-based jumps by splitting; never silently bridge the jump.
        out=[]
        for seg in segments:
            current=[]
            for v in seg:
                if current:
                    a,b=seconds(current[-1].get('time')),seconds(v.get('time'))
                    if a is not None and b is not None and (b<=a or distance(current[-1],v)/(b-a)*3.6>limit):out.append(current);current=[]
                current.append(v)
            if current:out.append(current)
        return {'marks':[mark_with(mark,out,mark['name']+' reviewed jumps')],'statistics':{'segments_before':len(segments),'segments_after':len(out),'points_deleted':0}}
    if op=='smooth':
        for seg in segments:
            values=[v.get('ele') for v in seg]
            for i,v in enumerate(seg):
                finite=[a for a in values[max(0,i-2):i+3] if a is not None]
                if values[i] is not None and finite:v['ele']=statistics.median(finite)
        return {'marks':[mark_with(mark,segments,mark['name']+' elevation median')]}
    if op=='dem':
        from .terrain import TerrainReader
        flat=[v for s in segments for v in s]
        if len(flat)>10000:raise ValueError('Limit DEM assignment to 10,000 points.')
        values=TerrainReader(p.get('source','terrain'),p.get('offline',False)).sample_points([(v['lat'],v['lon']) for v in flat])
        for v,z in zip(flat,values):
            if z is not None:v['ele']=z
        return {'marks':[mark_with(mark,segments,mark['name']+' DEM')],'statistics':{'missing_elevations':sum(v is None for v in values),'vertical_datum':'DEM source; no vertical transformation'}}
    raise ValueError('Unknown GPS operation.')
