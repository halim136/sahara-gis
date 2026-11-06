"""JSON-stdin dispatcher for the local GIS workbench."""
import sys,json,re,io,math,uuid
from pathlib import Path
from PIL import Image,ImageOps
from .gis_common import APP,EXPORTS,output_file,download
UPLOADS=APP/'cache/studio'

def uploaded(identifier,kind,extension=None):
    if not re.fullmatch(r'[a-f0-9]{32}',str(identifier)):raise ValueError('Invalid upload identifier.')
    suffix={'scan':'.png','gpkg':'.gpkg','dem':'.tif','project':'.sasgis','raster':'.tif','photo':'.jpg'}.get(kind)
    if kind=='vector':
        allowed={'.kml','.kmz','.gpx','.geojson','.json','.zip','.sml','.db3'}
        suffix=str(extension or '').lower()
        if suffix not in allowed:raise ValueError('Unsupported vector upload.')
        path=UPLOADS/(str(identifier)+suffix)
        if not path.is_file():raise ValueError('Upload not found.')
        return path
    if not suffix:raise ValueError('Unsupported upload kind.')
    root=APP/'cache/terrain/geotiff' if kind=='dem' else UPLOADS
    path=root/(identifier+suffix)
    if not path.is_file():raise ValueError('Upload not found.')
    return path

def inspect_upload(p):
    kind=p['kind'];path=uploaded(p['id'],kind,p.get('extension'))
    if kind=='vector':
        from .vector_formats import parse_vector_file
        result=parse_vector_file(path);result.update(id=p['id'],name=p.get('name','Vector'))
        return result
    if kind=='raster':
        from .field_raster import raster_import
        return raster_import(path,p.get('name','Local GeoTIFF'))
    if kind=='photo':
        from .field_raster import photo_import
        return photo_import(path,p.get('name','Photo'))
    if kind=='dem':
        from .dem_catalog import inspect_dem
        return inspect_dem(path,p.get('name'))
    if kind=='project':return {'id':p['id'],'name':p.get('name')}
    if kind=='gpkg':return {'id':p['id'],'name':p.get('name')}
    with Image.open(path) as original:
        if original.width*original.height>64000000:raise ValueError('Images are limited to 64 million pixels.')
        image=ImageOps.exif_transpose(original).convert('RGBA')
    image.save(path)
    preview=EXPORTS/(p['id']+'.png');EXPORTS.mkdir(parents=True,exist_ok=True);image.save(preview)
    return {'id':p['id'],'width':image.width,'height':image.height,'preview':download(preview)}

def cached_crop(p):
    from .tile_storage import FileSystemStorage,IMAGE_EXTENSIONS
    from .projections import lon_lat_to_tile
    from .terrain import validate_bbox
    from pyproj import Transformer
    bbox=p['bbox'];validate_bbox(bbox);z=int(p.get('zoom',18))
    if not 0<=z<=22:raise ValueError('Invalid imagery zoom.')
    w,s,e,n=bbox;npx=256*2**z
    f=Transformer.from_crs(4326,3857,always_xy=True);limit=20037508.342789244
    def pixel(lon,lat):
        x,y=f.transform(lon,lat);return (x+limit)/(2*limit)*npx,(limit-y)/(2*limit)*npx
    left,top=pixel(w,n);right,bottom=pixel(e,s)
    x0,y0=math.floor(left/256),math.floor(top/256);x1,y1=math.floor(right/256),math.floor(bottom/256)
    if (x1-x0+1)*(y1-y0+1)>64 or min(right-left,bottom-top)<16:raise ValueError('Select one building with a margin at a suitable zoom (maximum 64 tiles).')
    image=Image.new('RGB',((x1-x0+1)*256,(y1-y0+1)*256));storage=FileSystemStorage()
    for y in range(y0,y1+1):
        for x in range(x0,x1+1):
            data=next((raw for ext in IMAGE_EXTENSIONS if (raw:=storage.load_tile(p['source_id'],z,x,y,ext))),None)
            if not data:raise ValueError('Imagery is missing from cache_gmt. Display or download this small region first.')
            tile=Image.open(io.BytesIO(data)).convert('RGB');image.paste(tile,((x-x0)*256,(y-y0)*256))
    image=image.crop((round(left-x0*256),round(top-y0*256),round(right-x0*256),round(bottom-y0*256)))
    # Rectify Mercator rows onto a geographic rectangle before converting pixels to lon/lat.
    import numpy as np,cv2
    image.thumbnail((1600,1600));width,height=image.size
    xs=np.linspace(w,e,width);ys=np.linspace(n,s,height);mapx=np.tile(np.arange(width,dtype='float32'),(height,1));mapy=np.array([(pixel(w,float(lat))[1]-top)/(bottom-top)*(height-1) for lat in ys],dtype='float32')[:,None].repeat(width,axis=1)
    image=Image.fromarray(cv2.remap(np.array(image),mapx,mapy,cv2.INTER_LINEAR))
    path=output_file('roof_crop','.png');image.save(path);return {'path':path,'preview':download(path),'bbox':bbox}

def cache_scan(p):
    from .tile_storage import FileSystemStorage,IMAGE_EXTENSIONS
    from .projections import lon_lat_to_tile
    from .terrain import validate_bbox
    validate_bbox(p['bbox']);storage=FileSystemStorage();bad=[];checked=0;missing=0
    w,s,e,n=p['bbox'];zooms=p['zooms']
    if not isinstance(zooms,list) or not zooms or len(zooms)>24 or any(isinstance(z,bool) or not isinstance(z,int) or not 0<=z<=22 for z in zooms):raise ValueError('Invalid zooms.')
    planned=0
    for z in sorted(set(zooms)):
        x0,y1=lon_lat_to_tile(w,s,z);x1,y0=lon_lat_to_tile(e,n,z);planned+=(x1-x0+1)*(y1-y0+1)
        if planned>10000:raise ValueError('Scan at most 10,000 selected tiles.')
        for y in range(y0,y1+1):
            for x in range(x0,x1+1):
                paths=[Path(storage.get_tile_path(p['source_id'],z,x,y,ext)) for ext in IMAGE_EXTENSIONS];found=False;valid=False
                for path in paths:
                    if not path.is_file():continue
                    found=True
                    try:
                        with Image.open(path) as image:image.verify()
                        with Image.open(path) as image:image.load();valid=image.size==(256,256)
                        if valid:break
                    except Exception:pass
                if not found:missing+=1
                elif not valid:bad.append({'z':z,'x':x,'y':y})
                checked+=int(found)
    return {'statistics':{'checked':checked,'missing':missing,'damaged':len(bad)},'damaged':bad,'note':'Original files are preserved; repair replaces a tile only after a download succeeds.'}

def dispatch(operation,p):
    if operation=='inspect':return inspect_upload(p)
    if operation=='field_track':
        from .field_tracks import operate
        return operate(p)
    if operation=='field_gpx':
        from .field_tracks import parse_gpx
        return parse_gpx(p['content'])
    if operation in ('field_grid','field_coordinates','field_coverage','field_route'):
        from . import field_planning as f
        return {'field_grid':f.metric_grid,'field_coordinates':f.batch_coordinates,'field_coverage':f.coverage,'field_route':f.route}[operation](p)
    if operation=='field_package':
        from .field_raster import field_package
        return field_package(p)
    if operation in ('project_save','project_list','project_load','project_backups','project_pack'):
        from . import projects
        return {'project_save':projects.save_project,'project_list':lambda p:projects.list_projects(),'project_load':projects.load_project,'project_backups':projects.backups,'project_pack':projects.pack_project}[operation](p)
    if operation=='project_import':
        from .projects import unpack_project
        return unpack_project(uploaded(p['id'],'project'))
    if operation in ('catalog_list','catalog_import','catalog_import_marks','catalog_query'):
        from . import sheet_catalog
        return {'catalog_list':lambda p:sheet_catalog.list_catalogs(),'catalog_import':sheet_catalog.import_catalog,'catalog_import_marks':sheet_catalog.import_marks_catalog,'catalog_query':sheet_catalog.query_catalog}[operation](p)
    if operation in ('qa_checkpoints','qa_dem','qa_topology','validate_edit'):
        from . import pro_quality
        return {'qa_checkpoints':pro_quality.checkpoints,'qa_dem':pro_quality.dem_quality,'qa_topology':pro_quality.topology,'validate_edit':pro_quality.validate_edit}[operation](p)
    if operation=='atlas':
        from .atlas import atlas
        return atlas(p)
    if operation=='print_split':
        from .print_split import split_print
        return split_print(p)
    if operation=='print3d':
        from .print3d import export_print
        return export_print(p)
    if operation=='sheets25k':
        from .map_sheets import sheet_grid
        return sheet_grid(p['bbox'],p.get('datum','nord_sahara'),p.get('export',False))
    if operation=='terrain_prepare':
        from .terrain import CACHE
        resolution=p.get('resolution',129)
        if isinstance(resolution,bool) or resolution not in (65,129,257):raise ValueError('Select a 65, 129 or 257 vertex terrain grid.')
        source=p.get('source','terrain');offline=p.get('offline',False)
        if not isinstance(offline,bool):raise ValueError('Offline mode must be boolean.')
        # Use exactly the scene request, then verify it without network access.
        from .scene3d import build_scene
        build_scene(p['bbox'],source,offline,resolution)
        scene=build_scene(p['bbox'],source,True,resolution)
        return {'ready':True,'bbox':p['bbox'],'resolution':resolution,'metadata':scene['metadata'],'elevation_cache':str(CACHE.resolve())}
    if operation=='scene3d':
        from .scene3d import build_scene
        return build_scene(p['bbox'],p.get('source','terrain'),p.get('offline',False),p.get('resolution',129),p.get('buildings'),p.get('building_height',10))
    if operation=='dem_list':
        from .dem_catalog import list_dems
        return {'dems':list_dems()}
    if operation=='dem_mosaic':
        from .dem_catalog import mosaic
        return mosaic(p['ids'],p.get('name','Mosaic'))
    if operation=='dem_crop':
        from .dem_catalog import dem_path,inspect_dem
        import rasterio
        from rasterio.windows import from_bounds,Window
        from rasterio.warp import transform_bounds
        from .terrain import validate_bbox
        validate_bbox(p['bbox'])
        with rasterio.open(dem_path(p['id'])) as src:
            bounds=transform_bounds('EPSG:4326',src.crs,*p['bbox'],densify_pts=21);window=from_bounds(*bounds,src.transform).round_offsets().round_lengths().intersection(Window(0,0,src.width,src.height))
            if window.width<2 or window.height<2:raise ValueError('Crop has no valid overlap.')
            out=dem_path(uuid.uuid4().hex);profile=src.profile.copy();profile.update(width=int(window.width),height=int(window.height),transform=src.window_transform(window),compress='deflate')
            with rasterio.open(out,'w',**profile) as dst:
                # Windowed copy avoids loading a full high-resolution DEM into memory.
                for _,block in dst.block_windows(1):
                    data=src.read(window=Window(window.col_off+block.col_off,window.row_off+block.row_off,block.width,block.height));dst.write(data,window=block)
        return inspect_dem(out,p.get('name','Cropped DEM'))
    if operation in ('watershed','viewshed','volume'):
        from .studio_analysis import run_analysis
        return run_analysis(operation,p)
    if operation=='veg_index':
        from .studio_analysis import vegetation_index
        return vegetation_index(p)
    if operation=='cogo':
        from .cogo import cogo
        return cogo(p)
    if operation=='geom_ops':
        from .geometry_ops import geom_ops
        return geom_ops(p)
    if operation=='terrain_path':
        from .terrain_path import terrain_path
        return terrain_path(p)
    if operation=='digitize_raster':
        from .map_digitize import digitize
        return digitize({**p,'path':uploaded(p['id'],p.get('kind','raster'))})
    if operation=='georeference':
        from .georeference import georeference
        return georeference(uploaded(p['id'],'scan'),p['gcps'],p.get('crs','EPSG:4326'))
    if operation=='layout':
        from .map_layout import create_layout
        return create_layout(p)
    if operation=='buildings':
        from .buildings import orthogonalize,roof_proposal,save_proposal
        if p.get('method')=='validate':
            from shapely.geometry import shape
            from shapely.ops import transform
            from .buildings import local_transform
            collection=p['geojson']
            for feature in collection['features']:
                geometry=shape(feature['geometry'])
                if geometry.geom_type!='Polygon' or not geometry.is_valid or geometry.is_empty:raise ValueError('Building polygon must not intersect itself. Correct the vertices before saving.')
                forward,_=local_transform(list(geometry.exterior.coords));feature.setdefault('properties',{}).update(area_m2=transform(forward.transform,geometry).area,review_required=False)
            return save_proposal(collection)
        if p.get('method')=='image':
            if p.get('id'):path=uploaded(p['id'],'scan');crop=None
            else:crop=cached_crop(p);path=crop['path']
            result=save_proposal(roof_proposal(path,p['bbox'],p.get('rectangle',False)))
            if crop:result.update(preview=crop['preview'],bbox=p['bbox'])
            return result
        return save_proposal(orthogonalize(p['points'],p.get('rectangle',False)))
    if operation=='gpkg_export':
        from .geopackage import export_package
        return export_package(p.get('features'),p.get('source_id'),p.get('bbox'),p.get('zooms'))
    if operation=='gpkg_import':
        from .geopackage import read_package
        return read_package(uploaded(p['id'],'gpkg'),bool(p.get('import_tiles',False)),p.get('source_id'))
    if operation=='cache_scan':return cache_scan(p)
    raise ValueError('Unknown GIS operation.')

if __name__=='__main__':
    try:
        payload=json.load(sys.stdin);result=dispatch(sys.argv[1],payload);print(json.dumps(result,ensure_ascii=False,allow_nan=False))
    except Exception as error:
        print(str(error),file=sys.stderr);sys.exit(1)
