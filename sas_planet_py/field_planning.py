"""Metric coordinate grids, CSV conversion, offline graph routes and coverage lines."""
import csv,io,json,math,uuid,heapq
import numpy as np
from pyproj import Transformer
from shapely.geometry import shape,LineString,box,mapping
from shapely.ops import transform
from shapely.affinity import rotate
from .gis_common import target_crs,output_file,download
def transformers(bbox,crs='utm_wgs84_auto'):
    target,label=target_crs(crs,bbox)
    if not target.is_projected or target.linear_units not in ('metre','meter'):raise ValueError('Select a projected CRS in meters.')
    forward=Transformer.from_crs(4326,target.to_wkt(),always_xy=True);inverse=Transformer.from_crs(target.to_wkt(),4326,always_xy=True);return forward,inverse,label
def metric_grid(p):
    bbox=p['bbox'];forward,inverse,label=transformers(bbox,p.get('crs','utm_ns_auto'));extent=transform(forward.transform,box(*bbox)).bounds;w,s,e,n=extent;step=float(p.get('step_m',1000))
    if step not in (100,500,1000,5000,10000,100000):raise ValueError('Select a supported grid spacing.')
    if not all(math.isfinite(v) for v in extent) or (e-w+n-s)/step>180:raise ValueError('Zoom in or increase grid spacing (maximum 180 lines).')
    features=[]
    for axis,low,high in [('E',w,e),('N',s,n)]:
        for value in np.arange(math.ceil(low/step)*step,high+step*.001,step):
            coords=[inverse.transform(value,v) if axis=='E' else inverse.transform(v,value) for v in np.linspace(s,n,25) if axis=='E'] if axis=='E' else [inverse.transform(v,value) for v in np.linspace(w,e,25)]
            features.append({'type':'Feature','properties':{'axis':axis,'value_m':float(value),'label':axis+' '+str(round(value/1000,3))+' km'},'geometry':{'type':'LineString','coordinates':coords}})
    return {'geojson':{'type':'FeatureCollection','features':features},'statistics':{'crs':label,'step_m':step,'lines':len(features)}}
def batch_coordinates(p):
    delimiter=p.get('delimiter',',')
    if delimiter not in (',',';','\t'):raise ValueError('Select CSV delimiter.')
    content=p.get('csv','')
    if len(content)>16*1024**2:raise ValueError('CSV exceeds 16 MB.')
    reader=csv.DictReader(io.StringIO(content.lstrip('\ufeff')),delimiter=delimiter);fields=reader.fieldnames or []
    xfield=p.get('x_field','x');yfield=p.get('y_field','y')
    if xfield not in fields or yfield not in fields:raise ValueError('Mapped X/Y columns not found.')
    src,source_label=target_crs(p.get('source_crs','EPSG:4326'));dst,destination_label=target_crs(p.get('target_crs','EPSG:30731'))
    converter=Transformer.from_crs(src.to_wkt(),dst.to_wkt(),always_xy=True)
    uses_ns=any(30729<=int(label[5:])<=30732 for label in (source_label,destination_label))
    geographic=Transformer.from_crs(src.to_wkt(),4326,always_xy=True)
    from .nord_sahara import PARAMETERS
    names=['output_x','output_y','conversion_error'];out=io.StringIO();writer=csv.DictWriter(out,fieldnames=fields+[k for k in names if k not in fields],delimiter=delimiter);writer.writeheader();good=bad=0;preview=[]
    for i,row in enumerate(reader):
        if i>=50000:raise ValueError('Limit CSV to 50,000 points.')
        try:
            x=float(row[xfield]);y=float(row[yfield])
            if not math.isfinite(x+y):raise ValueError('Non-finite input')
            if src.is_geographic and not(-180<=x<=180 and -90<y<90):raise ValueError('Geographic input out of bounds')
            if uses_ns:
                lon,lat=geographic.transform(x,y,errcheck=True);w,s,e,n=PARAMETERS['bbox']
                if not w<=lon<e or not s<=lat<=n:raise ValueError('Outside Nord Sahara 1959 area of use (Algeria).')
            x,y=converter.transform(x,y,errcheck=True)
            if not math.isfinite(x+y):raise ValueError('Outside coordinate system')
            row.update(output_x=format(x,'.10f' if dst.is_geographic else '.4f'),output_y=format(y,'.10f' if dst.is_geographic else '.4f'),conversion_error='');good+=1
        except Exception as error:row.update(output_x='',output_y='',conversion_error=str(error)[:180]);bad+=1
        writer.writerow(row)
        if len(preview)<8:preview.append(row.copy())
    path=output_file('coordinates','.csv');path.write_text(out.getvalue(),'utf-8-sig')
    report={'source_crs':source_label,'target_crs':destination_label,'converted':good,'failed':bad,'vertical_transformation':False,'nord_sahara_operation':'EPSG:1253; published accuracy 44 m' if any(30729<=int(s[5:])<=30732 for s in (source_label,destination_label)) else None}
    info=path.with_suffix('.json');info.write_text(json.dumps(report,indent=2),'utf8');return {'files':[{'name':'Coordinates CSV','url':download(path)},{'name':'Transformation report','url':download(info)}],'statistics':report,'preview':preview}
def coverage(p):
    geometry=shape(p['geometry'])
    if geometry.geom_type not in ('Polygon','MultiPolygon') or not geometry.is_valid:raise ValueError('Select a valid coverage polygon.')
    bbox=list(geometry.bounds);forward,inverse,label=transformers(bbox);g=transform(forward.transform,geometry);spacing=float(p.get('spacing_m',25));angle=float(p.get('angle_deg',0))
    if not 1<=spacing<=10000 or not math.isfinite(angle):raise ValueError('Invalid spacing/angle.')
    if g.area>1000000000:raise ValueError('Limit coverage planning to 1000 km².')
    from shapely import segmentize
    g=transform(forward.transform,segmentize(geometry,.0003))
    origin=g.centroid.coords[0];rotated=rotate(g,-angle,origin=origin);w,s,e,n=rotated.bounds
    if (n-s)/spacing>1000:raise ValueError('Too many survey legs; increase spacing.')
    segments=[]
    for row,y in enumerate(np.arange(s+spacing/2,n,spacing)):
        intersection=rotated.intersection(LineString([(w-1,y),(e+1,y)]));parts=list(intersection.geoms) if hasattr(intersection,'geoms') else [intersection]
        for line in parts:
            if line.geom_type!='LineString' or line.length<.01:continue
            restored=rotate(line,angle,origin=origin);points=[restored.interpolate(d).coords[0] for d in np.linspace(0,restored.length,max(2,math.ceil(restored.length/20)+1))]
            if row%2:points.reverse()
            points=[inverse.transform(*v) for v in points];segments.append([{'lon':v[0],'lat':v[1]} for v in points])
    if not segments:raise ValueError('No legs fit; reduce spacing.')
    mark={'id':uuid.uuid4().hex,'name':'Coverage plan','type':'linestring','category':'GPS coverage','color':'#935aca','trackSegments':segments,'coords':[[v['lon'],v['lat']] for seg in segments for v in seg]}
    from .field_tracks import analysis
    report=analysis(mark)['statistics'];report.update(crs=label,spacing_m=spacing,angle_deg=angle,connections_planned=False,note='Separate survey legs clipped to boundary and holes. Transit connections and obstacle clearance are not planned.')
    return {'marks':[mark],'statistics':report}
def route(p):
    features=p['roads'].get('features',[]);mode=p.get('mode','walk')
    if len(features)>50000 or mode not in ('walk','bike','car'):raise ValueError('Use up to 50,000 road features and a supported mode.')
    a,b=p['start'],p['end'];bbox=[min(a[0],b[0]),min(a[1],b[1]),max(a[0],b[0]),max(a[1],b[1])];forward,inverse,label=transformers(bbox);start=forward.transform(*a);end=forward.transform(*b)
    if math.dist(start,end)>200000:raise ValueError('Limit local routing to 200 km.')
    edges=[]
    for f in features:
        props=f.get('properties') or {};geometry=f.get('geometry') or {};kind=geometry.get('type')
        if props.get('access') in ('no','private') or props.get({'walk':'foot','bike':'bicycle','car':'motor_vehicle'}[mode])=='no':continue
        if mode=='car' and props.get('highway') in ('footway','path','steps','pedestrian','cycleway'):continue
        if mode=='walk' and props.get('highway') in ('motorway','motorway_link'):continue
        parts=[geometry['coordinates']] if kind=='LineString' else geometry.get('coordinates',[]) if kind=='MultiLineString' else []
        direction=-1 if props.get('oneway')=='-1' and mode!='walk' else 1 if str(props.get('oneway')).lower() in ('yes','true','1') and mode!='walk' else 0
        for points in parts:
            for x,y in zip(points,points[1:]):
                u,v=forward.transform(*x[:2]),forward.transform(*y[:2])
                if all(math.isfinite(t) for t in (*u,*v)) and math.dist(u,v)>.01:edges.append((u,v,direction))
                if len(edges)>150000:raise ValueError('Road graph exceeds 150,000 edges.')
    if not edges:raise ValueError('No accessible road edges.')
    def nearest(point):
        best=(float('inf'),0,0)
        for i,(u,v,_) in enumerate(edges):
            dx,dy=v[0]-u[0],v[1]-u[1];t=max(0,min(1,((point[0]-u[0])*dx+(point[1]-u[1])*dy)/(dx*dx+dy*dy)));q=(u[0]+t*dx,u[1]+t*dy);candidate=(math.dist(point,q),i,t)
            if candidate<best:best=candidate
        return best
    first,last=nearest(start),nearest(end);limit=float(p.get('max_snap_m',250))
    if first[0]>limit or last[0]>limit:raise ValueError('Start/end too far from road graph; move points or increase snap limit.')
    graph={}
    def key(v):return (round(v[0],2),round(v[1],2))
    def add(u,v):
        graph.setdefault(key(u),[]).append((key(v),math.dist(u,v)));graph.setdefault(key(v),[])
    nodes=[]
    for i,(u,v,direction) in enumerate(edges):
        cuts=[(0,u),(1,v)]
        for match in (first,last):
            if match[1]==i:
                t=match[2];cuts.append((t,(u[0]+t*(v[0]-u[0]),u[1]+t*(v[1]-u[1]))))
        cuts.sort()
        for (_,x),(_,y) in zip(cuts,cuts[1:]):
            if direction>=0:add(x,y)
            if direction<=0:add(y,x)
    def snapped(match):
        u,v,_=edges[match[1]];t=match[2];return key((u[0]+t*(v[0]-u[0]),u[1]+t*(v[1]-u[1])))
    first_node,last_node=snapped(first),snapped(last)
    if first_node==last_node:raise ValueError('Start and end resolve to the same road position.')
    queue=[(0,first_node)];distances={first_node:0};previous={}
    while queue:
        cost,node=heapq.heappop(queue)
        if cost!=distances[node]:continue
        if node==last_node:break
        for other,length in graph.get(node,[]):
            value=cost+length
            if value<distances.get(other,float('inf')):distances[other]=value;previous[other]=node;heapq.heappush(queue,(value,other))
    if last_node not in distances:raise ValueError('No connected route. Road intersections must share vertices; separate bridges/levels remain separate.')
    path=[last_node]
    while path[-1]!=first_node:path.append(previous[path[-1]])
    points=[inverse.transform(*v) for v in reversed(path)]
    mark={'id':uuid.uuid4().hex,'name':'Local '+mode+' route','type':'linestring','coords':points,'color':'#2867d5','category':'GPS route','gpxKind':'rte'}
    return {'marks':[mark],'statistics':{'distance_m':distances[last_node],'start_snap_m':first[0],'end_snap_m':last[0],'mode':mode,'crs':label,'edges':len(edges),'method':'Dijkstra shortest distance on supplied graph; direction/access filters','note':'Only shared vertices connect roads. No traffic, turn restrictions or guaranteed map freshness. Snapped endpoints exclude off-road access legs.'}}
