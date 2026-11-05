"""OGC GeoPackage 1.3 vector features and standard Web Mercator tile pyramids."""
import sqlite3,struct,json,io,math
from datetime import datetime,timezone
from pathlib import Path
from shapely.geometry import shape,mapping
from shapely import wkb
from pyproj import CRS,Transformer
from shapely.ops import transform
from PIL import Image
from .gis_common import output_file,download
from .tile_storage import FileSystemStorage,IMAGE_EXTENSIONS
from .projections import lon_lat_to_tile
from .map_sources import get_source

SCHEMA='''
CREATE TABLE gpkg_spatial_ref_sys(srs_name TEXT NOT NULL,srs_id INTEGER PRIMARY KEY,organization TEXT NOT NULL,organization_coordsys_id INTEGER NOT NULL,definition TEXT NOT NULL,description TEXT);
CREATE TABLE gpkg_contents(table_name TEXT PRIMARY KEY,data_type TEXT NOT NULL,identifier TEXT UNIQUE,description TEXT DEFAULT '',last_change DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),min_x DOUBLE,min_y DOUBLE,max_x DOUBLE,max_y DOUBLE,srs_id INTEGER,FOREIGN KEY(srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id));
CREATE TABLE gpkg_geometry_columns(table_name TEXT NOT NULL,column_name TEXT NOT NULL,geometry_type_name TEXT NOT NULL,srs_id INTEGER NOT NULL,z TINYINT NOT NULL,m TINYINT NOT NULL,PRIMARY KEY(table_name,column_name),FOREIGN KEY(table_name) REFERENCES gpkg_contents(table_name),FOREIGN KEY(srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id));
CREATE TABLE gpkg_tile_matrix_set(table_name TEXT PRIMARY KEY,srs_id INTEGER NOT NULL,min_x DOUBLE NOT NULL,min_y DOUBLE NOT NULL,max_x DOUBLE NOT NULL,max_y DOUBLE NOT NULL,FOREIGN KEY(table_name) REFERENCES gpkg_contents(table_name),FOREIGN KEY(srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id));
CREATE TABLE gpkg_tile_matrix(table_name TEXT NOT NULL,zoom_level INTEGER NOT NULL,matrix_width INTEGER NOT NULL,matrix_height INTEGER NOT NULL,tile_width INTEGER NOT NULL,tile_height INTEGER NOT NULL,pixel_x_size DOUBLE NOT NULL,pixel_y_size DOUBLE NOT NULL,PRIMARY KEY(table_name,zoom_level),FOREIGN KEY(table_name) REFERENCES gpkg_contents(table_name));
'''

def create(path):
    db=sqlite3.connect(path);db.executescript(SCHEMA);db.execute('PRAGMA application_id=1196444487');db.execute('PRAGMA user_version=10300');db.execute('PRAGMA foreign_keys=ON')
    for code,name,org in [(-1,'Undefined Cartesian','NONE'),(0,'Undefined geographic','NONE'),(4326,'WGS 84','EPSG'),(3857,'WGS 84 / Pseudo-Mercator','EPSG')]:
        definition=CRS.from_epsg(code).to_wkt('WKT1_GDAL') if code>0 else 'undefined';db.execute('INSERT INTO gpkg_spatial_ref_sys VALUES(?,?,?,?,?,?)',(name,code,org,code,definition,''))
    return db

def export_package(features=None,source_id=None,bbox=None,zooms=None,cache_dir=None):
    path=output_file('project','.gpkg');db=create(path);count=tiles=0
    try:
        if features:
            db.execute('CREATE TABLE features(fid INTEGER PRIMARY KEY AUTOINCREMENT,geom BLOB NOT NULL,name TEXT,properties TEXT)')
            db.execute("INSERT INTO gpkg_contents(table_name,data_type,identifier,srs_id) VALUES('features','features','Map features',4326)")
            db.execute("INSERT INTO gpkg_geometry_columns VALUES('features','geom','GEOMETRY',4326,0,0)")
            bounds=[]
            for f in features.get('features',[]):
                geometry=shape(f['geometry'])
                if geometry.is_empty or not geometry.is_valid:raise ValueError('GeoPackage contains an invalid geometry.')
                # Core WKB and XY only; elevation stays in feature attributes.
                from shapely import force_2d
                geometry=force_2d(geometry);properties=f.get('properties',{});blob=b'GP'+bytes([0,1])+struct.pack('<i',4326)+wkb.dumps(geometry,byte_order=1)
                db.execute('INSERT INTO features(geom,name,properties) VALUES(?,?,?)',(blob,str(properties.get('name','')),json.dumps(properties,ensure_ascii=False)));count+=1;bounds.append(geometry.bounds)
            if bounds:db.execute("UPDATE gpkg_contents SET min_x=?,min_y=?,max_x=?,max_y=? WHERE table_name='features'",(min(b[0] for b in bounds),min(b[1] for b in bounds),max(b[2] for b in bounds),max(b[3] for b in bounds)))
        if source_id and bbox and zooms:
            get_source(source_id);storage=FileSystemStorage(cache_dir);limit=20037508.342789244
            db.execute('CREATE TABLE imagery(id INTEGER PRIMARY KEY AUTOINCREMENT,zoom_level INTEGER NOT NULL,tile_column INTEGER NOT NULL,tile_row INTEGER NOT NULL,tile_data BLOB NOT NULL,UNIQUE(zoom_level,tile_column,tile_row))')
            converter=Transformer.from_crs(4326,3857,always_xy=True);w,s=converter.transform(bbox[0],bbox[1]);e,n=converter.transform(bbox[2],bbox[3])
            db.execute("INSERT INTO gpkg_contents(table_name,data_type,identifier,description,min_x,min_y,max_x,max_y,srs_id) VALUES('imagery','tiles',?,?,?,?,?,?,3857)",(source_id,'Cached tiles only; missing tiles remain absent',w,s,e,n))
            db.execute("INSERT INTO gpkg_tile_matrix_set VALUES('imagery',3857,?,?,?,?)",(-limit,-limit,limit,limit))
            planned=0;tile_extents=[]
            for z in sorted(set(zooms)):
                if isinstance(z,bool) or not isinstance(z,int) or not 0<=z<=22:raise ValueError('Invalid tile zoom.')
                x0,y1=lon_lat_to_tile(bbox[0],bbox[1],z);x1,y0=lon_lat_to_tile(bbox[2],bbox[3],z);planned+=(x1-x0+1)*(y1-y0+1)
                if planned>100000:raise ValueError('Limit GeoPackage to 100,000 selected tiles.')
                db.execute("INSERT INTO gpkg_tile_matrix VALUES('imagery',?,?,?,?,?,?,?)",(z,2**z,2**z,256,256,2*limit/(256*2**z),2*limit/(256*2**z)))
                for y in range(y0,y1+1):
                    for x in range(x0,x1+1):
                        raw=next((raw for ext in IMAGE_EXTENSIONS if (raw:=storage.load_tile(source_id,z,x,y,ext))),None)
                        if not raw:continue
                        image=Image.open(io.BytesIO(raw));image.load()
                        if image.size!=(256,256):raise ValueError('GeoPackage requires 256×256 map tiles.')
                        if not(raw.startswith(b'\x89PNG') or raw.startswith(b'\xff\xd8')):
                            buf=io.BytesIO();image.convert('RGBA').save(buf,format='PNG');raw=buf.getvalue()
                        db.execute('INSERT INTO imagery(zoom_level,tile_column,tile_row,tile_data) VALUES(?,?,?,?)',(z,x,y,raw));tiles+=1
                        span=2*limit/2**z;tile_extents.append((-limit+x*span,limit-(y+1)*span,-limit+(x+1)*span,limit-y*span))
            if tile_extents:db.execute("UPDATE gpkg_contents SET min_x=?,min_y=?,max_x=?,max_y=? WHERE table_name='imagery'",(min(b[0] for b in tile_extents),min(b[1] for b in tile_extents),max(b[2] for b in tile_extents),max(b[3] for b in tile_extents)))
            db.execute('CREATE TABLE studio_source(source_id TEXT NOT NULL)');db.execute('INSERT INTO studio_source VALUES(?)',(source_id,))
        if count+tiles==0:raise ValueError('No features or cached tiles to export.')
        db.commit()
        if db.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('GeoPackage relationship validation failed.')
    except Exception:
        db.close();path.unlink(missing_ok=True);raise
    db.close();return {'files':[{'name':'GeoPackage','url':download(path)}],'statistics':{'features':count,'tiles':tiles}}

def read_package(path,import_tiles=False,source_id=None,cache_dir=None):
    # User files are untrusted SQLite input: read-only, no extensions or SQL identifiers interpolated unchecked.
    db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True);db.enable_load_extension(False)
    try:
        if db.execute('PRAGMA application_id').fetchone()[0]!=1196444487:raise ValueError('Not a GeoPackage.')
        layers=db.execute('SELECT table_name,data_type,srs_id FROM gpkg_contents').fetchall();features=[];tiles=0
        def quoted(value):return '"'+value.replace('"','""')+'"'
        for table,kind,srs in layers:
            if kind=='features':
                column,=db.execute('SELECT column_name FROM gpkg_geometry_columns WHERE table_name=?',(table,)).fetchone()
                definition=db.execute('SELECT definition FROM gpkg_spatial_ref_sys WHERE srs_id=?',(srs,)).fetchone()[0]
                converter=Transformer.from_crs(CRS.from_user_input(definition),4326,always_xy=True)
                cursor=db.execute('SELECT * FROM '+quoted(table)+' LIMIT 50001');names=[d[0] for d in cursor.description]
                for row in cursor:
                    if len(features)>=50000:raise ValueError('Import limited to 50,000 features.')
                    item=dict(zip(names,row));raw=item.pop(column)
                    if raw is None:continue
                    if raw[:2]!=b'GP' or raw[2]!=0:raise ValueError('Unsupported GeoPackage geometry header.')
                    flags=raw[3];envelope=(flags>>1)&7
                    if envelope not in (0,1,2,3,4):raise ValueError('Invalid geometry envelope.')
                    offset=8+{0:0,1:32,2:48,3:48,4:64}[envelope]
                    geometry=transform(converter.transform,wkb.loads(raw[offset:]))
                    properties={k:v for k,v in item.items() if not isinstance(v,bytes)}
                    if 'properties' in properties:
                        try:properties.update(json.loads(properties.pop('properties')))
                        except (ValueError,TypeError):pass
                    features.append({'type':'Feature','properties':properties,'geometry':mapping(geometry)})
            elif kind=='tiles' and import_tiles:
                if srs!=3857:raise ValueError('Cache import currently requires EPSG:3857 tiles.')
                if not source_id:raise ValueError('Select a matching target map source for cache import.')
                get_source(source_id);storage=FileSystemStorage(cache_dir)
                extent=db.execute('SELECT min_x,min_y,max_x,max_y FROM gpkg_tile_matrix_set WHERE table_name=?',(table,)).fetchone();limit=20037508.342789244
                if any(abs(a-b)>1 for a,b in zip(extent,(-limit,-limit,limit,limit))):raise ValueError('Tile package must use the global XYZ matrix extent.')
                matrices=db.execute('SELECT zoom_level,matrix_width,matrix_height,tile_width,tile_height FROM gpkg_tile_matrix WHERE table_name=?',(table,)).fetchall()
                if any(not 0<=z<=22 or mw!=2**z or mh!=2**z or tw!=256 or th!=256 for z,mw,mh,tw,th in matrices):raise ValueError('Tile matrix is not a standard 256px XYZ pyramid.')
                for z,x,y,raw in db.execute('SELECT zoom_level,tile_column,tile_row,tile_data FROM '+quoted(table)+' LIMIT 100001'):
                    if tiles>=100000:raise ValueError('Tile import limited to 100,000.')
                    with Image.open(io.BytesIO(raw)) as image:image.verify()
                    storage.save_tile(source_id,z,x,y,raw);tiles+=1
        return {'geojson':{'type':'FeatureCollection','features':features},'statistics':{'features':len(features),'imported_tiles':tiles,'layers':[l[0] for l in layers]}}
    finally:db.close()
