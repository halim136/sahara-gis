"""Local single-band elevation GeoTIFF catalog, windowed sampling, native-resolution mosaics."""
import json,math,re,uuid
from pathlib import Path
from contextlib import ExitStack
import numpy as np
import rasterio
from rasterio.warp import reproject,Resampling,transform_bounds
from rasterio.transform import from_bounds
from rasterio.windows import Window
from rasterio.vrt import WarpedVRT
from rasterio.merge import merge
from pyproj import Transformer
from .gis_common import TERRAIN,NODATA

ROOT=TERRAIN/'geotiff'

def dem_path(identifier):
    identifier=identifier.removeprefix('dem:')
    if not re.fullmatch('[0-9a-f]{32}',identifier):raise ValueError('Invalid DEM identifier.')
    return ROOT/(identifier+'.tif')

def inspect_dem(path,name=None):
    with rasterio.open(path) as src:
        if src.driver!='GTiff' or src.count!=1:raise ValueError('Use a single-band elevation GeoTIFF, not an RGB map image.')
        if not src.crs:raise ValueError('The elevation GeoTIFF has no coordinate reference system.')
        if src.width<2 or src.height<2:raise ValueError('Elevation raster is too small.')
        if src.dtypes[0] not in ('int16','uint16','int32','uint32','float32','float64','uint8','int8'):raise ValueError('Unsupported elevation data type.')
        bounds=transform_bounds(src.crs,'EPSG:4326',*src.bounds,densify_pts=21)
        info={'id':'dem:'+Path(path).stem,'name':name or Path(path).name,'width':src.width,'height':src.height,
              'crs':src.crs.to_string(),'wgs84_bbox':list(bounds),'pixel_size':list(src.res),'dtype':src.dtypes[0],
              'nodata':float(src.nodata) if src.nodata is not None and math.isfinite(src.nodata) else None,
              'elevation_units':'m (user supplied; verify vertical datum and units)'}
    Path(path).with_suffix('.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),'utf-8')
    return info

def list_dems():
    ROOT.mkdir(parents=True,exist_ok=True);result=[]
    for file in ROOT.glob('*.json'):
        try:
            value=json.loads(file.read_text('utf-8'))
            if dem_path(value['id']).is_file():result.append(value)
        except (ValueError,KeyError,OSError):pass
    return result

def read_grid(identifier,bbox,rows,cols):
    from .terrain import validate_bbox
    validate_bbox(bbox);w,s,e,n=bbox
    dx=(e-w)/(cols-1);dy=(n-s)/(rows-1)
    transform=from_bounds(w-dx/2,s-dy/2,e+dx/2,n+dy/2,cols,rows)
    array=np.full((rows,cols),np.nan,dtype='float32')
    with rasterio.open(dem_path(identifier)) as src:
        reproject(rasterio.band(src,1),array,src_transform=src.transform,src_crs=src.crs,src_nodata=src.nodata,
                  dst_transform=transform,dst_crs='EPSG:4326',dst_nodata=np.nan,resampling=Resampling.bilinear)
        pixel=(abs(src.res[1])*111320 if src.crs.is_geographic else max(map(abs,src.res)))
    mask=np.isfinite(array);values=array[mask]
    if not values.size:raise ValueError('The selected region has no valid local DEM coverage.')
    return {'grid':[[float(v) if math.isfinite(v) else None for v in row] for row in array],
            'rows':rows,'cols':cols,'bbox':bbox,'dx':dx,'dy':dy,'min_elevation':float(values.min()),'max_elevation':float(values.max()),
            'nodata_samples':int((~mask).sum()),'source':'Local GeoTIFF DEM','source_id':identifier,'offline':True,
            'source_pixel_size_m':round(pixel,2),'attribution':'User supplied local elevation raster'}

def sample_points(identifier,points):
    with rasterio.open(dem_path(identifier)) as src:
        converter=Transformer.from_crs(4326,src.crs,always_xy=True);result=[]
        for lat,lon in points:
            x,y=converter.transform(lon,lat);c,r=(~src.transform)*(x,y);c-=.5;r-=.5
            c0,r0=math.floor(c),math.floor(r);tx,ty=c-c0,r-r0
            samples=src.read(1,window=Window(c0,r0,2,2),boundless=True,masked=True)
            if samples.shape!=(2,2) or np.ma.getmaskarray(samples).any():result.append(None)
            else:result.append(float(samples[0,0]*(1-tx)*(1-ty)+samples[0,1]*tx*(1-ty)+samples[1,0]*(1-tx)*ty+samples[1,1]*tx*ty))
    return result

def mosaic(identifiers,name='Mosaic DEM'):
    if not isinstance(identifiers,list) or not 2<=len(identifiers)<=16:raise ValueError('Select 2 to 16 local elevation rasters.')
    ROOT.mkdir(parents=True,exist_ok=True);path=ROOT/(uuid.uuid4().hex+'.tif')
    with ExitStack() as stack:
        datasets=[stack.enter_context(rasterio.open(dem_path(i))) for i in identifiers]
        first=datasets[0];warped=[src if src.crs==first.crs else stack.enter_context(WarpedVRT(src,crs=first.crs,resampling=Resampling.bilinear)) for src in datasets]
        merge(warped,res=first.res,nodata=NODATA,dtype='float32',method='first',dst_path=path,mem_limit=64,
              dst_kwds={'compress':'deflate','tiled':True,'blockxsize':256,'blockysize':256,'BIGTIFF':'IF_SAFER'})
    return inspect_dem(path,name)
