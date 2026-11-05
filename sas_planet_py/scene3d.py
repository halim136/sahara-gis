"""Metric, local-UTM terrain mesh for a cached-image 3D viewer.
Missing elevations remain holes. Building heights are user estimates.
"""
import math
import numpy as np
from pyproj import Transformer
from .terrain import TerrainReader,validate_bbox
from .gis_common import target_crs

def mercator(lon,lat):
    radius=6378137.;return radius*math.radians(lon),radius*math.asinh(math.tan(math.radians(lat)))

def build_scene(bbox,source='terrain',offline=False,resolution=129,buildings=None,building_height=10):
    validate_bbox(bbox)
    if isinstance(resolution,bool) or resolution not in (65,129,257):raise ValueError('Select a 65, 129 or 257 vertex terrain grid.')
    if not isinstance(offline,bool):raise ValueError('Offline mode must be boolean.')
    if isinstance(building_height,bool) or not isinstance(building_height,(int,float)) or not math.isfinite(building_height) or not 1<=building_height<=500:raise ValueError('Building height must be 1–500 meters.')
    west,south,east,north=bbox
    crs,label=target_crs('utm_wgs84_auto',bbox);project=Transformer.from_crs(4326,crs.to_wkt(),always_xy=True)
    corners=[project.transform(x,y) for x in (west,east) for y in (south,north)]
    width=max(x for x,y in corners)-min(x for x,y in corners);depth=max(y for x,y in corners)-min(y for x,y in corners)
    if max(width,depth)>50000 or min(width,depth)<10:raise ValueError('Select a local region between 10 m and 50 km across for the 3D scene.')
    origin_x,origin_y=project.transform((west+east)/2,(south+north)/2);span=max(width,depth)
    dem=TerrainReader(source,offline).grid(bbox,resolution,resolution);grid=dem['grid']
    valid=[float(v) for row in grid for v in row if v is not None and math.isfinite(v)]
    if not valid:raise ValueError('No elevation coverage for the selected scene. Import a local DEM or cache terrain first.')
    base=min(valid);positions=[];uv=[];indices=[];elevations=[]
    left,bottom=mercator(west,south);right,top=mercator(east,north)
    for r,row in enumerate(grid):
        lat=north-r/(resolution-1)*(north-south)
        for c,v in enumerate(row):
            lon=west+c/(resolution-1)*(east-west);x,y=project.transform(lon,lat);mx,my=mercator(lon,lat)
            usable=v is not None and math.isfinite(v);elevations.append(float(v) if usable else None)
            positions.extend(((x-origin_x)/span,((float(v)-base) if usable else 0)/span,-(y-origin_y)/span));uv.extend(((mx-left)/(right-left),(my-bottom)/(top-bottom)))
    for r in range(resolution-1):
        for c in range(resolution-1):
            a=r*resolution+c;b=a+1;d=a+resolution;e=d+1
            # Each triangle is independent, preserving valid neighbors beside NoData.
            for triangle in ((a,d,b),(b,d,e)):
                if all(elevations[i] is not None for i in triangle):indices.extend(triangle)
    if not indices:raise ValueError('Insufficient connected elevation samples for a 3D surface.')
    def height_at(lon,lat):
        x=(lon-west)/(east-west)*(resolution-1);y=(north-lat)/(north-south)*(resolution-1)
        if not(0<=x<=resolution-1 and 0<=y<=resolution-1):return None
        c=min(resolution-2,int(x));r=min(resolution-2,int(y));fx=x-c;fy=y-r
        result=0.
        for rr,cc,weight in ((r,c,(1-fx)*(1-fy)),(r,c+1,fx*(1-fy)),(r+1,c,(1-fx)*fy),(r+1,c+1,fx*fy)):
            v=grid[rr][cc]
            if weight>1e-10 and (v is None or not math.isfinite(v)):return None
            result+=(float(v) if v is not None else 0)*weight
        return result
    shapes=[];skipped=0
    if buildings is not None and (not isinstance(buildings,list) or len(buildings)>2000):raise ValueError('Use at most 2000 building polygons.')
    from shapely.geometry import Polygon
    from shapely.ops import transform
    for feature in buildings or []:
        if feature.get('type')!='polygon':continue
        coords=feature.get('coords',[])
        try:
            rings=coords if coords and isinstance(coords[0][0],(list,tuple)) else [coords]
            if sum(len(r) for r in rings)>2000:skipped+=1;continue
            polygon=Polygon(rings[0],rings[1:])
            if polygon.is_empty or not polygon.is_valid:skipped+=1;continue
            if not all(west<=x<=east and south<=y<=north for ring in rings for x,y,*_ in ring):skipped+=1;continue
            local=[];heights=[];ground_rings=[]
            for ring in rings:
                out=[];ground_ring=[]
                for point in ring:
                    lon,lat=point[:2];height=height_at(lon,lat)
                    if height is None:raise ValueError('Building touches missing elevation data.')
                    x,y=project.transform(lon,lat);out.append([(x-origin_x)/span,-(y-origin_y)/span]);heights.append(height);ground_ring.append((height-base)/span)
                local.append(out);ground_rings.append(ground_ring)
            # A level estimated roof above the highest footprint sample avoids sinking into hillsides.
            ground=max(heights);height=feature.get('height_m',building_height)
            if isinstance(height,bool) or not isinstance(height,(int,float)) or not math.isfinite(height) or not 1<=height<=500:height=building_height
            shapes.append({'name':str(feature.get('name','Building'))[:200],'rings':local,'ground':ground_rings,'base':(ground-base)/span,'height':float(height)/span,'height_m':height,'height_kind':'user estimate','ground_elevation_m':ground})
        except (ValueError,TypeError,IndexError):skipped+=1
    return {'bbox':list(bbox),'positions':positions,'uv':uv,'indices':indices,'elevations':elevations,'buildings':shapes,
            'metadata':{'crs':label,'origin':[origin_x,origin_y],'base_elevation_m':base,'min_elevation_m':base,'max_elevation_m':max(valid),'span_m':span,'width_m':width,'depth_m':depth,'resolution':resolution,'nodata_samples':len(elevations)-len(valid),'triangles':len(indices)//3,'source':dem['source'],'source_pixel_size_m':dem.get('source_pixel_size_m'),'attribution':dem.get('attribution','Local DEM'),'skipped_buildings':skipped,'buildings_height_kind':'user estimates; not reconstructed from imagery','vertical_reference':'source elevation reference; no vertical datum transformation'}}
