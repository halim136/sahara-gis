"""Batch fixed-scale atlases and unscaled A4/A3 assembly tiles."""
import math,json,io,zipfile,copy
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4,A3
from pypdf import PdfReader,PdfWriter,Transformation
from .gis_common import EXPORTS,output_file,download
from .map_layout import create_layout

def tile_pdf(source,output,page='A4',overlap_mm=10,margin_mm=12):
    if page not in ('A4','A3'):raise ValueError('Tile paper must be A4 or A3.')
    if not 0<=overlap_mm<=30 or not 5<=margin_mm<=30:raise ValueError('Invalid overlap or margin.')
    pw,ph=A4 if page=='A4' else A3;mm=72/25.4;margin=margin_mm*mm;overlap=overlap_mm*mm;w,h=pw-2*margin,ph-2*margin;sx,sy=w-overlap,h-overlap
    reader=PdfReader(source);writer=PdfWriter();index=[]
    for sheet,page_source in enumerate(reader.pages,1):
        width,height=float(page_source.mediabox.width),float(page_source.mediabox.height);cols=max(1,math.ceil((width-overlap)/sx));rows=max(1,math.ceil((height-overlap)/sy))
        if len(index)+rows*cols>240:raise ValueError('Atlas exceeds 240 tiled pages; use fewer sheets or larger paper.')
        for r in range(rows):
            for c in range(cols):
                x=c*sx;y=max(0,height-h-r*sy);part=copy.deepcopy(page_source);part.cropbox.lower_left=(x,y);part.cropbox.upper_right=(min(width,x+w),min(height,y+h))
                dst=writer.add_blank_page(pw,ph);dst.merge_transformed_page(part,Transformation().translate(margin-x,margin-y),expand=False)
                overlay=io.BytesIO();pdf=canvas.Canvas(overlay,pagesize=(pw,ph));pdf.setFont('Helvetica',8);pdf.drawString(margin,ph-18,f'Sheet {sheet} | row {r+1}/{rows}, col {c+1}/{cols} | print 100%');pdf.drawString(margin,15,f'Overlap {overlap_mm} mm | scale unchanged | tile {len(index)+1}')
                pdf.setLineWidth(.3);pdf.setDash(2,2);pdf.rect(margin,margin,w,h);pdf.save();dst.merge_page(PdfReader(overlay).pages[0]);index.append({'page':len(index)+1,'source_sheet':sheet,'row':r+1,'column':c+1,'rows':rows,'columns':cols,'source_window_points':[x,y,min(width,x+w),min(height,y+h)],'content_scale':1})
    writer.write(output);return index

def atlas(p):
    sheets=p.get('sheets',[])
    if not 1<=len(sheets)<=12:raise ValueError('Select 1–12 sheets for the atlas.')
    path=output_file('atlas','.pdf');writer=PdfWriter();sources=[]
    for sheet in sheets:
        props=sheet['properties'];title=str(props.get('sheet_name') or props.get('sheet_id','Sheet'))
        result=create_layout({'bbox':props['wgs84_bbox'],'sheet':sheet,'source':p.get('source','terrain'),'offline':p.get('offline',False),'resolution':p.get('resolution',128),'page':'A1','landscape':False,'scale':25000,'crs':p.get('crs','utm_ns_auto'),'interval':p.get('interval',25),'title':title})
        file=EXPORTS/Path(result['files'][0]['url']).name;writer.append(file);sources.append({'sheet_id':props.get('sheet_id'),'title':title,'scale':25000,'metadata':result['statistics']})
    writer.write(path);tile_path=path.with_name(path.stem+'_'+p.get('paper','A4')+'.pdf');tiles=tile_pdf(path,tile_path,p.get('paper','A4'),float(p.get('overlap_mm',10)),float(p.get('margin_mm',12)))
    report={'scale':25000,'source_pages':len(sheets),'assembly_pages':len(tiles),'paper':p.get('paper','A4'),'overlap_mm':p.get('overlap_mm',10),'rescaling_applied':False,'sheets':sources,'assembly_index':tiles,'print_instruction':'Print Actual Size / 100%, disable Fit to Page. Trim/align using the dashed content frames and overlaps.'};info=path.with_suffix('.json');info.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    return {'files':[{'name':'Atlas A1 — 1:25,000','url':download(path)},{'name':p.get('paper','A4')+' assembly atlas — 100%','url':download(tile_path)},{'name':'Assembly index & metadata','url':download(info)}],'statistics':report}
