"""ArcGIS-ready GeoTIFF rasters, PolyLineZ shapefiles and an import package.
GeoTIFF uses EPSG:4326, PixelIsArea, Float32 and explicit NoData (-9999).
Contour XYZ vertices are derived from the same cell-centered DEM as the rasters.
"""
import io
import json
import math
import struct
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, TiffImagePlugin
from .terrain import TerrainReader, validate_bbox
from .topography import TopographicEngine
from .terrain_analysis import terrain_metrics, drainage, metric_spacing, statistics, valid

NODATA=-9999.0
WKT='GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
UNITS={'dem':'m','filled_dem':'m','fill_depth':'m','slope':'degree','aspect':'degree clockwise from north; -1 = flat','hillshade':'0-255','tpi':'m','roughness':'m','flow_direction':'D8 code; 0 = outlet','flow_accumulation':'upstream cell count, excludes current cell'}


def geotiff(grid, bbox, title, unit):
    rows,cols=len(grid),len(grid[0]); west,south,east,north=bbox
    values=[float(v) if valid(v) else NODATA for row in grid for v in row]
    image=Image.frombytes('F',(cols,rows),struct.pack('<'+'f'*len(values),*values),'raw','F;32F')
    tags=TiffImagePlugin.ImageFileDirectory_v2()
    tags[33550]=((east-west)/cols,(north-south)/rows,0.0)
    tags[33922]=(0.0,0.0,0.0,float(west),float(north),0.0)
    tags[34735]=(1,1,0,5,1024,0,1,2,1025,0,1,1,2048,0,1,4326,2054,0,1,9102,4099,0,1,9001)
    tags[42113]=str(int(NODATA)); tags[270]=title+'; units='+unit+'; horizontal CRS=EPSG:4326'
    stream=io.BytesIO(); image.save(stream,format='TIFF',compression='tiff_deflate',tiffinfo=tags)
    return stream.getvalue()


def color_image(grid, kind, hillshade=None):
    rows,cols=len(grid),len(grid[0]); image=Image.new('RGBA',(cols,rows)); pixels=[]
    vals=[v for row in grid for v in row if valid(v)]
    scale=max((max(vals) if vals else 1),1)
    signed_scale=max((max(abs(v) for v in vals) if vals else 1),1)
    ramp=((0,(39,116,67)),(200,(111,156,81)),(500,(200,193,128)),(1000,(183,153,109)),(2000,(143,125,113)),(3500,(224,221,217)),(6000,(255,255,255)))
    for r in range(rows):
        for c in range(cols):
            v=grid[r][c]
            if not valid(v):pixels.append((0,0,0,0));continue
            if kind=='relief':
                if v<0:color=(112,164,190)
                else:
                    color=ramp[-1][1]
                    for (a,ca),(b,cb) in zip(ramp,ramp[1:]):
                        if a<=v<=b:
                            t=(v-a)/(b-a);color=tuple(round(x+(y-x)*t) for x,y in zip(ca,cb));break
                shade=hillshade[r][c] if hillshade and valid(hillshade[r][c]) else 180
                color=tuple(round(x*(.35+.65*shade/255)) for x in color)
            elif kind=='slope':
                color=(77,154,92) if v<5 else (172,188,91) if v<15 else (240,189,76) if v<30 else (219,107,65) if v<45 else (141,55,57)
            elif kind=='hillshade':color=(round(v),)*3
            elif kind=='aspect':
                import colorsys
                color=(180,180,180) if v<0 else tuple(round(x*255) for x in colorsys.hsv_to_rgb(v/360,.65,.85))
            elif kind=='flow_accumulation':
                t=math.log1p(max(0,v))/math.log1p(scale);color=(round(235*(1-t)),round(245*(1-t)+80*t),round(245*(1-t)+170*t))
            elif kind=='tpi':
                t=min(1,abs(v)/signed_scale);color=(round(235-140*t),round(235-90*t),round(235-35*t)) if v<0 else (round(235-45*t),round(235-125*t),round(235-160*t))
            else:
                t=min(1,max(0,v)/scale);color=(round(240-150*t),round(240-110*t),round(225-170*t))
            pixels.append((*color,255))
    image.putdata(pixels);return image


def rgb_geotiff(image,bbox):
    rows,cols=image.height,image.width; west,south,east,north=bbox
    tags=TiffImagePlugin.ImageFileDirectory_v2();tags[33550]=((east-west)/cols,(north-south)/rows,0.0);tags[33922]=(0.,0.,0.,float(west),float(north),0.)
    tags[34735]=(1,1,0,4,1024,0,1,2,1025,0,1,1,2048,0,1,4326,2054,0,1,9102)
    stream=io.BytesIO();image.save(stream,format='TIFF',compression='tiff_deflate',tiffinfo=tags);return stream.getvalue()


def shapefile(contours,wkt=WKT):
    features=contours['features'];records=[];index=[];offset=50
    xs=[];ys=[];zs=[]
    for number,feature in enumerate(features,1):
        pts=feature['geometry']['coordinates'];z=float(feature['properties']['elevation']);n=len(pts)
        xx=[p[0] for p in pts];yy=[p[1] for p in pts];xs.extend(xx);ys.extend(yy);zs.append(z)
        box=(min(xx),min(yy),max(xx),max(yy))
        content=struct.pack('<i4d3i',13,*box,1,n,0)+b''.join(struct.pack('<2d',*p) for p in pts)
        content+=struct.pack('<2d',z,z)+struct.pack('<'+'d'*n,*([z]*n))
        content+=struct.pack('<2d',-1e39,-1e39)+struct.pack('<'+'d'*n,*([-1e39]*n))
        words=len(content)//2;index.append(struct.pack('>2i',offset,words));records.append(struct.pack('>2i',number,words)+content);offset+=4+words
    box=(min(xs),min(ys),max(xs),max(ys)) if xs else (0.,0.,0.,0.)
    zrange=(min(zs),max(zs)) if zs else (0.,0.)
    def header(length):return struct.pack('>7i',9994,0,0,0,0,0,length)+struct.pack('<2i8d',1000,13,*box,*zrange,-1e39,-1e39)
    shp=header(offset)+b''.join(records);shx=header(50+len(index)*4)+b''.join(index)
    fields=[('ELEV_M',18,3),('INDEX_LN',1,0),('INTERVAL',12,3)]
    now=datetime.now(timezone.utc);hlen=32+32*len(fields)+1;rlen=1+sum(f[1] for f in fields)
    dbf=bytearray(struct.pack('<4BIHH20x',3,now.year-1900,now.month,now.day,len(features),hlen,rlen))
    for name,width,precision in fields:dbf+=struct.pack('<11sc4xBB14x',name.encode().ljust(11,b'\0'),b'N',width,precision)
    dbf+=b'\r'
    for f in features:
        p=f['properties'];dbf+=b' '+f"{p['elevation']:18.3f}{int(p['is_index']):1d}{p['interval']:12.3f}".encode('ascii')
    dbf+=b'\x1a'
    return {'contours.shp':shp,'contours.shx':shx,'contours.dbf':bytes(dbf),'contours.prj':wkt.encode(),'contours.cpg':b'UTF-8'}


def ascii_grid(grid,bbox):
    rows,cols=len(grid),len(grid[0]);west,south,east,north=bbox;cell=(east-west)/cols
    if not math.isclose(cell,(north-south)/rows,rel_tol=1e-8):raise ValueError('ASCII grid requires equal angular cell sizes.')
    header=f'ncols {cols}\nnrows {rows}\nxllcorner {west:.12f}\nyllcorner {south:.12f}\ncellsize {cell:.12f}\nNODATA_value -9999\n'
    return (header+'\n'.join(' '.join(f'{v:.4f}' if valid(v) else '-9999' for v in row) for row in grid)+'\n').encode()


def build_package(bbox, output_dir, resolution=256, interval=25, source='terrain', offline=False, azimuth=315, altitude=45, z_factor=1, hydrology=True, above_sea_only=True, target_crs='EPSG:4326'):
    validate_bbox(bbox)
    if isinstance(resolution,bool) or resolution not in (64,128,256,512):raise ValueError('Use resolution 64, 128, 256 or 512.')
    for val,low,high in ((interval,.1,10000),(azimuth,0,360),(altitude,1,90),(z_factor,.1,10)):
        if isinstance(val,bool) or not isinstance(val,(int,float)) or not math.isfinite(val) or not low<=val<=high:raise ValueError('Invalid analysis parameters.')
    if not isinstance(hydrology,bool) or not isinstance(above_sea_only,bool):raise ValueError('Boolean analysis options required.')
    west,south,east,north=bbox;cell=max(east-west,north-south)/resolution
    cols=math.ceil((east-west)/cell-1e-9);rows=math.ceil((north-south)/cell-1e-9)
    if min(rows,cols)<3:raise ValueError("Region is too narrow for a 3x3 terrain analysis window.")
    bounds=(west,north-rows*cell,west+cols*cell,north)
    if bounds[1]<-85 or bounds[2]>180:raise ValueError('Aligned grid extends outside supported bounds. Select a smaller region.')
    centers=(west+cell/2,bounds[1]+cell/2,bounds[2]-cell/2,north-cell/2)
    dem=TerrainReader(source,offline).grid(centers,rows,cols)
    grid=dem['grid'];dx,dy=metric_spacing(bounds,rows,cols)
    products={'dem':grid,**terrain_metrics(grid,dx,dy,azimuth,altitude,z_factor)}
    if hydrology:products.update(drainage(grid,dx,dy))
    contours=TopographicEngine.generate_contour_geojson(centers,interval,dem=dem,above_sea_only=above_sea_only)
    token='arcgis_'+uuid.uuid4().hex[:12];folder=Path(output_dir)/token;folder.mkdir(parents=True)
    previews={}
    for name in ('relief','hillshade','slope','aspect','tpi','roughness','flow_accumulation'):
        if name!='relief' and name not in products:continue
        image=color_image(grid if name=='relief' else products[name],name,products['hillshade'])
        image.save(folder/(name+'.png'))
        previews[name]='/exports/'+token+'/'+name+'.png'
        if name=='relief':relief=image
    summary={name:statistics(values) for name,values in products.items()}
    summary['aspect']['mean']=None  # Compass bearings do not have an arithmetic mean.
    if 'flow_direction' in summary:summary['flow_direction']['mean']=None
    metadata={'created_utc':datetime.now(timezone.utc).isoformat(),'crs':'EPSG:4326','horizontal_units':'degree','elevation_units':'m',
              'vertical_datum':'Source terrain vertical reference; not independently transformed.',
              'requested_bbox':bbox,'bbox':bounds,'rows':rows,'cols':cols,'cell_size_degrees':cell,
              'ground_cell_size_m':{'east_west':dx[rows//2],'north_south':dy[rows//2]},
              'source':dem['source'],'source_pixel_size_m':dem.get('source_pixel_size_m'),'attribution':dem.get('attribution'),
              'attribution_url':dem.get('attribution_url'),'nodata_samples':dem['nodata_samples'],'interval':interval,
              'above_sea_only':above_sea_only,'azimuth':azimuth,'altitude':altitude,'hillshade_z_factor':z_factor,
              'algorithms':{'derivatives':'Horn 3x3 with WGS84 per-row metric spacing, full valid neighborhood; border=NoData',
                            'aspect':'Downhill compass bearing, north=0 east=90; flat=-1',
                            'tpi':'Center minus mean of eight neighboring cells (3x3)',
                            'roughness':'Max minus min in 3x3 neighborhood, meters',
                            'hydrology':'Priority-Flood fill, D8 steepest descent, flood-parent flat routing; edges and NoData boundaries are outlets' if hydrology else 'not computed',
                            'flow_direction_codes':{'E':1,'SE':2,'S':4,'SW':8,'W':16,'NW':32,'N':64,'NE':128,'outlet':0},
                            'accumulation':'Number of upstream cells, excluding current cell; not discharge or flood depth'},
              'statistics':summary,'contour_lines':len(contours['features'])}
    readme='''ARCGIS TOPOGRAPHIC PACKAGE / حزمة الخرائط الطبوغرافية

1. Extract this ZIP to a local folder. Keep contours.shp, .shx, .dbf, .prj, .cpg together.
2. ArcGIS Pro / ArcMap: Add Data > add relief.tif and contours.shp for a topographic view.
3. Add dem.tif for elevation analysis; slope.tif is in degrees, aspect.tif is a compass bearing.
4. Optional ArcGIS Pro loader: first edit PACKAGE in load_in_arcgis.py to the extracted folder. Then run it in the Python window with exec(open(r"FULL_PATH/load_in_arcgis.py", encoding="utf-8").read()).
5. All files use WGS84 EPSG:4326 (longitude/latitude degrees), elevation values in meters.
   For metric GIS operations, use Project Raster to your local UTM CRS. Do not merely Define Projection as UTM.
6. dem.asc is an optional ESRI ASCII grid. Import using Copy Raster or ASCII To Raster. Its .prj accompanies it.
7. Pixel registration: Area; upper-left outer corner and pixel scale are embedded in every GeoTIFF.
8. NoData=-9999. Derivative borders and incomplete 3x3 windows are NoData. Flat aspect=-1.
9. Hydrology is local to this extraction: boundary and NoData cells act as outlets. Accumulation counts upstream cells, excludes the current cell and is not a flood-depth or discharge model.
10. The filled DEM is a separate analysis product. Original elevations and contours are never replaced by depression-filled heights.
11. The extraction may pad the east/south edge by less than one pixel to align square angular cells. See metadata.json for exact bounds, spacing, native source pixel size and attribution.

بالعربية: فك ضغط الحزمة، ثم أضف relief.tif و contours.shp إلى ArcGIS. استعمل dem.tif للتحليل الرقمي، وراجع metadata.json لمعرفة دقة المصدر والإسناد. لا تغير تعريف الإسقاط إلى UTM؛ استخدم أداة Project Raster لإعادة الإسقاط فعلياً.
'''
    loader='''from pathlib import Path
import arcpy
# In ArcGIS Pro: replace PACKAGE with the extracted folder, then run this script.
PACKAGE = Path(r"REPLACE_WITH_EXTRACTED_PACKAGE_FOLDER")
if not PACKAGE.is_dir():
    raise ValueError("Set PACKAGE to the extracted ZIP folder before running this script.")
aprx = arcpy.mp.ArcGISProject("CURRENT")
m = aprx.activeMap or (aprx.listMaps()[0] if aprx.listMaps() else aprx.createMap("Topography"))
for filename in ("dem.tif", "slope.tif", "aspect.tif", "hillshade.tif", "relief.tif", "contours.shp"):
    layer = m.addDataFromPath(str(PACKAGE / filename))
    layer.visible = filename in ("relief.tif", "contours.shp")
'''
    files={name+'.tif':geotiff(values,bounds,name,UNITS[name]) for name,values in products.items()}
    files['relief.tif']=rgb_geotiff(relief,bounds)
    projected_contours=contours;export_grid=grid;export_bounds=bounds;export_wkt=WKT
    if target_crs!='EPSG:4326':
        from .gis_common import target_crs as resolve_crs,warped_bytes,geojson_transform
        from rasterio.io import MemoryFile
        import rasterio
        crs,label=resolve_crs(target_crs,bounds)
        files['dem.tif'],reference=warped_bytes(files['dem.tif'],crs)
        for filename in list(files):
            if filename!='dem.tif':files[filename],_=warped_bytes(files[filename],crs,reference,nearest=filename in ('aspect.tif','flow_direction.tif','flow_accumulation.tif'))
        with MemoryFile(files['dem.tif']) as memory,memory.open() as src:
            array=src.read(1,masked=True);export_grid=__import__('numpy').where(__import__('numpy').ma.getmaskarray(array),float('nan'),array.data).tolist()
            export_bounds=list(src.bounds);metadata.update(rows=src.height,cols=src.width,raster_bbox=export_bounds,raster_cell_size=[src.transform.a,-src.transform.e])
        projected_contours=geojson_transform(contours,'EPSG:4326',crs.to_wkt());export_wkt=crs.to_wkt()
        metadata.update(crs=label,horizontal_units='m' if crs.is_projected else 'degree',preview_crs='EPSG:4326',analysis_rows=rows,analysis_cols=cols)
        metadata['reprojection']='Actual GDAL resampling; categorical directions, aspect and cell counts use nearest neighbor.'
        if label.startswith('EPSG:307'):metadata['datum_operation']={'operation':'EPSG:1253','accuracy_m':44,'translation_m':[-186,-93,310]}
        readme='Raster and Shapefile CRS: '+label+'; actual coordinates have been reprojected. GeoJSON and PNG previews remain WGS84. See metadata.json.\n'+readme.replace('5. All files use WGS84 EPSG:4326 (longitude/latitude degrees), elevation values in meters.','5. Rasters and Shapefile use '+label+'; GeoJSON remains WGS84. Elevations are meters.').replace('   For metric GIS operations, use Project Raster to your local UTM CRS. Do not merely Define Projection as UTM.','')
    files['dem.asc']=ascii_grid(export_grid,export_bounds);files['dem.prj']=export_wkt
    files.update(shapefile(projected_contours,export_wkt))
    zip_path=Path(output_dir)/(token+'.zip')
    with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,content in files.items():archive.writestr(name,content)
        archive.writestr('contours.geojson',json.dumps(contours,ensure_ascii=False))
        archive.writestr('metadata.json',json.dumps(metadata,ensure_ascii=False,indent=2,allow_nan=False))
        archive.writestr('README.txt',readme);archive.writestr('load_in_arcgis.py',loader)
    return {'download_url':'/exports/'+zip_path.name,'metadata':metadata,'previews':previews,'size_mb':round(zip_path.stat().st_size/1024**2,2)}
