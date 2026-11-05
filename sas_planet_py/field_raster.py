"""Local-only georeferenced raster previews, GPS photos and field map packages."""
import json,math,shutil,zipfile,io,uuid
from pathlib import Path
import numpy as np
import rasterio
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_bounds
from rasterio.transform import from_bounds
from rasterio.enums import Resampling,ColorInterp
from PIL import Image,ImageOps
from .gis_common import EXPORTS,output_file,download
def local_export(url):
    if not isinstance(url,str) or not url.startswith('/exports/'):raise ValueError('Use a local exported raster.')
    path=(EXPORTS/url[len('/exports/'):]).resolve()
    if not path.is_relative_to(EXPORTS.resolve()) or not path.is_file():raise ValueError('Local exported file not found.')
    return path
def raster_import(path,name):
    with rasterio.open(path) as src:
        if src.driver!='GTiff' or not src.crs:raise ValueError('Select a georeferenced GeoTIFF with a defined CRS.')
        if src.count not in (1,2,3,4):raise ValueError('Use a grayscale, palette or RGB/RGBA GeoTIFF.')
        bounds=transform_bounds(src.crs,'EPSG:3857',*src.bounds,densify_pts=21)
        if not all(math.isfinite(v) for v in bounds) or min(bounds[2]-bounds[0],bounds[3]-bounds[1])<=0:raise ValueError('Raster cannot be displayed in Web Mercator.')
        w,s,e,n=bounds;factor=min(2048/max(e-w,n-s),src.width/(e-w),src.height/(n-s));width=max(1,round((e-w)*factor));height=max(1,round((n-s)*factor))
        with WarpedVRT(src,crs='EPSG:3857',transform=from_bounds(*bounds,width,height),width=width,height=height,resampling=Resampling.nearest if src.colorinterp[0]==ColorInterp.palette else Resampling.bilinear) as vrt:
            data=vrt.read();mask=vrt.dataset_mask()
        rgb=[]
        if src.count==1:
            try:
                cmap=src.colormap(1);lut=np.zeros((65536,4),dtype='uint8')
                for key,color in cmap.items():
                    if 0<=key<len(lut):lut[key]=color
                rgba=lut[np.clip(data[0],0,65535).astype('int32')];rgba[:,:,3]=np.minimum(rgba[:,:,3],mask)
            except ValueError:rgba=None
        else:rgba=None
        if rgba is None:
            for band in (data[:3] if src.count>=3 else np.repeat(data[:1],3,axis=0)):
                finite=band[(mask>0)&np.isfinite(band)]
                if not finite.size:raise ValueError('Raster has no valid display pixels.')
                lo,hi=(0,255) if band.dtype=='uint8' else np.percentile(finite,[2,98])
                rgb.append(np.nan_to_num(np.clip((band-lo)/max(float(hi-lo),1e-9)*255,0,255)).astype('uint8'))
            alpha=mask
            if src.count in (2,4):alpha=np.minimum(alpha,np.clip(data[-1],0,255).astype('uint8'))
            rgba=np.dstack([*rgb,alpha])
        geographic=transform_bounds(3857,4326,*bounds);report={'name':name,'crs':src.crs.to_string(),'width':src.width,'height':src.height,'bands':src.count,'bbox':list(geographic),'display_crs':'EPSG:3857','display_size':[width,height],'display_resampled':True}
    preview=output_file('local_map','.png');Image.fromarray(rgba).save(preview)
    original=preview.with_suffix('.tif');shutil.copy2(path,original)
    return {'layer':{'id':uuid.uuid4().hex,'kind':'image','name':name,'visible':True,'opacity':1,'url':download(preview),'original':download(original),'bbox':list(geographic),'metadata':report},'statistics':report}
def photo_import(path,name):
    with Image.open(path) as src:
        if src.width*src.height>64000000:raise ValueError('Photo is too large.')
        exif=src.getexif();gps=exif.get_ifd(34853) if 34853 in exif else {};lon=lat=direction=None
        def deg(v):return float(v[0])+float(v[1])/60+float(v[2])/3600
        if gps.get(2) and gps.get(4):
            lat=deg(gps[2])*(-1 if gps.get(1)=='S' else 1);lon=deg(gps[4])*(-1 if gps.get(3)=='W' else 1)
            if not -85<=lat<=85 or not -180<=lon<=180:lon=lat=None
        if gps.get(17) is not None:direction=float(gps[17])
        image=ImageOps.exif_transpose(src).convert('RGB');image.thumbnail((1280,1280));out=output_file('field_photo','.jpg');image.save(out,quality=88)
        return {'name':name,'url':download(out),'lon':lon,'lat':lat,'direction':direction,'captured':str(exif.get(36867,exif.get(306,''))),'source':'EXIF GPS' if lat is not None else 'Manual coordinates required'}
def field_package(p):
    layer=p['layer'];bbox=layer['bbox']
    if len(bbox)!=4:raise ValueError('Invalid raster bounds.')
    image=local_export(layer['url'])
    with Image.open(image) as original:
        source=original.convert('RGBA');width,height=source.size
        columns=math.ceil(width/1024);rows=math.ceil(height/1024)
        if columns*rows>100:raise ValueError('Garmin package exceeds 100 tiles.')
        # Overlay source pixels are Web Mercator; resample to geographic pixels
        # before writing KML LatLonBox (which is geographic, not Mercator).
        from rasterio.warp import reproject
        w,s,e,n=bbox;merc=transform_bounds(4326,3857,*bbox);src=np.moveaxis(np.asarray(source),-1,0);dst=np.zeros_like(src)
        for band in range(4):reproject(src[band],dst[band],src_transform=from_bounds(*merc,width,height),src_crs=3857,dst_transform=from_bounds(*bbox,width,height),dst_crs=4326,resampling=Resampling.bilinear)
        geographic=Image.fromarray(np.moveaxis(dst,0,-1))
    from xml.etree.ElementTree import Element,SubElement,tostring
    kml=Element('kml',xmlns='http://www.opengis.net/kml/2.2');doc=SubElement(kml,'Document')
    path=output_file('field_maps','.kmz' if p.get('format')=='kmz' else '.zip')
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
        for r in range(rows):
            for c in range(columns):
                x0,y0=c*1024,r*1024;x1,y1=min(width,x0+1024),min(height,y0+1024);tile=geographic.crop((x0,y0,x1,y1));rgb=Image.new('RGB',tile.size,'white');rgb.paste(tile,mask=tile.getchannel('A'));buf=io.BytesIO();rgb.save(buf,format='JPEG',quality=92);name=f'images/R{r+1}_C{c+1}.jpg';archive.writestr(name,buf.getvalue())
                overlay=SubElement(doc,'GroundOverlay');SubElement(overlay,'name').text=f'R{r+1} C{c+1}';SubElement(SubElement(overlay,'Icon'),'href').text=name;box=SubElement(overlay,'LatLonBox')
                for key,value in [('west',w+(e-w)*x0/width),('east',w+(e-w)*x1/width),('north',n-(n-s)*y0/height),('south',n-(n-s)*y1/height),('rotation',0)]:SubElement(box,key).text=str(value)
        archive.writestr('doc.kml',tostring(kml,encoding='utf8',xml_declaration=True))
        from .field_tracks import export_gpx
        archive.writestr('tracks.gpx',export_gpx(p.get('marks',[])))
        if p.get('format')!='kmz':
            archive.writestr('map.png',image.read_bytes())
            if layer.get('original'):archive.write(local_export(layer['original']),'map.tif')
            archive.writestr('metadata.json',json.dumps({'layer':layer,'map_png_crs':'EPSG:3857','kml_tiles_crs':'EPSG:4326'},ensure_ascii=False))
        archive.writestr('README.txt','Garmin: copy KMZ to Garmin/CustomMaps on a compatible device; tile limits vary by model. Field ZIP: GeoTIFF + KML/KMZ-compatible tiles + GPX; import supported files in your mobile GIS app. Not a proprietary OruxMaps database. Transparent pixels are flattened to white in Garmin JPEG tiles.')
    return {'files':[{'name':path.name,'url':download(path)}],'statistics':{'tiles':rows*columns,'max_tile_pixels':1024,'bbox':bbox,'garmin_device_limits_require_check':True}}
