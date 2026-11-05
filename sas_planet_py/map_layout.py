"""A4/A3 north-up cartographic PDF with vector contours and metric UTM grid."""
import math,io
import numpy as np
from PIL import Image,ImageFont,ImageDraw
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4,A3,A2,A1,landscape
from reportlab.lib.utils import ImageReader
from pyproj import Transformer,CRS
from rasterio.io import MemoryFile
from .gis_common import analysis_grid,output_file,download,APP,target_crs,warped_bytes
from .terrain_analysis import terrain_metrics,metric_spacing
from .arcgis_export import color_image,rgb_geotiff
from .topography import TopographicEngine

def create_layout(p):
    bbox=p['bbox'];crs,label=target_crs(p.get('crs','utm_wgs84_auto'),bbox)
    if not crs.is_projected:raise ValueError('Select a metric UTM CRS for the printed map.')
    page=p.get('page','A4')
    if page not in ('A4','A3','A2','A1'):raise ValueError('Select A4, A3, A2 or A1.')
    size={'A4':A4,'A3':A3,'A2':A2,'A1':A1}[page]
    if p.get('landscape',True):size=landscape(size)
    pw,ph=size;x0,y0=50,105;mw,mh=pw-100,ph-175
    forward=Transformer.from_crs(4326,crs.to_wkt(),always_xy=True);inverse=Transformer.from_crs(crs.to_wkt(),4326,always_xy=True)
    lon=(bbox[0]+bbox[2])/2;lat=(bbox[1]+bbox[3])/2;cx,cy=forward.transform(lon,lat)
    corners=[forward.transform(x,y) for x in (bbox[0],bbox[2]) for y in (bbox[1],bbox[3])]
    requested=float(p.get('scale',0));auto=max((max(x for x,y in corners)-min(x for x,y in corners))/(mw*.0254/72),(max(y for x,y in corners)-min(y for x,y in corners))/(mh*.0254/72))
    if requested and not 100<=requested<=10000000:raise ValueError('Scale denominator must be 100–10,000,000 or zero for fit.')
    scale=requested or auto;width=mw*.0254/72*scale;height=mh*.0254/72*scale;bounds=[cx-width/2,cy-height/2,cx+width/2,cy+height/2]
    # Densify the projected frame before requesting geographic source coverage.
    perimeter=[inverse.transform(bounds[0]+width*t,bounds[1]+height*u) for t,u in [(t/20,u) for t in range(21) for u in (0,1)]+[(u,t/20) for t in range(21) for u in (0,1)]]
    gb=[min(x for x,y in perimeter),min(y for x,y in perimeter),max(x for x,y in perimeter),max(y for x,y in perimeter)]
    dem=analysis_grid(gb,p.get('resolution',256),p.get('source','terrain'),p.get('offline',False));grid=dem['grid'];rows,cols=len(grid),len(grid[0]);dx,dy=metric_spacing(gb,rows,cols);metrics=terrain_metrics(grid,dx,dy)
    raw=rgb_geotiff(color_image(grid,'relief',metrics['hillshade']),gb)
    from rasterio.transform import from_bounds
    # Print raster exactly fills the metric map frame; source pixel size is reported, not hidden by upsampling.
    reference=(from_bounds(*bounds,1200,max(1,round(1200*mh/mw))),1200,max(1,round(1200*mh/mw)))
    warped,_=warped_bytes(raw,crs,reference)
    with MemoryFile(warped) as mem,mem.open() as src:image=Image.fromarray(np.moveaxis(src.read(),0,2),'RGBA')
    path=output_file('topographic_map','.pdf');pdf=canvas.Canvas(str(path),pagesize=size);pdf.setTitle(str(p.get('title','Topographic map')))
    pdf.drawImage(ImageReader(image),x0,y0,mw,mh,mask='auto')
    def px(x):return x0+(x-bounds[0])/width*mw
    def py(y):return y0+(y-bounds[1])/height*mh
    pdf.saveState();clip=pdf.beginPath();clip.rect(x0,y0,mw,mh);pdf.clipPath(clip,stroke=0)
    interval=float(p.get('interval',25))
    if not .1<=interval<=10000:raise ValueError('Invalid contour interval.')
    centers=(gb[0]+(gb[2]-gb[0])/cols/2,gb[1]+(gb[3]-gb[1])/rows/2,gb[2]-(gb[2]-gb[0])/cols/2,gb[3]-(gb[3]-gb[1])/rows/2)
    contours=TopographicEngine.generate_contour_geojson(centers,interval,dem=dem,above_sea_only=False)
    label_boxes=[]
    for f in contours['features']:
        pts=[forward.transform(*v[:2]) for v in f['geometry']['coordinates']];pdf.setStrokeColorRGB(.48,.29,.12);pdf.setLineWidth(.65 if f['properties']['is_index'] else .25);line=pdf.beginPath()
        for i,(x,y) in enumerate(pts):
            if i==0:line.moveTo(px(x),py(y))
            else:line.lineTo(px(x),py(y))
        pdf.drawPath(line)
        if f['properties']['is_index'] and len(pts)>4:
            x,y=pts[len(pts)//2];xx,yy=px(x),py(y)
            if x0+20<xx<x0+mw-20 and y0+10<yy<y0+mh-10 and all(math.hypot(xx-a,yy-b)>40 for a,b in label_boxes):
                label_boxes.append((xx,yy));pdf.setFont('Helvetica',7);pdf.setFillColorRGB(.35,.18,.05);pdf.drawCentredString(xx,yy,str(round(f['properties']['elevation'])))
    if p.get('sheet'):
        from shapely.geometry import shape
        sheet=shape(p['sheet']['geometry']);pdf.setStrokeColorRGB(.15,.18,.25);pdf.setLineWidth(1.2)
        for ring in [sheet.exterior,*sheet.interiors]:
            border=pdf.beginPath()
            for i,point in enumerate(ring.coords):
                x,y=forward.transform(*point[:2])
                if i==0:border.moveTo(px(x),py(y))
                else:border.lineTo(px(x),py(y))
            pdf.drawPath(border)
    # Rounded metric spacing keeps the grid readable across selected print scales.
    raw_step=width/6;power=10**math.floor(math.log10(raw_step));step=next((m*power for m in (1,2,5,10) if m*power>=raw_step),10*power)
    pdf.setStrokeColorRGB(.2,.35,.55);pdf.setLineWidth(.25);pdf.setDash(2,3)
    xs=np.arange(math.ceil(bounds[0]/step)*step,bounds[2],step);ys=np.arange(math.ceil(bounds[1]/step)*step,bounds[3],step)
    for x in xs:pdf.line(px(x),y0,px(x),y0+mh)
    for y in ys:pdf.line(x0,py(y),x0+mw,py(y))
    pdf.restoreState();pdf.setDash();pdf.setStrokeColorRGB(0,0,0);pdf.rect(x0,y0,mw,mh);pdf.setFont('Helvetica',7);pdf.setFillColorRGB(0,0,0)
    for x in xs:pdf.drawCentredString(px(x),y0-10,str(round(x)))
    for y in ys:pdf.saveState();pdf.translate(x0-8,py(y));pdf.rotate(90);pdf.drawCentredString(0,0,str(round(y)));pdf.restoreState()
    title=str(p.get('title','Topographic map'))[:200]
    if any('؀'<=c<='ۿ' for c in title):
        from arabic_reshaper import reshape
        from bidi.algorithm import get_display
        display=get_display(reshape(title));font=ImageFont.truetype(str(APP/'public/fonts/NotoSansArabic.ttf'),72,layout_engine=ImageFont.Layout.BASIC);box=font.getbbox(display);title_image=Image.new('RGBA',(box[2]-box[0]+20,box[3]-box[1]+20));ImageDraw.Draw(title_image).text((10-box[0],10-box[1]),display,font=font,fill='black');tw=min(mw,title_image.width/title_image.height*24);pdf.drawImage(ImageReader(title_image),(pw-tw)/2,ph-50,tw,24,mask='auto')
    else:pdf.setFont('Helvetica-Bold',16);pdf.drawCentredString(pw/2,ph-43,title)
    pdf.setFont('Helvetica',8);pdf.drawString(x0,75,label+' | Grid north | Contour interval '+str(interval)+' m');pdf.drawString(x0,62,'Scale 1:'+format(round(scale),',')+' at original paper size | '+page)
    # Metric bar is derived from exactly the same map-to-paper transform.
    bar=step;bw=bar/width*mw
    while bw>mw*.35:bar/=2;bw=bar/width*mw
    pdf.setFillColorRGB(0,0,0);pdf.rect(x0,43,bw/2,5,fill=1);pdf.rect(x0+bw/2,43,bw/2,5);pdf.drawString(x0,32,'0');pdf.drawRightString(x0+bw,32,str(round(bar))+' m')
    nx=x0+mw-22;ny=y0+mh-42;arrow=pdf.beginPath();arrow.moveTo(nx,ny+25);arrow.lineTo(nx-7,ny);arrow.lineTo(nx,ny+5);arrow.lineTo(nx+7,ny);arrow.close();pdf.drawPath(arrow,fill=1);pdf.setFont('Helvetica-Bold',10);pdf.drawCentredString(nx,ny+30,'N')
    pdf.setFont('Helvetica',6);pdf.drawRightString(x0+mw,62,'Brown: contours | Color: elevation + hillshade');pdf.drawRightString(x0+mw,49,'Native source spacing ~'+str(dem.get('source_pixel_size_m','unknown'))+' m; elevations assumed meters')
    attribution=str(dem.get('attribution','Local DEM')).encode('ascii','replace').decode()[:150];pdf.drawRightString(x0+mw,20,attribution)
    pdf.showPage();pdf.save()
    return {'files':[{'name':page+' topographic PDF','url':download(path)}],'statistics':{'scale':scale,'page':page,'crs':label,'grid_interval_m':step,'map_bounds':bounds,'geographic_bbox':gb,'contour_lines':len(contours['features']),'source_pixel_size_m':dem.get('source_pixel_size_m')}}
