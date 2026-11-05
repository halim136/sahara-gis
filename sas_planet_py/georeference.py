"""Affine least-squares GCP registration with explicit fitting residuals."""
import json,math
import numpy as np
import rasterio
from rasterio.transform import Affine,from_bounds
from rasterio.warp import reproject,Resampling
from PIL import Image,ImageOps
from .gis_common import output_file,download,target_crs

def fit_affine(gcps):
    if not isinstance(gcps,list) or not 3<=len(gcps)<=100:raise ValueError('Provide 3–100 control points.')
    values=np.asarray([[g[k] for k in ('col','row','x','y')] for g in gcps],dtype=float)
    if not np.isfinite(values).all():raise ValueError('Control coordinates must be finite.')
    A=np.column_stack((values[:,:2],np.ones(len(values))))
    # Centering keeps conditioning meaningful for large UTM coordinates.
    if np.linalg.matrix_rank(A)<3:raise ValueError('Control points must not be collinear.')
    model=np.linalg.lstsq(A,values[:,2:],rcond=None)[0]
    predicted=A@model;errors=np.linalg.norm(predicted-values[:,2:],axis=1)
    affine=Affine(model[0,0],model[1,0],model[2,0],model[0,1],model[1,1],model[2,1])
    if abs(affine.determinant)<1e-12:raise ValueError('Control points produce a collapsed map.')
    return affine,{'rmse':float(np.sqrt(np.mean(errors**2))),'residuals':[{'index':i+1,'dx':float(predicted[i,0]-values[i,2]),'dy':float(predicted[i,1]-values[i,3]),'error':float(errors[i])} for i in range(len(values))],'points':len(values),'degrees_of_freedom':2*len(values)-6,'warning':'Fitting residuals are not independent positional accuracy. Three points fit exactly.'}

def georeference(image_path,gcps,crs='EPSG:4326'):
    transform,report=fit_affine(gcps);dst_crs,label=target_crs(crs)
    image=ImageOps.exif_transpose(Image.open(image_path)).convert('RGBA');width,height=image.size
    if width*height>64000000:raise ValueError('Image exceeds 64 million pixels.')
    for g in gcps:
        if not 0<=g['col']<=width or not 0<=g['row']<=height:raise ValueError('Control point outside image.')
    corners=[transform*p for p in ((0,0),(width,0),(width,height),(0,height))];xx,yy=zip(*corners)
    west,south,east,north=min(xx),min(yy),max(xx),max(yy)
    pixel=math.sqrt(abs(transform.determinant));cols=math.ceil((east-west)/pixel-1e-7);rows=math.ceil((north-south)/pixel-1e-7)
    if rows*cols>64000000:raise ValueError('Warped image too large; check control coordinates.')
    target=from_bounds(west,south,east,north,cols,rows);data=np.moveaxis(np.array(image),2,0)
    out=output_file('registered','.tif')
    with rasterio.open(out,'w',driver='GTiff',width=cols,height=rows,count=4,dtype='uint8',crs=dst_crs,transform=target,compress='deflate',photometric='RGB') as dst:
        from rasterio.enums import ColorInterp
        dst.colorinterp=(ColorInterp.red,ColorInterp.green,ColorInterp.blue,ColorInterp.alpha)
        for b in range(4):
            reproject(data[b],rasterio.band(dst,b+1),src_transform=transform,src_crs=dst_crs,dst_transform=target,dst_crs=dst_crs,resampling=Resampling.nearest if b==3 else Resampling.bilinear)
        dst.update_tags(GCP_FIT_RMSE=str(report['rmse']),GCP_CRS=label)
    report.update(crs=label,units='degree' if dst_crs.is_geographic else 'm',transform=list(transform)[:6],bbox=[west,south,east,north],gcps=gcps)
    report_path=out.with_suffix('.json');report_path.write_text(json.dumps(report,indent=2),encoding='utf8')
    return {'files':[{'name':'Registered GeoTIFF','url':download(out)},{'name':'GCP residual report','url':download(report_path)}],'statistics':report}
