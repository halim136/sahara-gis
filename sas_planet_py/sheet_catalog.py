"""User-supplied authoritative sheet catalog, retaining source provenance."""
import json,uuid,re
from pathlib import Path
from datetime import datetime,timezone
from shapely.geometry import shape,mapping,box
from shapely.ops import transform
from pyproj import Transformer
from .gis_common import APP
from .map_sheets import grid_crs
ROOT=APP/'cache/catalogs'

def path_for(identifier):
    if not re.fullmatch('[a-f0-9]{32}',str(identifier)):raise ValueError('Invalid catalog identifier.')
    return ROOT/(identifier+'.json')

def list_catalogs():
    ROOT.mkdir(parents=True,exist_ok=True);result=[]
    for path in ROOT.glob('*.json'):
        try:
            data=json.loads(path.read_text('utf8'));result.append({**data['metadata'],'id':path.stem,'features':len(data['geojson']['features'])})
        except (ValueError,KeyError):pass
    return {'catalogs':result}

def import_catalog(p):
    collection=p['geojson'];features=collection.get('features',[])
    if collection.get('type')!='FeatureCollection' or not 1<=len(features)<=50000:raise ValueError('Import 1–50,000 sheet polygons in a GeoJSON FeatureCollection.')
    provenance=p.get('provenance',{})
    if not str(provenance.get('publisher','')).strip() or not str(provenance.get('source','')).strip():raise ValueError('Publisher and source document/URL are required.')
    crs=p.get('crs','EPSG:4326');source=grid_crs('nord_sahara')[0] if crs=='EPSG:4307' else crs;converter=Transformer.from_crs(source,4326,always_xy=True);out=[];seen=set()
    fields=p.get('fields',{});number_field=fields.get('number','sheet_id');name_field=fields.get('name','name');edition_field=fields.get('edition','edition');year_field=fields.get('year','year')
    for i,f in enumerate(features):
        props=f.get('properties',{});number=str(props.get(number_field,'')).strip();name=str(props.get(name_field,'')).strip()
        if not number or not name:raise ValueError('Every sheet requires mapped number and name fields; missing at row '+str(i+1))
        g=transform(converter.transform,shape(f['geometry']))
        if g.geom_type not in ('Polygon','MultiPolygon') or g.is_empty or not g.is_valid or not box(-10,17,14,39).intersects(g):raise ValueError('Invalid or non-Algeria sheet geometry at row '+str(i+1))
        edition=str(props.get(edition_field,''));year=str(props.get(year_field,''));key=(number,edition,year)
        if key in seen:raise ValueError('Duplicate sheet number/edition/year: '+number)
        seen.add(key);out.append({'type':'Feature','id':str(i),'properties':{**props,'sheet_id':number,'sheet_name':name,'edition':edition,'year':year,'scale':int(p.get('scale',25000)),'wgs84_bbox':list(g.bounds),'imported_inventory':True,'source_status':'user-supplied catalog; provenance retained, not independently certified','publisher':provenance['publisher'],'source_document':provenance['source']},'geometry':mapping(g)})
    identifier=uuid.uuid4().hex;ROOT.mkdir(parents=True,exist_ok=True);data={'metadata':{'name':p.get('name','Imported sheet catalog'),'provenance':provenance,'source_crs':crs,'imported_utc':datetime.now(timezone.utc).isoformat(),'independently_verified':False},'geojson':{'type':'FeatureCollection','features':out}}
    path_for(identifier).write_text(json.dumps(data,ensure_ascii=False),encoding='utf8');return {'id':identifier,**data['metadata'],'features':len(out)}

def import_marks_catalog(p):
    """Build a sheet catalog from SAS.Planet marks (parsed from .sml/.db3/.kml…).

    Polygon marks become sheets; the sheet number/name are taken from the
    retained SAS.Planet fields (n_50000 → number, nom → name) with sensible
    fallbacks, so an imported grid appears as a permanent, searchable source.
    """
    marks=p.get('marks') or []
    if not isinstance(marks,list) or not 1<=len(marks)<=50000:raise ValueError('Import 1–50,000 SAS.Planet marks.')
    features=[]
    for mark in marks:
        if not isinstance(mark,dict) or mark.get('type')!='polygon':continue
        ring=mark.get('coords') or [];holes=(mark.get('properties') or {}).get('holes') or []
        if len(ring)<3:continue
        props=mark.get('properties') or {}
        number=str(props.get('n_50000') or props.get('id') or props.get('source_name') or '').strip()
        name=str(props.get('nom') or props.get('type') or props.get('source_name') or mark.get('name') or '').strip()
        if not number or not name:continue
        kept={key:props[key] for key in ('id','nom','type','n_50000','coup','num') if key in props}
        features.append({'type':'Feature','properties':{**kept,'sheet_id':number,'name':name,'edition':str(props.get('type','')),'year':''},'geometry':{'type':'Polygon','coordinates':[ring,*holes]}})
    if not features:raise ValueError('No sheet polygons with id/name were found in this SAS.Planet file.')
    payload={'geojson':{'type':'FeatureCollection','features':features},'name':str(p.get('name') or 'SAS.Planet grid').strip() or 'SAS.Planet grid','crs':'EPSG:4326','scale':int(p.get('scale',25000)),'fields':{'number':'sheet_id','name':'name','edition':'edition','year':'year'},'provenance':{'publisher':str(p.get('publisher') or 'SAS.Planet export').strip() or 'SAS.Planet export','source':str(p.get('source') or 'SAS.Planet marks database (.sml/.db3)').strip() or 'SAS.Planet marks database (.sml/.db3)'}}
    return import_catalog(payload)

def query_catalog(p):
    data=json.loads(path_for(p['id']).read_text('utf8'));region=box(*p['bbox']);search=str(p.get('search','')).casefold();edition=str(p.get('edition',''))
    features=[f for f in data['geojson']['features'] if (not search or search in (f['properties']['sheet_id']+' '+f['properties']['sheet_name']).casefold()) and (not edition or f['properties']['edition']==edition) and region.intersects(shape(f['geometry']))]
    if len(features)>3500:features=features[:3500]
    return {'geojson':{'type':'FeatureCollection','features':features},'metadata':data['metadata'],'statistics':{'sheets':len(features),'official_inventory':False,'imported_inventory':True},'overview':False,'files':[]}
