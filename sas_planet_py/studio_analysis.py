"""Local watershed, stream network and terrain visibility products."""
import math,json
from collections import deque
import numpy as np
from rasterio.transform import from_bounds
from rasterio.features import shapes
from PIL import Image
from .gis_common import analysis_grid,grid_tiff,output_file,download
from .terrain_analysis import drainage,metric_spacing,D8

def cell_for(point,bbox,rows,cols):
    lon,lat=map(float,point);w,s,e,n=bbox
    if not(w<=lon<=e and s<=lat<=n):raise ValueError('Point must be inside the selected region.')
    return min(rows-1,int((n-lat)/(n-s)*rows)),min(cols-1,int((lon-w)/(e-w)*cols))

def center(r,c,bbox,rows,cols):
    w,s,e,n=bbox;return [w+(c+.5)*(e-w)/cols,n-(r+.5)*(n-s)/rows]

def watershed_grid(grid,bbox,pour_point,threshold_cells=100,snap_cells=3):
    rows,cols=len(grid),len(grid[0]);dx,dy=metric_spacing(bbox,rows,cols)
    hydro=drainage(grid,dx,dy);flow=hydro['flow_direction'];acc=hydro['flow_accumulation']
    r,c=cell_for(pour_point,bbox,rows,cols)
    candidates=[(acc[y][x],y,x) for y in range(max(0,r-snap_cells),min(rows,r+snap_cells+1)) for x in range(max(0,c-snap_cells),min(cols,c+snap_cells+1)) if acc[y][x] is not None]
    if not candidates:raise ValueError('No valid DEM near the outlet.')
    _,r,c=max(candidates,key=lambda t:(t[0],-((t[1]-r)**2+(t[2]-c)**2)))
    reverse={};offsets={code:(dr,dc) for dr,dc,code in D8}
    for y in range(rows):
        for x in range(cols):
            if flow[y][x] in offsets:
                dr,dc=offsets[flow[y][x]];reverse.setdefault((y+dr,x+dc),[]).append((y,x))
    mask=np.zeros((rows,cols),dtype='uint8');q=deque([(r,c)])
    while q:
        y,x=q.popleft()
        if mask[y,x]:continue
        mask[y,x]=1;q.extend(reverse.get((y,x),[]))
    features=[{'type':'Feature','properties':{'outlet_lon':center(r,c,bbox,rows,cols)[0],'outlet_lat':center(r,c,bbox,rows,cols)[1]},'geometry':geom} for geom,val in shapes(mask,mask=mask.astype(bool),transform=from_bounds(*bbox,cols,rows)) if val==1]
    # Join stream reaches between junctions rather than emitting disconnected cell edges.
    edges={}
    for y in range(rows):
        for x in range(cols):
            if mask[y,x] and acc[y][x] is not None and acc[y][x]+1>=threshold_cells and flow[y][x] in offsets:
                dr,dc=offsets[flow[y][x]];target=(y+dr,x+dc)
                if 0<=target[0]<rows and 0<=target[1]<cols and mask[target]:edges[(y,x)]=target
    incoming={}
    for a,b in edges.items():incoming[b]=incoming.get(b,0)+1
    streams=[];visited=set()
    for start in edges:
        if incoming.get(start,0)==1:continue
        path=[start];current=start
        while current in edges and current not in visited:
            visited.add(current);current=edges[current];path.append(current)
            if incoming.get(current,0)!=1:break
        if len(path)>1:streams.append({'type':'Feature','properties':{'threshold_cells':threshold_cells},'geometry':{'type':'LineString','coordinates':[center(y,x,bbox,rows,cols) for y,x in path]}})
    area=sum(float(mask[y].sum())*dx[y]*dy[y] for y in range(rows))
    return mask,{'type':'FeatureCollection','features':features},{'type':'FeatureCollection','features':streams},{'area_m2':area,'cells':int(mask.sum()),'snapped_outlet':center(r,c,bbox,rows,cols),'upstream_cells':acc[r][c],'threshold_cells':threshold_cells,'boundary_limited':True}

def viewshed_grid(grid,bbox,observer,observer_height=2,target_height=0,refraction=.13,curvature=True,max_distance=100000):
    a=np.array([[np.nan if v is None else v for v in row] for row in grid],dtype=float);rows,cols=a.shape
    oy,ox=cell_for(observer,bbox,rows,cols)
    if not np.isfinite(a[oy,ox]):raise ValueError('Observer has no elevation data.')
    dx,dy=metric_spacing(bbox,rows,cols);sx=dx[oy];sy=dy[oy]
    result=np.full(a.shape,np.nan);rr,cc=np.indices(a.shape);flat=list(zip(rr.ravel(),cc.ravel()))
    for start in range(0,len(flat),256):
        points=np.array(flat[start:start+256]);ys,xs=points[:,0],points[:,1];distance=np.hypot((xs-ox)*sx,(ys-oy)*sy)
        steps=max(2,int(np.ceil(max(np.max(np.abs(xs-ox)),np.max(np.abs(ys-oy)))*2)))
        t=np.arange(1,steps)/steps
        yy=oy+(ys[:,None]-oy)*t;xx=ox+(xs[:,None]-ox)*t
        y0=np.floor(yy).astype(int);x0=np.floor(xx).astype(int);y1=np.minimum(y0+1,rows-1);x1=np.minimum(x0+1,cols-1)
        fy=yy-y0;fx=xx-x0
        # A missing neighbor with zero weight does not invalidate an exact grid sample.
        terrain=np.zeros_like(yy);unknown=np.zeros_like(yy,dtype=bool)
        for syi,sxi,weight in ((y0,x0,(1-fy)*(1-fx)),(y1,x0,fy*(1-fx)),(y0,x1,(1-fy)*fx),(y1,x1,fy*fx)):
            values=a[syi,sxi];unknown|=(~np.isfinite(values))&(weight>1e-10);terrain+=np.nan_to_num(values)*weight
        line=a[oy,ox]+observer_height+(a[ys,xs,None]+target_height-a[oy,ox]-observer_height)*t
        bulge=distance[:,None]**2*t*(1-t)/(2*6371008.8/(1-refraction)) if curvature else 0
        visible=~np.any(terrain+bulge>line+1e-7,axis=1)
        valid=np.isfinite(a[ys,xs])&(~unknown.any(axis=1))&(distance<=max_distance)
        result[ys[valid],xs[valid]]=visible[valid].astype(float)
    result[oy,ox]=1
    return result

def volume_grid(grid,bbox,base_mode='min',base_level=0.0):
    """Cut and fill volumes of the terrain against a reference level (m)."""
    a=np.array([[np.nan if v is None else v for v in row] for row in grid],dtype=float)
    rows,cols=a.shape;dx,dy=metric_spacing(bbox,rows,cols)
    finite=np.isfinite(a)
    if not finite.any():raise ValueError('No elevation data in the selected region.')
    if base_mode=='mean':reference=float(np.nanmean(a))
    elif base_mode=='max':reference=float(np.nanmax(a))
    elif base_mode=='custom':reference=float(base_level)
    else:reference=float(np.nanmin(a))
    diff=np.where(finite,a-reference,np.nan)   # + above reference (cut), - below (fill)
    area=np.array([[dx[r]*dy[r] for _ in range(cols)] for r in range(rows)])
    cut=float(np.nansum(np.where(diff>0,diff,0.0)*area))
    fill=float(np.nansum(np.where(diff<0,-diff,0.0)*area))
    total_area=float(np.nansum(np.where(finite,area,0.0)))
    stats={'base_mode':base_mode,'base_level_m':round(reference,3),'cut_volume_m3':round(cut,2),'fill_volume_m3':round(fill,2),
           'net_volume_m3':round(cut-fill,2),'surface_area_m2':round(total_area,2),
           'min_elevation_m':round(float(np.nanmin(a)),2),'max_elevation_m':round(float(np.nanmax(a)),2),'cells':int(finite.sum())}
    span=max(1e-6,float(np.nanmax(np.abs(diff))))
    image=np.zeros((rows,cols,4),dtype='uint8')
    above=diff>0;below=diff<0
    image[above]=np.column_stack([np.full(int(above.sum()),220),(200*(1-np.clip(diff[above]/span,0,1))).astype('uint8'),np.full(int(above.sum()),50),np.full(int(above.sum()),170)])
    image[below]=np.column_stack([np.full(int(below.sum()),40),(120+120*np.clip(-diff[below]/span,0,1)).astype('uint8'),np.full(int(below.sum()),230),np.full(int(below.sum()),170)])
    return diff,image,stats

def index_from_rgb(r,g,b,kind='vari'):
    """Visible-band vegetation index from 8-bit RGB arrays, clipped to [-1, 1]."""
    r=r.astype(float);g=g.astype(float);b=b.astype(float)
    with np.errstate(divide='ignore',invalid='ignore'):
        if kind=='gli':
            denom=2*g+r+b
            index=np.where(denom>1e-6,(2*g-r-b)/denom,0.0)
        else:  # VARI — Visible Atmospherically Resistant Index
            denom=g+r-b
            index=np.where(np.abs(denom)>1e-6,(g-r)/denom,0.0)
    return np.clip(index,-1,1)

def colorize_index(index,valid):
    """Brown → yellow → green ramp as an RGBA overlay; transparent where invalid."""
    rows,cols=index.shape;image=np.zeros((rows,cols,4),dtype='uint8')
    t=np.clip((index+0.2)/0.8,0,1)  # emphasise the vegetation range
    red=np.where(t<0.5,165+2*(255-165)*t,255*(1-t)*2*0.6+90*(2*t-1)).astype('uint8')
    green=np.where(t<0.5,100+2*(200-100)*t,200-(200-110)*(2*t-1)).astype('uint8')
    blue=np.where(t<0.5,40+2*(40-40)*t,40+(60)*(2*t-1)).astype('uint8')
    image[...,0]=red;image[...,1]=green;image[...,2]=blue;image[...,3]=np.where(valid,185,0).astype('uint8')
    return image

def vegetation_index(p):
    """Stitch the current imagery over the bbox and derive a visible vegetation index."""
    import rasterio
    from .tile_stitcher import TileStitcher
    bbox=p['bbox'];source_id=p.get('source_id','google_sat');kind=str(p.get('kind','vari')).lower()
    zoom=int(p.get('zoom',15))
    if kind not in ('vari','gli'):raise ValueError('Index must be VARI or GLI.')
    if not 1<=zoom<=21:raise ValueError('Zoom must be 1–21.')
    tif=output_file('imagery','.tif')
    stitched=TileStitcher.stitch_bbox(source_id=source_id,bbox=tuple(bbox),zoom=zoom,output_image_path=str(tif),target_crs='EPSG:4326')
    with rasterio.open(tif) as ds:
        if ds.count<3:raise ValueError('The map source is not RGB imagery; choose a satellite/aerial source.')
        r=ds.read(1);g=ds.read(2);b=ds.read(3)
    valid=(r.astype(int)+g+b)>0
    index=index_from_rgb(r,g,b,kind)
    overlay=colorize_index(index,valid)
    png=output_file('veg_index','.png');Image.fromarray(overlay).save(png)
    bounds=stitched['bounds'];out_bbox=[bounds['min_lon'],bounds['min_lat'],bounds['max_lon'],bounds['max_lat']]
    itif=output_file('veg_index','.tif');grid_tiff(itif,np.where(valid,index,np.nan),out_bbox,title=kind+'_index')
    veg=float(np.mean((index>0.1)&valid))*100 if valid.any() else 0.0
    stats={'index':kind.upper(),'zoom':zoom,'source':source_id,'mean_index':round(float(np.mean(index[valid])),4) if valid.any() else None,
           'vegetated_percent':round(veg,1),'min':round(float(np.min(index[valid])),4) if valid.any() else None,'max':round(float(np.max(index[valid])),4) if valid.any() else None,'pixels':int(valid.sum())}
    return {'files':[{'name':kind+'_index.tif','url':download(itif)}],'preview':download(png),'bbox':out_bbox,'geojson':None,'statistics':stats,
            'note':'Visible-band index from RGB imagery (not true NDVI, which needs a near-infrared band). Useful as a relative vegetation guide; shadows, water and bare soil can bias it.'}

def run_analysis(operation,p):
    bbox=p['bbox'];dem=analysis_grid(bbox,p.get('resolution',256),p.get('source','terrain'),p.get('offline',False));grid=dem['grid']
    files=[]
    if operation=='volume':
        base_mode=str(p.get('base_mode','min'))
        if base_mode not in ('min','mean','max','custom'):raise ValueError('Base level must be min, mean, max or custom.')
        raster,image,stats=volume_grid(grid,bbox,base_mode,float(p.get('base_level',0)))
        path=output_file('volume','.tif');grid_tiff(path,raster,bbox,title='cut_fill_depth');files.append({'name':'cut_fill_depth.tif','url':download(path)})
        png=path.with_suffix('.png');Image.fromarray(image).save(png)
        return {'files':files,'preview':download(png),'bbox':bbox,'geojson':None,'statistics':stats,'source':dem['source'],'note':'Terrain-only cut/fill against a flat reference level; buildings and vegetation need a DSM. Accuracy follows the elevation source.'}
    if operation=='watershed':
        threshold=int(p.get('threshold_cells',100));snap=int(p.get('snap_cells',3))
        if not 1<=threshold<=1000000 or not 0<=snap<=20:raise ValueError('Invalid stream threshold or outlet snap radius.')
        mask,basin,streams,stats=watershed_grid(grid,bbox,p['point'],threshold,snap)
        for name,data in [('watershed',basin),('streams',streams)]:
            path=output_file(name,'.geojson');path.write_text(json.dumps(data),encoding='utf8');files.append({'name':name+'.geojson','url':download(path)})
        raster=np.where(mask,1,np.nan);overlay=basin
        image=np.zeros((*mask.shape,4),dtype='uint8');image[mask.astype(bool)]=[15,150,235,140]
    else:
        height=float(p.get('observer_height',2));target=float(p.get('target_height',0));refraction=float(p.get('refraction',.13));distance=float(p.get('max_distance',100000))
        if not 0<=height<=10000 or not 0<=target<=10000 or not 0<=refraction<1 or not 1<=distance<=200000:raise ValueError('Invalid visibility heights, refraction or distance.')
        raster=viewshed_grid(grid,bbox,p['point'],height,target,refraction,bool(p.get('curvature',True)),distance)
        dx,dy=metric_spacing(bbox,len(grid),len(grid[0]));stats={'visible_cells':int(np.nansum(raster==1)),'hidden_cells':int(np.nansum(raster==0)),'unknown_cells':int(np.isnan(raster).sum()),'visible_area_m2':sum(int((raster[y]==1).sum())*dx[y]*dy[y] for y in range(len(grid))),'observer_height_m':height,'refraction':refraction}
        overlay=None;image=np.zeros((*raster.shape,4),dtype='uint8');image[raster==1]=[10,190,80,150];image[raster==0]=[220,60,55,100]
    path=output_file(operation,'.tif');grid_tiff(path,raster,bbox,title=operation);files.append({'name':operation+'.tif','url':download(path)})
    png=path.with_suffix('.png');Image.fromarray(image).save(png)
    return {'files':files,'preview':download(png),'bbox':bbox,'geojson':overlay,'statistics':stats,'source':dem['source'],'note':'Terrain-only model; buildings and vegetation require an appropriate DSM. Watersheds are limited by extraction boundaries.'}
