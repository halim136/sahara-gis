"""Watertight terrain relief for 3D printing: binary STL and core 3MF, millimeters.
Buildings are rasterized into a single height field; NoData is never fabricated.
"""
import io,json,math,struct,zipfile
from collections import Counter
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon
from shapely import intersects_xy
from .gis_common import output_file,download


def number(value,low,high,label):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:raise ValueError(label+' outside allowed range.')
    return float(value)

def resample(array,size):
    source=array.shape[0];old=np.arange(source);new=np.linspace(0,source-1,size)
    across=np.array([np.interp(new,old,row) for row in array]);return np.array([np.interp(new,old,col) for col in across.T]).T

def make_solid(scene,longest_side_mm=150,base_mm=3,vertical_exaggeration=1,resolution=257,include_buildings=True,scale_denominator=0,bed_mm=(220,220,250),allow_oversize=False):
    longest_side_mm=number(longest_side_mm,10,1500,'Model side');base_mm=number(base_mm,1,100,'Base thickness');vertical_exaggeration=number(vertical_exaggeration,.1,10,'Vertical exaggeration');scale_denominator=number(scale_denominator,0,1e8,'Print scale')
    if not isinstance(resolution,int) or resolution not in (65,129,257,513) or isinstance(resolution,bool):raise ValueError('Print grid must be 65,129,257 or 513.')
    if not isinstance(include_buildings,bool) or not isinstance(allow_oversize,bool):raise ValueError('Boolean print options required.')
    if not isinstance(bed_mm,(list,tuple)) or len(bed_mm)!=3:raise ValueError('Provide printer width, depth and height.')
    bed_mm=[number(v,10,2000,'Printer dimensions') for v in bed_mm]
    meta=scene.get('metadata',{});n=meta.get('resolution');span=number(meta.get('span_m'),1,100000,'Scene span')
    if not isinstance(n,int) or n not in (65,129,257):raise ValueError('Invalid terrain scene resolution.')
    raw=scene.get('positions');elevations=scene.get('elevations')
    if not isinstance(raw,list) or len(raw)!=n*n*3 or not isinstance(elevations,list) or len(elevations)!=n*n:raise ValueError('Invalid scene vertex arrays.')
    if any(v is None or isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in elevations):raise ValueError('The scene contains missing elevations. Select a fully covered area or import a complete DEM before printing.')
    a=np.asarray(raw,dtype=float).reshape(n,n,3)
    if not np.isfinite(a).all() or np.max(np.abs(a))>10000:raise ValueError('Invalid scene coordinates.')
    xx=resample(a[:,:,0],resolution);yy=-resample(a[:,:,2],resolution);height=resample(a[:,:,1],resolution)
    offset=float(height.min());height-=offset;buildings=scene.get('buildings',[])
    if not isinstance(buildings,list) or len(buildings)>2000:raise ValueError('Too many buildings.')
    represented=omitted=0
    if include_buildings:
        for b in buildings:
            rings=b.get('rings',[])
            if not rings or sum(len(r) for r in rings)>2000:raise ValueError('Invalid building footprint.')
            rings=[[(number(p[0],-10000,10000,'Footprint X'),-number(p[1],-10000,10000,'Footprint Y')) for p in ring] for ring in rings]
            polygon=Polygon(rings[0],rings[1:])
            if not polygon.is_valid or polygon.is_empty:raise ValueError('Invalid building polygon.')
            roof=number(b.get('base'),-10000,10000,'Building base')+number(b.get('height'),0,10000,'Building height')-offset
            mask=intersects_xy(polygon,xx,yy)
            if mask.any():height[mask]=np.maximum(height[mask],roof);represented+=1
            else:omitted+=1
    xmin,ymin=float(xx.min()),float(yy.min());xextent=float(xx.max()-xmin);yextent=float(yy.max()-ymin)
    if min(xextent,yextent)<1e-9:raise ValueError('Collapsed terrain footprint.')
    factor=span*1000/scale_denominator if scale_denominator else longest_side_mm/max(xextent,yextent)
    xx=(xx-xmin)*factor;yy=(yy-ymin)*factor;zz=height*factor*vertical_exaggeration+base_mm
    dimensions=[float(xx.max()),float(yy.max()),float(zz.max())]
    if min(dimensions[:2])<1 or max(dimensions)>2000:raise ValueError('Model dimensions are impractical; choose another scale or region.')
    fits=all(size<=bed+1e-6 for size,bed in zip(dimensions,bed_mm))
    if not fits and not allow_oversize:raise ValueError('The model exceeds the printer volume: '+', '.join(format(v,'.1f') for v in dimensions)+' mm. Reduce its side/vertical exaggeration, change scale, or allow oversize export for external splitting.')
    size=resolution;top=np.stack((xx,yy,zz),axis=-1).reshape(-1,3)
    # CCW perimeter in the print XY plane.
    ring=[r*size for r in range(size)]+[(size-1)*size+c for c in range(1,size)]+[r*size+size-1 for r in range(size-2,-1,-1)]+[c for c in range(size-2,0,-1)]
    bottom=np.array([[top[i,0],top[i,1],0.] for i in ring]);center=np.array([[bottom[:,0].mean(),bottom[:,1].mean(),0.]])
    vertices=np.vstack((top,bottom,center));faces=[]
    for r in range(size-1):
        for c in range(size-1):
            i=r*size+c;faces.extend(((i,i+size,i+1),(i+1,i+size,i+size+1)))
    start=len(top);middle=len(vertices)-1
    for i,aidx in enumerate(ring):
        j=(i+1)%len(ring);bidx=ring[j];ba=start+i;bb=start+j
        faces.extend(((aidx,ba,bb),(aidx,bb,bidx),(middle,bb,ba)))
    faces=np.asarray(faces,dtype=np.int32)
    # Float32 is the STL representation; validate the exact quantized output.
    vertices=vertices.astype('float32');triangles=vertices[faces].astype(float);normals=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]);areas=np.linalg.norm(normals,axis=1)
    if np.any(areas<1e-10):raise ValueError('The print mesh has a degenerate triangle. Increase model size or reduce grid detail.')
    if np.any(normals[:2*(size-1)**2,2]<=0):raise ValueError('Terrain footprint folds over itself.')
    edges=np.concatenate((faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]));canonical=np.sort(edges,axis=1);_,counts=np.unique(canonical,axis=0,return_counts=True)
    if np.any(counts!=2):raise ValueError('Mesh is not closed and manifold.')
    # Opposite directed edges on every join guarantee consistent winding.
    directed=np.where(edges[:,0]<edges[:,1],1,-1);order=np.lexsort((canonical[:,1],canonical[:,0]));sums=directed[order].reshape(-1,2).sum(axis=1)
    if np.any(sums):raise ValueError('Mesh surface orientation is inconsistent.')
    volume=float(np.einsum('ij,ij->i',triangles[:,0],np.cross(triangles[:,1],triangles[:,2])).sum()/6)
    if volume<=0:raise ValueError('Print mesh has non-positive volume.')
    report={'units':'millimeter','dimensions_mm':dimensions,'horizontal_scale_denominator':span*1000/factor,'vertical_exaggeration':vertical_exaggeration,'base_thickness_mm':base_mm,'printer_volume_mm':bed_mm,'fits_printer':fits,'vertices':len(vertices),'triangles':len(faces),'closed_manifold':True,'consistently_oriented':True,'volume_mm3':volume,'print_grid':size,'represented_buildings':represented,'omitted_small_buildings':omitted,'building_method':'height-field rasterization; footprints smaller than the print grid may be omitted','source_crs':meta.get('crs'),'source_pixel_size_m':meta.get('source_pixel_size_m'),'bbox':scene.get('bbox'),'color':'Geometry only; satellite imagery is not a color-print texture.','note':'STL uses millimeters by convention; 3MF declares millimeters. Open in your slicer and choose your printer/material profile. No printer-specific G-code is generated.'}
    return vertices,faces,report

def stl_bytes(vertices,faces):
    triangles=vertices[faces].astype('float32');normal=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]);normal/=np.linalg.norm(normal,axis=1)[:,None]
    dtype=np.dtype([('normal','<f4',(3,)),('vertices','<f4',(3,3)),('attribute','<u2')]);records=np.zeros(len(faces),dtype=dtype);records['normal']=normal;records['vertices']=triangles
    return b'SASPlanet watertight relief - MILLIMETERS'.ljust(80,b' ')+struct.pack('<I',len(faces))+records.tobytes()

def three_mf_bytes(vertices,faces):
    import xml.etree.ElementTree as ET
    namespace='http://schemas.microsoft.com/3dmanufacturing/core/2015/02';ET.register_namespace('',namespace)
    def tag(name):return '{'+namespace+'}'+name
    model=ET.Element(tag('model'),{'unit':'millimeter','{http://www.w3.org/XML/1998/namespace}lang':'en-US'})
    resources=ET.SubElement(model,tag('resources'));obj=ET.SubElement(resources,tag('object'),{'id':'1','type':'model'});mesh=ET.SubElement(obj,tag('mesh'));points=ET.SubElement(mesh,tag('vertices'))
    for x,y,z in vertices:ET.SubElement(points,tag('vertex'),{'x':format(float(x),'.9g'),'y':format(float(y),'.9g'),'z':format(float(z),'.9g')})
    triangles=ET.SubElement(mesh,tag('triangles'))
    for a,b,c in faces:ET.SubElement(triangles,tag('triangle'),{'v1':str(int(a)),'v2':str(int(b)),'v3':str(int(c))})
    build=ET.SubElement(model,tag('build'));ET.SubElement(build,tag('item'),{'objectid':'1'})
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml','<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        archive.writestr('_rels/.rels','<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        archive.writestr('3D/3dmodel.model',ET.tostring(model,encoding='utf-8',xml_declaration=True))
    return output.getvalue()

def export_print(p):
    options={k:p[k] for k in ('longest_side_mm','base_mm','vertical_exaggeration','resolution','include_buildings','scale_denominator','bed_mm','allow_oversize') if k in p}
    vertices,faces,report=make_solid(p['scene'],**options);stl=output_file('terrain_print','.stl');mf=stl.with_suffix('.3mf');info=stl.with_suffix('.json')
    stl.write_bytes(stl_bytes(vertices,faces));mf.write_bytes(three_mf_bytes(vertices,faces));info.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    return {'files':[{'name':'STL — mm','url':download(stl)},{'name':'3MF — mm','url':download(mf)},{'name':'Mesh validation report','url':download(info)}],'statistics':report}
