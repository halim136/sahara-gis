"""Printer-bed mesh partitions with loose alignment pins in base material."""
import math,io,json,zipfile
import numpy as np
import manifold3d as M
from .print3d import make_solid,stl_bytes,three_mf_bytes,number
from .gis_common import output_file,download

def mesh_arrays(solid):
    if solid.is_empty():raise ValueError('Empty print piece.')
    mesh=solid.to_mesh();vertices=np.array(mesh.vert_properties[:,:3],dtype='float32',copy=True);faces=np.asarray(mesh.tri_verts,dtype='int32')
    if solid.volume()<=0:raise ValueError('Print piece has invalid volume.')
    return vertices,faces

def split_print(p):
    options={k:p[k] for k in ('longest_side_mm','base_mm','vertical_exaggeration','resolution','include_buildings','scale_denominator','bed_mm') if k in p};options['allow_oversize']=True
    v,f,report=make_solid(p['scene'],**options);bed=report['printer_volume_mm'];width,depth,height=report['dimensions_mm'];margin=number(p.get('bed_margin_mm',2),0,15,'Bed margin');nozzle=number(p.get('nozzle_mm',.4),.1,2,'Nozzle size');pins=bool(p.get('alignment_pins',True));diameter=number(p.get('pin_diameter_mm',2),1,8,'Pin diameter');clearance=number(p.get('pin_clearance_mm',.2),.05,.5,'Pin clearance');base=report['base_thickness_mm'];radius=diameter/2+clearance
    if height>bed[2]:raise ValueError('Reduce vertical exaggeration or model scale: terrain exceeds printer height.')
    if min(bed[:2])<=2*margin:raise ValueError('Bed margin exceeds printer dimensions.')
    nx=math.ceil(width/(bed[0]-2*margin));ny=math.ceil(depth/(bed[1]-2*margin))
    if nx*ny>36:raise ValueError('Limit splitting to 36 pieces.')
    if pins and nx*ny>1 and base<2*radius+2*nozzle:raise ValueError('Increase base thickness for pin holes and minimum walls; use at least '+str(round(2*radius+2*nozzle,2))+' mm.')
    if diameter<3*nozzle and pins:raise ValueError('Pins are too thin for the selected nozzle.')
    solid=M.Manifold(M.Mesh(np.ascontiguousarray(v),np.ascontiguousarray(f,dtype='uint32')))
    if solid.volume()<=0:raise ValueError('Cannot construct printable solid.')
    dx,dy=width/nx,depth/ny;holes=[];joints=[];pin_length=min(12,dx*.35,dy*.35);z=base/2
    if pins and nx*ny>1:
        for x in range(1,nx):
            for y in range(ny):
                if dy<diameter*6:continue
                for fraction in (.3,.7):
                    center=[x*dx,(y+fraction)*dy,z];holes.append(M.Manifold.cylinder(pin_length,radius,circular_segments=24,center=True).rotate([0,90,0]).translate(center));joints.append({'axis':'X','center_mm':center,'pieces':[[x-1,y],[x,y]]})
        for y in range(1,ny):
            for x in range(nx):
                if dx<diameter*6:continue
                for fraction in (.3,.7):
                    center=[(x+fraction)*dx,y*dy,z];holes.append(M.Manifold.cylinder(pin_length,radius,circular_segments=24,center=True).rotate([90,0,0]).translate(center));joints.append({'axis':'Y','center_mm':center,'pieces':[[x,y-1],[x,y]]})
        for hole in holes:solid=solid-hole
    path=output_file('print_pieces','.zip');pieces=[]
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
        for y in range(ny):
            for x in range(nx):
                piece=solid.trim_by_plane([1,0,0],x*dx).trim_by_plane([-1,0,0],-(x+1)*dx).trim_by_plane([0,1,0],y*dy).trim_by_plane([0,-1,0],-(y+1)*dy)
                pv,pf=mesh_arrays(piece);pv[:,0]-=x*dx;pv[:,1]-=y*dy;name=f'piece_R{y+1:02d}_C{x+1:02d}';archive.writestr(name+'.stl',stl_bytes(pv,pf));archive.writestr(name+'.3mf',three_mf_bytes(pv,pf));extent=(pv.max(axis=0)-pv.min(axis=0)).tolist()
                if any(a>b+1e-3 for a,b in zip(extent,bed)):raise ValueError('A split piece exceeds printer volume.')
                pieces.append({'name':name,'row':y+1,'column':x+1,'assembly_origin_mm':[x*dx,y*dy,0],'dimensions_mm':extent,'volume_mm3':piece.volume()})
        if joints:
            pin=M.Manifold.cylinder(max(2,pin_length-.4),diameter/2,circular_segments=24);pv,pf=mesh_arrays(pin);archive.writestr('alignment_pin.stl',stl_bytes(pv,pf));archive.writestr('alignment_pin.3mf',three_mf_bytes(pv,pf))
        warnings=[]
        if p.get('alignment_pins',True) and nx*ny>1 and not joints:warnings.append('Edges too short for safe pin spacing; no alignment holes were added.')
        if report['omitted_small_buildings']:warnings.append('Some building footprints are below print-grid resolution.')
        warnings.append('Estimated minimum printable XY detail is '+str(round(2*nozzle,2))+' mm; inspect fine peaks/roofs in the slicer.')
        report.update(pieces=pieces,columns=nx,rows=ny,alignment_joints=joints,pins_to_print=len(joints),pin_diameter_mm=diameter,pin_hole_diameter_mm=2*radius,pin_length_mm=pin_length-.4 if joints else 0,nozzle_mm=nozzle,minimum_xy_detail_mm=2*nozzle,warnings=warnings)
        archive.writestr('assembly.json',json.dumps(report,indent=2,ensure_ascii=False));archive.writestr('README.txt','Each piece is already in millimeters and fits the configured printer. Print pieces individually. Reassemble using assembly_origin_mm and R/C labels. Print alignment_pin.stl once per joint. Holes include radial clearance. Slice with your printer/material settings. No G-code is supplied.')
        svg=['<svg xmlns="http://www.w3.org/2000/svg" width="800" height="800" viewBox="0 0 800 800"><rect width="800" height="800" fill="white"/>']
        for piece in pieces:
            x=piece['column']-1;y=piece['row']-1;xx=20+x*760/nx;yy=20+(ny-1-y)*760/ny;svg.append(f'<rect x="{xx}" y="{yy}" width="{760/nx}" height="{760/ny}" fill="#dfedf0" stroke="#40636e"/><text x="{xx+10}" y="{yy+25}" font-size="14">R{y+1} C{x+1}</text>')
        svg.append('</svg>');archive.writestr('assembly.svg',''.join(svg))
    return {'files':[{'name':'Printer pieces, pins & assembly (.ZIP)','url':download(path)}],'statistics':report}
