"""Metric building drafting and image-assisted roof proposals for manual review."""
import math,json,io
import numpy as np
from pyproj import Transformer
from shapely.geometry import Polygon,mapping
from shapely.ops import transform
from PIL import Image
from .gis_common import output_file,download

def local_transform(points):
    lon=sum(p[0] for p in points)/len(points);lat=sum(p[1] for p in points)/len(points);zone=min(60,max(1,int((lon+180)//6)+1));epsg=(32600 if lat>=0 else 32700)+zone
    return Transformer.from_crs(4326,epsg,always_xy=True),Transformer.from_crs(epsg,4326,always_xy=True)

def orthogonalize(points,rectangle=False):
    points=list(points)
    if points and points[0]==points[-1]:points=points[:-1]
    if not 3<=len(points)<=2000:raise ValueError('Draw at least three vertices.')
    forward,inverse=local_transform(points);xy=np.array([forward.transform(*p) for p in points]);origin=xy.mean(axis=0);xy-=origin
    polygon=Polygon(xy)
    if not polygon.is_valid or polygon.area<.1:raise ValueError('Polygon must be simple with a nonzero area.')
    if rectangle:
        fitted=np.asarray(polygon.minimum_rotated_rectangle.exterior.coords)[:-1]
    else:
        edges=np.roll(xy,-1,axis=0)-xy;length=np.linalg.norm(edges,axis=1)
        if np.min(length)<.01:raise ValueError('Remove duplicate or very short edges.')
        theta=np.arctan2(edges[:,1],edges[:,0]);angle=math.atan2(float(np.sum(length*np.sin(4*theta))),float(np.sum(length*np.cos(4*theta))))/4
        rotation=np.array([[math.cos(angle),-math.sin(angle)],[math.sin(angle),math.cos(angle)]])
        uv=xy@rotation;n=len(points);constraints=[]
        for i in range(n):
            j=(i+1)%n;delta=uv[j]-uv[i];axis=1 if abs(delta[0])>=abs(delta[1]) else 0
            row=np.zeros(2*n);row[2*i+axis]=1;row[2*j+axis]=-1;constraints.append(row)
        C=np.array(constraints);v=uv.ravel();fitted=(v-C.T@np.linalg.pinv(C@C.T)@(C@v)).reshape(-1,2)@rotation.T
    candidate=Polygon(fitted)
    if not candidate.is_valid or candidate.area<.1 or candidate.area<polygon.area*.2:raise ValueError('Orthogonal fit collapsed the polygon. Use a rectangle or edit the original vertices.')
    absolute=fitted+origin;ring=[list(inverse.transform(*p)) for p in absolute];ring.append(ring[0])
    result={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'name':'Building proposal','area_m2':float(candidate.area),'review_required':True,'method':'minimum rotated rectangle' if rectangle else 'dominant orientation + constrained least squares'},'geometry':{'type':'Polygon','coordinates':[ring]}}]}
    return result

def roof_proposal(image_path,bbox,rectangle=False):
    import cv2
    image=Image.open(image_path).convert('RGB');image.thumbnail((1600,1600));rgb=np.asarray(image);h,w=rgb.shape[:2]
    if min(h,w)<16:raise ValueError('Select a larger image region.')
    # The selected crop should contain one roof with a margin of background.
    margin=max(2,round(min(h,w)*.08));mask=np.zeros((h,w),np.uint8);bg=np.zeros((1,65));fg=np.zeros((1,65))
    cv2.setRNGSeed(0);cv2.grabCut(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),mask,(margin,margin,w-2*margin,h-2*margin),bg,fg,5,cv2.GC_INIT_WITH_RECT)
    binary=np.where((mask==1)|(mask==3),255,0).astype('uint8');binary=cv2.morphologyEx(binary,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    contours,_=cv2.findContours(binary,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    if not contours:raise ValueError('No roof boundary found. Add background margin or use manual drawing.')
    contour=max(contours,key=cv2.contourArea)
    approx=cv2.approxPolyDP(contour,max(1,cv2.arcLength(contour,True)*.008),True).reshape(-1,2)
    if len(approx)<3 or cv2.contourArea(contour)<w*h*.005:raise ValueError('No usable roof proposal found.')
    west,south,east,north=bbox;points=[[west+(float(x)+.5)/w*(east-west),north-(float(y)+.5)/h*(north-south)] for x,y in approx]
    if rectangle:return orthogonalize(points,True)
    polygon=Polygon(points)
    if not polygon.is_valid:polygon=polygon.buffer(0)
    if polygon.geom_type!='Polygon':raise ValueError('Ambiguous segmentation; use manual drawing.')
    forward,_=local_transform(points)
    return {'type':'FeatureCollection','features':[{'type':'Feature','properties':{'name':'Roof proposal','area_m2':transform(forward.transform,polygon).area,'review_required':True,'method':'GrabCut foreground segmentation; roof is not a surveyed footprint'},'geometry':mapping(polygon)}]}

def save_proposal(collection):
    path=output_file('building_proposal','.geojson');path.write_text(json.dumps(collection),encoding='utf8')
    return {'geojson':collection,'files':[{'name':'Building GeoJSON','url':download(path)}],'statistics':collection['features'][0]['properties']}
