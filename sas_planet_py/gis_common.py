"""Shared GIS I/O; all work stays inside the application data/export folders."""
import json,math,uuid
from pathlib import Path
import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds
from rasterio.warp import calculate_default_transform,reproject,Resampling
from pyproj import CRS as PyCRS,Transformer
from .terrain import validate_bbox
from .nord_sahara import PARAMETERS

APP=Path(__file__).resolve().parents[1]
EXPORTS=APP/'public/exports'
TERRAIN=APP/'cache/terrain'
NODATA=-9999.0

def output_file(prefix,suffix,output_dir=None):
    root=Path(output_dir) if output_dir else EXPORTS;root.mkdir(parents=True,exist_ok=True)
    return root/(prefix+'_'+uuid.uuid4().hex[:12]+suffix)

def download(path):return '/exports/'+Path(path).name

def target_crs(value='EPSG:4326',bbox=None):
    value=str(value)
    if value in ('utm_wgs84_auto','utm_ns_auto'):
        if bbox is None:raise ValueError('A region is required for automatic UTM selection.')
        lon=(bbox[0]+bbox[2])/2;lat=(bbox[1]+bbox[3])/2;zone=min(60,max(1,int((lon+180)//6)+1))
        if value=='utm_ns_auto':value='EPSG:'+str(30700+zone)
        else:value='EPSG:'+str((32600 if lat>=0 else 32700)+zone)
    if not value.startswith('EPSG:') or not value[5:].isdigit():raise ValueError('Select a valid EPSG coordinate system.')
    code=int(value[5:])
    if 30729<=code<=30732:
        if bbox is not None:
            lon=(bbox[0]+bbox[2])/2;lat=(bbox[1]+bbox[3])/2
            w,s,e,n=PARAMETERS['bbox']
            if not(w<=lon<e and s<=lat<=n):raise ValueError('Nord Sahara 1959 is intended for Algeria.')
        proj='+proj=utm +zone='+str(code-30700)+' +a='+str(PARAMETERS['a'])+' +rf='+str(PARAMETERS['rf'])+' +towgs84='+','.join(map(str,PARAMETERS['towgs84']))+' +units=m +no_defs'
        return CRS.from_string(proj),value
    return CRS.from_epsg(code),value

def grid_array(grid):return np.array([[NODATA if v is None else v for v in row] for row in grid],dtype='float32')

def grid_tiff(path,grid,bbox,crs='EPSG:4326',title='GIS layer'):
    array=grid_array(grid) if not isinstance(grid,np.ndarray) else grid.astype('float32')
    array=np.where(np.isfinite(array),array,NODATA).astype('float32')
    with rasterio.open(path,'w',driver='GTiff',width=array.shape[1],height=array.shape[0],count=1,dtype='float32',crs=crs,
                       transform=from_bounds(*bbox,array.shape[1],array.shape[0]),nodata=NODATA,compress='deflate') as dst:
        dst.write(array,1);dst.set_band_description(1,title)
    return path

def warped_bytes(raw,dst_crs,reference=None,nearest=False):
    from rasterio.io import MemoryFile
    with MemoryFile(raw) as memory, memory.open() as src:
        transform,width,height=reference or calculate_default_transform(src.crs,dst_crs,src.width,src.height,*src.bounds)
        profile=src.profile.copy();profile.update(driver='GTiff',crs=dst_crs,transform=transform,width=width,height=height,compress='deflate')
        with MemoryFile() as out:
            with out.open(**profile) as dst:
                for band in range(1,src.count+1):
                    reproject(rasterio.band(src,band),rasterio.band(dst,band),src_transform=src.transform,src_crs=src.crs,
                              dst_transform=transform,dst_crs=dst_crs,src_nodata=src.nodata,dst_nodata=src.nodata,
                              resampling=Resampling.nearest if nearest else Resampling.bilinear)
                dst.update_tags(**{k:v for k,v in src.tags().items() if k!='TIFFTAG_IMAGEDESCRIPTION'})
                dst.update_tags(TIFFTAG_IMAGEDESCRIPTION='Reprojected GIS layer; horizontal CRS='+dst_crs.to_string())
            return out.read(),(transform,width,height)

def analysis_grid(bbox,resolution=256,source='terrain',offline=False):
    from .terrain import TerrainReader
    validate_bbox(bbox)
    if isinstance(resolution,bool) or resolution not in (64,128,256,512):raise ValueError('Resolution must be 64,128,256 or 512.')
    rows=cols=resolution;w,s,e,n=bbox;dx=(e-w)/cols;dy=(n-s)/rows
    dem=TerrainReader(source,offline).grid((w+dx/2,s+dy/2,e-dx/2,n-dy/2),rows,cols)
    dem['bbox']=list(bbox)
    return dem

def geojson_transform(collection,source,destination):
    from shapely.geometry import shape,mapping
    from shapely.ops import transform
    converter=Transformer.from_crs(PyCRS.from_user_input(source),PyCRS.from_user_input(destination),always_xy=True)
    return {'type':'FeatureCollection','features':[dict(feature,geometry=mapping(transform(converter.transform,shape(feature['geometry'])))) for feature in collection['features']]}
