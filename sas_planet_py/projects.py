"""Portable project manifests with backups and bundled local analysis assets."""
import json,uuid,re,zipfile,hashlib,shutil
from pathlib import Path
from datetime import datetime,timezone
from .gis_common import APP,EXPORTS,output_file,download
ROOT=APP/'cache/projects'
KEYS={'settings','marks','view','sourceId','overlays','contours','contourDisplay','terrainOverlay','analyses','camera3D','field','catalogId','name'}

def identifier(value):
    if not re.fullmatch('[a-f0-9]{32}',str(value)):raise ValueError('Invalid project identifier.')
    return value

def path_for(value):ROOT.mkdir(parents=True,exist_ok=True);return ROOT/(identifier(value)+'.json')
def clean_state(state):
    if not isinstance(state,dict):raise ValueError('Invalid project state.')
    out={k:v for k,v in state.items() if k in KEYS}
    raw=json.dumps(out,ensure_ascii=False,allow_nan=False)
    if len(raw.encode('utf8'))>32*1024**2:raise ValueError('Project manifest exceeds 32 MB.')
    if len(out.get('marks',[]))>50000:raise ValueError('Project has too many marks.')
    return out

def save_project(p):
    state=clean_state(p['state']);uid=identifier(p['id']) if p.get('id') else uuid.uuid4().hex;path=path_for(uid)
    if path.is_file():
        backup=ROOT/'backups'/uid;backup.mkdir(parents=True,exist_ok=True);shutil.copy2(path,backup/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'.json'))
    manifest={'schema':'sasgis-project','version':1,'id':uid,'name':str(p.get('name') or state.get('name') or 'GIS project')[:200],'saved_utc':datetime.now(timezone.utc).isoformat(),'state':state}
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8');tmp.replace(path)
    return {'project':manifest}

def list_projects():
    ROOT.mkdir(parents=True,exist_ok=True);result=[]
    for path in ROOT.glob('*.json'):
        try:
            m=json.loads(path.read_text('utf8'));result.append({k:m[k] for k in ('id','name','saved_utc')})
        except (KeyError,ValueError):pass
    return {'projects':sorted(result,key=lambda m:m['saved_utc'],reverse=True)}

def load_project(p):
    path=path_for(p['id'])
    if p.get('backup'):
        name=str(p['backup'])
        if not re.fullmatch('[0-9T]+[.]json',name):raise ValueError('Invalid backup name.')
        path=ROOT/'backups'/identifier(p['id'])/name
    m=json.loads(path.read_text('utf8'));clean_state(m['state']);return {'project':m}

def backups(p):
    folder=ROOT/'backups'/identifier(p['id']);return {'backups':sorted([f.name for f in folder.glob('*.json')],reverse=True) if folder.is_dir() else []}

def visit(value,convert):
    if isinstance(value,str):return convert(value)
    if isinstance(value,list):return [visit(v,convert) for v in value]
    if isinstance(value,dict):return {k:visit(v,convert) for k,v in value.items()}
    return value

def pack_project(p):
    project=load_project(p)['project'];assets={};missing=[];base=EXPORTS.resolve();total=0
    def collect(value):
        nonlocal total
        if value.startswith('/exports/'):
            from urllib.parse import unquote
            relative=unquote(value[len('/exports/'):].split('?',1)[0]);file=(base/relative).resolve()
            if not file.is_relative_to(base) or not file.is_file():missing.append(value);return value
            arc='assets/'+file.relative_to(base).as_posix()
            if arc not in assets:assets[arc]=file;total+=file.stat().st_size
            return 'asset://'+arc
        return value
    manifest={**project,'state':visit(project['state'],collect)}
    # Optional selected DEMs are packed with their sidecar metadata, preserving stable IDs.
    from .dem_catalog import dem_path
    for uid in p.get('dem_ids',[]):
        path=dem_path(uid)
        for file in (path,path.with_suffix('.json')):
            if file.is_file():assets['dem/'+file.name]=file;total+=file.stat().st_size
    catalog=project['state'].get('catalogId')
    if catalog:
        from .sheet_catalog import path_for as catalog_path
        file=catalog_path(catalog)
        if file.is_file():assets['catalog/'+file.name]=file;total+=file.stat().st_size
    if total>500*1024**2 or len(assets)>4096:raise ValueError('Project package exceeds 500 MB or 4096 assets.')
    path=output_file('project','.sasgis');checksums={name:hashlib.sha256(file.read_bytes()).hexdigest() for name,file in assets.items()}
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('project.json',json.dumps(manifest,ensure_ascii=False));archive.writestr('checksums.json',json.dumps(checksums))
        for name,file in assets.items():archive.write(file,name)
    return {'files':[{'name':'Portable GIS project (.sasgis)','url':download(path)}],'statistics':{'assets':len(assets),'size_mb':round(path.stat().st_size/1024**2,2),'missing_assets':missing,'relative_paths':True}}

def unpack_project(path):
    token=uuid.uuid4().hex;destination=EXPORTS/('project_import_'+token);missing=[]
    with zipfile.ZipFile(path) as archive:
        members=archive.infolist()
        if len(members)>4100 or sum(i.file_size for i in members)>550*1024**2:raise ValueError('Project package is too large.')
        for info in members:
            name=info.filename
            if info.is_dir():continue
            if name not in ('project.json','checksums.json') and not name.startswith(('assets/','dem/','catalog/')):raise ValueError('Unexpected package entry.')
            if '..' in Path(name).parts or chr(92) in name or name.startswith('/'):raise ValueError('Unsafe project package path.')
        manifest=json.loads(archive.read('project.json'));checksums=json.loads(archive.read('checksums.json'))
        if manifest.get('schema')!='sasgis-project' or manifest.get('version')!=1:raise ValueError('Unsupported GIS project package.')
        state=clean_state(manifest['state']);payloads={}
        for info in members:
            if info.filename in checksums:
                raw=archive.read(info.filename)
                if hashlib.sha256(raw).hexdigest()!=checksums[info.filename]:raise ValueError('Project asset checksum mismatch.')
                payloads[info.filename]=raw
        # Imported DEM/catalog IDs are remapped so existing user data is never overwritten.
        dem_map={};catalog_map={}
        for name in payloads:
            if name.startswith('dem/') and name.endswith('.tif'):dem_map[Path(name).stem]=uuid.uuid4().hex
            if name.startswith('catalog/'):catalog_map[Path(name).stem]=uuid.uuid4().hex
        for name,raw in payloads.items():
            if name.startswith('assets/'):
                file=(destination/name).resolve();
                if not file.is_relative_to(destination.resolve()):raise ValueError('Unsafe project asset destination.')
                file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(raw)
            elif name.startswith('dem/'):
                from .dem_catalog import dem_path,inspect_dem
                old=Path(name).stem
                if name.endswith('.tif'):
                    file=dem_path(dem_map[old]);file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(raw);inspect_dem(file,'Project DEM '+old[:8])
            elif name.startswith('catalog/'):
                from .sheet_catalog import path_for as catalog_path
                file=catalog_path(catalog_map[Path(name).stem]);file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(raw)
        def relink(value):
            if value.startswith('asset://'):
                name=value[len('asset://'):]
                if name not in payloads:missing.append(name);return ''
                return '/exports/'+destination.name+'/'+name
            if value.startswith('dem:') and value[4:] in dem_map:return 'dem:'+dem_map[value[4:]]
            if value in catalog_map:return catalog_map[value]
            return value
        state=visit(state,relink);result=save_project({'name':manifest['name']+' (imported)','state':state});result['statistics']={'missing_assets':missing,'imported_dems':len(dem_map),'catalogs':len(catalog_map)};return result
