"""Independent checkpoint errors, terrain QA and vector topology diagnostics."""
import json,math
import numpy as np
from shapely.geometry import shape,mapping,box
from shapely.validation import explain_validity
from shapely.ops import transform,unary_union
from pyproj import Transformer
from .gis_common import analysis_grid,target_crs,output_file,download
from .terrain_analysis import metric_spacing,terrain_metrics

def report_file(name,report,geojson=None):
    path=output_file(name,'.json');path.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8');files=[{'name':name+' report','url':download(path)}]
    if geojson is not None:
        file=path.with_suffix('.geojson');file.write_text(json.dumps(geojson,ensure_ascii=False),encoding='utf8');files.append({'name':'Diagnostics GeoJSON','url':download(file)})
    return {'statistics':report,'files':files,'geojson':geojson}

def checkpoints(p):
    points=p.get('points',[])
    if not 3<=len(points)<=10000:raise ValueError('Provide 3–10,000 independent checkpoints.')
    source=p.get('crs','EPSG:4326');bbox=p.get('bbox');destination,label=target_crs(p.get('metric_crs','utm_wgs84_auto'),bbox)
    if not destination.is_projected:raise ValueError('Error statistics require a metric projected CRS.')
    converter=Transformer.from_crs(source,destination.to_wkt(),always_xy=True);errors=[];vertical=[];features=[]
    same_vertical=p.get('observed_vertical','unknown')==p.get('reference_vertical','unknown') and p.get('observed_vertical','unknown')!='unknown'
    for i,point in enumerate(points):
        vals=[float(point[k]) for k in ('observed_x','observed_y','reference_x','reference_y')]
        if not all(math.isfinite(v) for v in vals):raise ValueError('Checkpoint coordinates must be finite.')
        ox,oy=converter.transform(*vals[:2]);rx,ry=converter.transform(*vals[2:]);dx,dy=ox-rx,oy-ry
        if not all(math.isfinite(v) for v in (ox,oy,rx,ry)):raise ValueError('Checkpoint outside coordinate system bounds.')
        errors.append([dx,dy])
        if same_vertical and point.get('observed_z') is not None and point.get('reference_z') is not None:
            dz=float(point['observed_z'])-float(point['reference_z'])
            if not math.isfinite(dz):raise ValueError('Invalid checkpoint elevation.')
            vertical.append(dz)
    arr=np.array(errors);radial=np.linalg.norm(arr,axis=1)
    report={'points':len(points),'metric_crs':label,'units':'m','bias_x_m':float(arr[:,0].mean()),'bias_y_m':float(arr[:,1].mean()),'rmse_x_m':float(np.sqrt((arr[:,0]**2).mean())),'rmse_y_m':float(np.sqrt((arr[:,1]**2).mean())),'horizontal_rmse_m':float(np.sqrt((radial**2).mean())),'max_horizontal_error_m':float(radial.max()),'empirical_p95_horizontal_m':float(np.percentile(radial,95)),'errors_xy_m':errors,'vertical_comparable':same_vertical,'vertical_points':len(vertical),'vertical_rmse_m':float(np.sqrt(np.mean(np.array(vertical)**2))) if vertical else None,'vertical_bias_m':float(np.mean(vertical)) if vertical else None,'observed_vertical':p.get('observed_vertical','unknown'),'reference_vertical':p.get('reference_vertical','unknown'),'vertical_transformation_applied':False,'independent_checkpoints_required':True,'note':'Empirical sample statistics, not a certified accuracy class. P95 with fewer than 20 points is unstable. Vertical statistics are withheld for unknown or differing datums.'}
    return report_file('checkpoints',report)

def dem_quality(p):
    dem=analysis_grid(p['bbox'],p.get('resolution',128),p.get('source','terrain'),p.get('offline',False));grid=dem['grid'];a=np.array([[np.nan if v is None else v for v in row] for row in grid]);valid=a[np.isfinite(a)]
    if not valid.size:raise ValueError('No valid elevation samples.')
    dx,dy=metric_spacing(p['bbox'],len(grid),len(grid[0]));spacing=max(dx[len(grid)//2],dy[len(grid)//2]);spikes=[]
    for r in range(1,len(grid)-1):
        for c in range(1,len(grid[0])-1):
            values=np.delete(a[r-1:r+2,c-1:c+2].ravel(),4);values=values[np.isfinite(values)]
            if np.isfinite(a[r,c]) and len(values)>=6:
                median=np.median(values);mad=np.median(np.abs(values-median))
                if abs(a[r,c]-median)>max(30,6*mad):spikes.append([r,c,float(a[r,c]-median)])
    native=dem.get('source_pixel_size_m');report={'source':dem['source'],'rows':len(grid),'cols':len(grid[0]),'bbox':p['bbox'],'valid_samples':int(valid.size),'nodata_samples':int(a.size-valid.size),'nodata_percent':float((a.size-valid.size)/a.size*100),'min_m':float(valid.min()),'max_m':float(valid.max()),'median_m':float(np.median(valid)),'p01_m':float(np.percentile(valid,1)),'p99_m':float(np.percentile(valid,99)),'analysis_spacing_m':spacing,'source_pixel_size_m':native,'oversampled':bool(native and spacing<float(native)*.8),'possible_spikes':len(spikes),'spike_samples':spikes[:1000],'vertical_datum_declared':p.get('vertical_datum','unknown'),'vertical_datum_verified':False,'height_units':'m assumed; verify source','attribution':dem.get('attribution'),'note':'Spike flags can be real cliffs; review them. Resampling does not improve native DEM accuracy. No vertical datum transformation is performed.'}
    return report_file('dem_quality',report)

def features_from_marks(marks):
    result=[]
    for mark in marks:
        kind={'point':'Point','linestring':'LineString','polygon':'Polygon'}.get(mark.get('type'))
        if not kind:continue
        coords=mark.get('coords',[])
        if kind=='Polygon' and coords and isinstance(coords[0][0],(float,int)):coords=[coords]
        result.append({'type':'Feature','id':mark.get('id'),'properties':{'id':mark.get('id'),'name':mark.get('name','')},'geometry':{'type':kind,'coordinates':coords}})
    return result

def topology(p):
    features=p.get('features') or features_from_marks(p.get('marks',[]))
    if not isinstance(features,list) or len(features)>2000:raise ValueError('Topology checks accept at most 2000 features.')
    bbox=p['bbox'];crs,label=target_crs('utm_wgs84_auto',bbox);forward=Transformer.from_crs(4326,crs.to_wkt(),always_xy=True);inverse=Transformer.from_crs(crs.to_wkt(),4326,always_xy=True);invalid=[];polygons=[];overlaps=[];diagnostics=[]
    for i,f in enumerate(features):
        try:g=shape(f['geometry'])
        except Exception:invalid.append({'index':i,'reason':'Unreadable geometry'});continue
        if g.is_empty or not g.is_valid:invalid.append({'index':i,'id':f.get('id'),'reason':explain_validity(g)});continue
        if g.geom_type in ('Polygon','MultiPolygon'):polygons.append((i,transform(forward.transform,g)))
    tolerance=float(p.get('area_tolerance_m2',.1))
    if not math.isfinite(tolerance) or tolerance<0:raise ValueError('Invalid area tolerance.')
    for pos,(i,a) in enumerate(polygons):
        for j,b in polygons[pos+1:]:
            if not a.intersects(b):continue
            overlap=a.intersection(b)
            if overlap.area>tolerance:
                overlaps.append({'a':i,'b':j,'area_m2':overlap.area});diagnostics.append({'type':'Feature','properties':{'issue':'overlap','a':i,'b':j,'area_m2':overlap.area},'geometry':mapping(transform(inverse.transform,overlap))})
                if len(overlaps)>=1000:break
        if len(overlaps)>=1000:break
    gaps=None
    if p.get('check_gaps'):
        boundary=transform(forward.transform,shape(p['boundary'])) if p.get('boundary') else transform(forward.transform,box(*bbox))
        gap=boundary.difference(unary_union([g for _,g in polygons]));gaps=float(gap.area)
        if gaps>tolerance:diagnostics.append({'type':'Feature','properties':{'issue':'candidate_gap','area_m2':gaps},'geometry':mapping(transform(inverse.transform,gap))})
    report={'features':len(features),'invalid':invalid,'overlaps':overlaps,'candidate_gap_area_m2':gaps,'metric_crs':label,'note':'Gaps are unfilled parts of the chosen coverage boundary and may be intentional. Diagnostics do not alter source data.'}
    return report_file('topology',report,{'type':'FeatureCollection','features':diagnostics})

def validate_edit(p):
    mark=p['mark'];feature=features_from_marks([mark])[0];g=shape(feature['geometry'])
    if g.is_empty or not g.is_valid:raise ValueError(explain_validity(g))
    for x,y,*_ in __import__('shapely').get_coordinates(g):
        if not math.isfinite(x+y) or not -180<=x<=180 or not -85<=y<=85:raise ValueError('Edited coordinates outside supported bounds.')
    return {'valid':True,'mark':mark}
