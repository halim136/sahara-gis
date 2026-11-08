import {portableLayout,resolveCacheLocation,cacheConfigPath} from './server/portablePaths';
import 'dotenv/config';
import {randomUUID} from 'node:crypto';
import {CacheJobs} from './server/cacheJobs';
import express from 'express';
import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import { MapDiskCache, TileError, tileSpec, sources as tileSources } from './server/mapCache';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PORT === undefined ? 3000 : Number(process.env.PORT);
const HOST = process.env.HOST || '127.0.0.1';
const layout=portableLayout(__dirname,process.env.SAS_PORTABLE);
const IS_PORTABLE = layout.portable;
const PORTABLE_ROOT=layout.root;
const CACHE_LOCATION_FILE=path.join(PORTABLE_ROOT,IS_PORTABLE?'data/cache-location.json':'cache/cache-location.json');
const PORTABLE_STATE = path.resolve(__dirname, '..', 'data', 'settings.json');

// Desktop/local browser traffic only; reject cross-site requests to the Python API.
app.use((req, res, next) => {
  const origin = req.headers.origin;
  if (req.headers['sec-fetch-site'] === 'cross-site') return res.status(403).json({error:'Cross-site access denied'});
  if (origin) {
    try { if (new URL(origin).host !== req.headers.host) return res.status(403).json({error:'Cross-origin access denied'}); }
    catch { return res.status(403).json({error:'Invalid origin'}); }
  }
  next();
});

app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));

// Ensure cache & exports directories exist
const CACHE_DIR = path.join(__dirname, 'cache');
const EXPORTS_DIR = path.join(__dirname, 'public', 'exports');
fs.mkdirSync(CACHE_DIR, { recursive: true });
fs.mkdirSync(EXPORTS_DIR, { recursive: true });
let cacheLocation=resolveCacheLocation(PORTABLE_ROOT,__dirname,CACHE_LOCATION_FILE);
let MAP_CACHE_DIR=cacheLocation.path;
process.env.SAS_MAP_CACHE = MAP_CACHE_DIR;
const mapCache = new MapDiskCache(MAP_CACHE_DIR, CACHE_DIR);
await mapCache.initialize();

// Serve static exports
app.use('/exports', express.static(EXPORTS_DIR));
app.use('/fonts',express.static(path.join(__dirname,'public/fonts')));
app.use('/assets/sasplanet',express.static(path.join(__dirname,'public/assets/sasplanet')));

// Detect Python executable: 'python' on Windows, 'python3' on Linux/macOS
const bundledPython = path.resolve(__dirname, '..', 'runtime', 'python', 'python.exe');
const developmentPython=path.join(__dirname,'build','gis-python','python.exe');
const PYTHON_CMD = process.env.SAS_PYTHON || (fs.existsSync(bundledPython) ? bundledPython : fs.existsSync(developmentPython)?developmentPython:(process.platform === 'win32' ? 'python' : 'python3'));

app.get('/api/health', (_req, res) => res.json({success:true, app:'sasplanet-gis', displayName:'Sahara GIS', desktopSupport:true, portable:IS_PORTABLE, instance:process.env.SAS_INSTANCE_ID || '', node:process.version}));
const portableKeys = ['sas:settings:v1','sas:saved-views:v1','sas:last-view:v1','sas_offline_mode','sas:marks:v1','sas:analyses:v1','sas:camera3d:v1','sas:field:v1','sas:windows:v1','sas:last-source:v1'];
app.get('/api/portable/state', (_req, res) => {
  let state:Record<string,string> = {};
  if (IS_PORTABLE && fs.existsSync(PORTABLE_STATE)) {
    try { const raw = JSON.parse(fs.readFileSync(PORTABLE_STATE,'utf8')); for (const key of portableKeys) if (typeof raw[key]==='string') state[key]=raw[key]; } catch {}
  }
  res.json({portable:IS_PORTABLE,state});
});
app.post('/api/portable/state', (req,res) => {
  if (!IS_PORTABLE) return res.json({success:true,portable:false});
  const state:Record<string,string> = {};
  for(const key of portableKeys) if(typeof req.body?.[key]==='string' && req.body[key].length<=(key==='sas:marks:v1'?10000000:key==='sas:analyses:v1'||key==='sas:field:v1'?5000000:100000)) state[key]=req.body[key];
  try { fs.mkdirSync(path.dirname(PORTABLE_STATE),{recursive:true});fs.writeFileSync(PORTABLE_STATE+'.tmp',JSON.stringify(state),'utf8');fs.renameSync(PORTABLE_STATE+'.tmp',PORTABLE_STATE);res.json({success:true}); }
  catch {res.status(500).json({success:false,error:'Cannot save portable settings. Move the portable folder to a writable location.'});}
});

// Helper: Run Python inline command or module
function executePython(args: string[], input?: unknown): Promise<{ stdout: string; stderr: string; code: number }> {
  return new Promise((resolve) => {
    const py = spawn(PYTHON_CMD, args, {
      cwd: __dirname,
      windowsHide: true,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' }
    });
    py.stdin.on('error', () => {});
    py.stdin.end(input === undefined ? undefined : JSON.stringify(input));
    let stdout = ''; 
    let stderr = '';

    py.stdout.on('data', (data) => {
      stdout += data.toString();
    });

    py.stderr.on('data', (data) => {
      stderr += data.toString();
    });

    py.on('close', (code) => {
      resolve({ stdout, stderr, code: code ?? 0 });
    });

    py.on('error', (err) => {
      resolve({ stdout: '', stderr: err.message, code: 1 });
    });
  });
}

// In-memory jobs tracking
const activeJobs = new Map<string, any>();

// 1. Get Sources
app.get('/api/sources', async (req, res) => {
  const result = await executePython(['-m', 'sas_planet_py.cli', 'sources']);
  try {
    const data = JSON.parse(result.stdout);
    res.json({ success: true, sources: data });
  } catch (e) {
    res.status(500).json({ success: false, error: result.stderr || 'Failed to list sources' });
  }
});

// 2. Coordinate Conversion
app.post('/api/python/convert', async (req, res) => {
  const { lat, lon, zoom = 15 } = req.body;
  if (lat === undefined || lon === undefined) {
    return res.status(400).json({ error: 'lat and lon are required' });
  }
  const result = await executePython([
    '-m', 'sas_planet_py.cli', 'convert-coord',
    '--lat', String(lat),
    '--lon', String(lon),
    '--zoom', String(zoom)
  ]);
  try {
    const data = JSON.parse(result.stdout);
    res.json({ success: true, data });
  } catch (e) {
    res.status(500).json({ success: false, error: result.stderr });
  }
});

// 3. Geodesic Measurement (Distance & Area)
app.post('/api/python/measure', async (req, res) => {
  const { coords } = req.body; // e.g. [[lat, lon], ...]
  if (!coords || !Array.isArray(coords)) {
    return res.status(400).json({ error: 'coords array required' });
  }
  const coordStr = coords.map((c: [number, number]) => `${c[0]},${c[1]}`).join(';');
  const result = await executePython([
    '-m', 'sas_planet_py.cli', 'measure',
    '--coords', coordStr
  ]);
  try {
    const data = JSON.parse(result.stdout);
    res.json({ success: true, data });
  } catch (e) {
    res.status(500).json({ success: false, error: result.stderr });
  }
});

// 4. Elevation Profile
app.post('/api/python/elevation', async (req, res) => {
  const { coords, samples = 40, offline = false } = req.body;
  if (!Array.isArray(coords) || coords.length < 2 || coords.length > 1000 ||
      coords.some((c: any) => !Array.isArray(c) || c.length !== 2 || !c.every((n: any) => typeof n === 'number' && Number.isFinite(n)) || Math.abs(c[0]) > 85 || Math.abs(c[1]) > 180) ||
      !Number.isInteger(samples) || samples < 2 || samples > 512 || typeof offline !== 'boolean') {
    return res.status(400).json({ success: false, error: 'Use valid coordinates and 2–512 samples.' });
  }
  const result = await executePython(['-c', 'import json,sys; from sas_planet_py.geocalc import generate_elevation_profile; p=json.load(sys.stdin); print(json.dumps(generate_elevation_profile(**p),allow_nan=False))'], { coords, num_samples: samples, offline });
  if (result.code !== 0) return res.status(422).json({ success: false, error: terrainError(result.stderr) });
  try { res.json({ success: true, profile: JSON.parse(result.stdout) }); }
  catch { res.status(500).json({ success: false, error: 'Cannot read elevation profile.' }); }
});

// 5. Run User Python Script (Interactive Console)
app.post('/api/python/run', async (req, res) => {
  const { code } = req.body;
  if (!code) {
    return res.status(400).json({ error: 'Python code required' });
  }
  const tmpScriptPath = path.join(__dirname, 'temp_run.py');
  fs.writeFileSync(tmpScriptPath, code, 'utf-8');

  const startTime = Date.now();
  const result = await executePython(['temp_run.py']);
  const elapsed = (Date.now() - startTime) / 1000;

  try {
    if (fs.existsSync(tmpScriptPath)) {
      fs.unlinkSync(tmpScriptPath);
    }
  } catch (_) {}

  res.json({
    success: result.code === 0,
    stdout: result.stdout,
    stderr: result.stderr,
    code: result.code,
    elapsed
  });
});

// 6. Batch Download
app.post('/api/python/download-batch', async (req, res) => {
  const { source_id = 'google_sat', bbox, zooms = [15], storage_type = 'gm1' } = req.body;
  if (!Object.hasOwn(tileSources,source_id)||!tileSources[source_id].url_template||!['gm1','sas','osm','tms','mbtiles'].includes(storage_type)||
      !Array.isArray(zooms)||!zooms.length||zooms.some((z:unknown)=>typeof z!=='number'||!Number.isInteger(z)||z<0||z>tileSources[source_id].max_zoom)) {
    return res.status(400).json({error:'Invalid map source, zooms or storage type'});
  }
  if (!Array.isArray(bbox)||bbox.length!==4||bbox.some((v:unknown)=>typeof v!=='number'||!Number.isFinite(v))||
      !(bbox[0]>=-180&&bbox[0]<bbox[2]&&bbox[2]<=180&&bbox[1]>=-85&&bbox[1]<bbox[3]&&bbox[3]<=85)) {
    return res.status(400).json({ error: 'Valid bbox [min_lon, min_lat, max_lon, max_lat] required' });
  }

  if(storage_type==='gm1'){try{const job=cacheJobs.add({source_id,bbox,zooms});return res.json({success:true,jobId:job.job_id,job});}catch(e:any){return res.status(400).json({error:e.message});}}
  const jobId = 'job_' + Date.now();
  const jobStatus = {
    job_id: jobId,
    source_id,
    bbox,
    zooms,
    storage_type,
    status: 'running',
    progress_percent: 0,
    downloaded: 0,
    cached: 0,
    failed: 0,
    total_tiles: 0,
    speed_kb_s: 0
  };
  activeJobs.set(jobId, jobStatus);

  // Run python downloader
  const pyCode = `
import json,sys
from sas_planet_py.tile_downloader import TileDownloader
p=json.load(sys.stdin)
downloader = TileDownloader()
job = downloader.create_job(**p)
def on_progress(p):
    print("PROGRESS:" + json.dumps(p), flush=True)

downloader.run_job(job, on_progress)
print("FINAL:" + json.dumps(job.to_dict()))
`;

  const py = spawn(PYTHON_CMD, ['-c', pyCode], {
    cwd: __dirname,
    windowsHide: true,
    env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' }
  });
  py.stdin.on('error',()=>{});
  py.stdin.end(JSON.stringify({job_id:jobId,source_id,bbox,zooms,storage_type,
    storage_path:storage_type==='mbtiles'?path.join(MAP_CACHE_DIR,jobId+'.mbtiles'):MAP_CACHE_DIR}));
  let progressBuffer='';
  py.stdout.on('data', (chunk) => {
    progressBuffer+=chunk.toString();
    const lines=progressBuffer.split(/\r?\n/);progressBuffer=lines.pop()||'';
    for (const line of lines) {
      if (line.startsWith('PROGRESS:')) {
        try {
          const p = JSON.parse(line.substring(9));
          activeJobs.set(jobId, p);
        } catch (_) {}
      } else if (line.startsWith('FINAL:')) {
        try {
          const finalData = JSON.parse(line.substring(6));
          activeJobs.set(jobId, finalData);
        } catch (_) {}
      }
    }
  });

  let downloadError='';
  py.stderr.on('data',chunk=>{downloadError+=chunk.toString();});
  py.on('error',error=>{const job=activeJobs.get(jobId);if(job){job.status='error';job.error=error.message;}});
  py.on('close', (code) => {
    const cur = activeJobs.get(jobId);
    if (cur) {
      cur.status = code === 0 ? 'completed' : 'error';
      if(code!==0)cur.error=downloadError.trim();
    }
  });

  res.json({ success: true, jobId, job: jobStatus });
});

// 7. Get Download Status
app.get('/api/python/download-status/:id', (req, res) => {
  const job = activeJobs.get(req.params.id)||cacheJobs.list().find(j=>j.job_id===req.params.id);
  if (!job) {
    return res.status(404).json({ error: 'Job not found' });
  }
  res.json(job);
});

// 8. Stitch Tiles
app.post('/api/python/stitch', async (req, res) => {
  const { source_id = 'google_sat', bbox, zoom = 14, format = 'bmp', target_crs = 'EPSG:3857' } = req.body;
  const supportedCrs = new Set(['EPSG:3857','EPSG:4326','EPSG:30729','EPSG:30730','EPSG:30731','EPSG:30732']);
  if (!Array.isArray(bbox) || bbox.length !== 4 || bbox.some((v:any)=>typeof v !== 'number' || !Number.isFinite(v)) || !supportedCrs.has(target_crs)) {
    return res.status(400).json({ error: 'Valid bbox required' });
  }

  let ext = 'bmp';
  if (format === 'jpg' || format === 'jpeg') ext = 'jpg';
  else if (format === 'png') ext = 'png';
  else if (format === 'geotiff' || format === 'tif' || format === 'tiff') ext = 'tif';
  else if (format === 'jp2' || format === 'jpeg2000' || format === 'ecw') ext = 'jp2';

  const outFileName = `stitch_${source_id}_z${zoom}_${Date.now()}.${ext}`;
  const outFilePath = path.join(EXPORTS_DIR, outFileName);
  const outFilePathPy = outFilePath.replace(/\\/g, '/');

  const pyCode = `
import json
from sas_planet_py.tile_stitcher import TileStitcher

res = TileStitcher.stitch_bbox(
    source_id=${JSON.stringify(source_id)},
    bbox=tuple(${JSON.stringify(bbox)}),
    zoom=${zoom},
    output_image_path=${JSON.stringify(outFilePathPy)},
    target_crs=${JSON.stringify(target_crs)}
)
print(json.dumps(res))
`;

  const result = await executePython(['-c', pyCode]);
  try {
    const data = JSON.parse(result.stdout);
    const wfExt = ext === 'jpg' ? '.jgw' : (ext === 'png' ? '.pgw' : (ext === 'tif' ? '.tfw' : (ext === 'jp2' ? '.j2w' : '.bpw')));
    // A streamed large raster is always written as GeoTIFF, so trust the real paths
    // the engine returned rather than the originally requested extension.
    const imgName = path.basename(data.image_path || outFileName);
    const wfName = path.basename(data.world_file_path || outFileName.replace(`.${ext}`, wfExt));
    data.download_url = `/exports/${imgName}`;
    data.world_file_url = `/exports/${wfName}`;
    data.projection_file_url = `/exports/${path.basename(data.projection_file_path)}`;
    res.json({ success: true, result: data });
  } catch (e) {
    res.status(500).json({ success: false, error: result.stderr || 'Stitching failed' });
  }
});

// 9. Vector Parse & Export
app.post('/api/python/vector/parse', async (req, res) => {
  const { content } = req.body;
  if (!content) return res.status(400).json({ error: 'content required' });

  const pyCode = `
import json
from sas_planet_py.vector_formats import parse_vector_data
raw = ${JSON.stringify(content)}
res = parse_vector_data(raw)
print(json.dumps(res))
`;
  const result = await executePython(['-c', pyCode]);
  try {
    res.json(JSON.parse(result.stdout));
  } catch (e) {
    res.status(500).json({ error: result.stderr });
  }
});

app.post('/api/python/vector/export', async (req, res) => {
  const { marks, format = 'geojson' } = req.body;
  const pyCode = `
from sas_planet_py.vector_formats import export_vector_data
marks = ${JSON.stringify(marks || [])}
out = export_vector_data(marks, '${format}')
print(out)
`;
  const result = await executePython(['-c', pyCode]);
  res.json({ success: true, content: result.stdout, format });
});

// Browsing, offline display and batch tools share cache_gmt on disk.
app.get('/api/cache/stats', async (_req,res) => {
  try{res.json({...await mapCache.stats(),location:cacheLocation});}catch{res.status(500).json({error:'Cannot read cache_gmt'});}
});
app.get('/api/cache/location',(_req,res)=>res.json({...cacheLocation,path:MAP_CACHE_DIR,portable:IS_PORTABLE,application_root:PORTABLE_ROOT}));
app.post('/api/cache/location',async(req,res)=>{try{
 if(cacheJobs.list().some((job:any)=>job.status==='running'))throw Error('Pause active downloads before changing the cache folder.');
 const selected=req.body?.path;if(typeof selected!=='string'||!path.isAbsolute(selected)||selected.length>32000)throw Error('Choose an absolute cache folder path.');
 const folder=path.resolve(selected);if(folder===path.parse(folder).root)throw Error('Select a cache folder, not a drive root.');
 const info=await fs.promises.stat(folder);if(!info.isDirectory())throw Error('Cache directory not found.');
 await mapCache.switchRoot(folder);MAP_CACHE_DIR=folder;process.env.SAS_MAP_CACHE=folder;
 cacheLocation={path:folder,default_path:path.join(PORTABLE_ROOT,'cache_gmt'),source:'configured',warning:''};
 fs.mkdirSync(path.dirname(CACHE_LOCATION_FILE),{recursive:true});fs.writeFileSync(CACHE_LOCATION_FILE+'.tmp',JSON.stringify({path:cacheConfigPath(PORTABLE_ROOT,folder)}),'utf8');fs.renameSync(CACHE_LOCATION_FILE+'.tmp',CACHE_LOCATION_FILE);
 res.json({success:true,...cacheLocation});
 }catch(e:any){res.status(400).json({success:false,error:e.message});}});
app.post('/api/cache/open', (_req,res) => {
 if(process.platform!=='win32')return res.status(400).json({success:false,path:MAP_CACHE_DIR,error:'Open this folder in your file manager.'});
 const executable=path.join(process.env.WINDIR||'C:/Windows','explorer.exe');
 const explorer=spawn(executable,[MAP_CACHE_DIR],{windowsHide:true,detached:true,stdio:'ignore'});
 explorer.on('error',(error)=>{if(!res.headersSent)res.status(500).json({success:false,path:MAP_CACHE_DIR,error:error.message});});
 explorer.on('spawn',()=>{explorer.unref();res.json({success:true,path:MAP_CACHE_DIR});});
});
const tileFailure=(error:any,res:express.Response)=>res.status(error instanceof TileError?error.status:502).set('Cache-Control','no-store').send(error.message||'Tile unavailable');
const sendTile=(tile:{bytes:Buffer;mime:string;hit:boolean},res:express.Response)=>res.set({'Content-Type':tile.mime,'Cache-Control':'no-store','X-SAS-Cache':tile.hit?'HIT':'SAVED'}).send(tile.bytes);
app.get('/api/maps/tile', async (req,res)=>{
  try{
    if(req.query.offline!==undefined&&!['0','1'].includes(String(req.query.offline)))throw new TileError(400,'Invalid offline option');
    const spec=tileSpec(req.query);
    sendTile(await mapCache.get(spec,req.query.offline==='1'),res);
  }catch(error){tileFailure(error,res);}
});
// Compatibility endpoint and migration of tiles saved by an older browser cache.
app.get('/api/cache/tile',async(req,res)=>{
  try{sendTile(await mapCache.get(tileSpec(req.query),true),res);}catch(error){tileFailure(error,res);}
});
app.post('/api/cache/tile',async(req,res)=>{
  try{
    const {source,z,x,y,content}=req.body;
    const spec=tileSpec({source,z:String(z),x:String(x),y:String(y)});
    if(typeof content!=='string'||content.length>12*1024*1024||!/^[A-Za-z0-9+/]*={0,2}$/.test(content))throw new TileError(400,'Invalid tile image');
    await mapCache.save(spec,Buffer.from(content,'base64'));res.json({success:true});
  }catch(error){tileFailure(error,res);}
});

// 11. UTM Nord Sahara Conversion
app.post('/api/python/nord-sahara/convert',async(req,res)=>{
  const {lat,lon,zone=0}=req.body;
  if(![lat,lon].every(v=>typeof v==='number'&&Number.isFinite(v))||![0,29,30,31,32].includes(zone))return res.status(400).json({success:false,error:'Use valid WGS84 coordinates and zone 0,29,30,31 or 32.'});
  const result=await executePython(['-c','import sys,json;from sas_planet_py.nord_sahara import wgs84_to_utm_nord_sahara;p=json.load(sys.stdin);print(json.dumps(wgs84_to_utm_nord_sahara(**p),allow_nan=False))'],{lat_wgs:lat,lon_wgs:lon,force_zone:zone});
  if(result.code!==0)return res.status(422).json({success:false,error:terrainError(result.stderr)});
  try{res.json({success:true,data:JSON.parse(result.stdout)});}catch{res.status(500).json({success:false,error:'Coordinate conversion failed.'});}
});
app.post('/api/python/nord-sahara/inverse',async(req,res)=>{
  const {easting,northing,zone=31}=req.body;
  if(![easting,northing].every(v=>typeof v==='number'&&Number.isFinite(v))||![29,30,31,32].includes(zone))return res.status(400).json({success:false,error:'Use finite Easting/Northing and zone 29,30,31 or 32.'});
  const result=await executePython(['-c','import sys,json;from sas_planet_py.nord_sahara import utm_nord_sahara_to_wgs84;p=json.load(sys.stdin);print(json.dumps(utm_nord_sahara_to_wgs84(**p),allow_nan=False))'],{easting,northing,zone});
  if(result.code!==0)return res.status(422).json({success:false,error:terrainError(result.stderr)});
  try{res.json({success:true,data:JSON.parse(result.stdout)});}catch{res.status(500).json({success:false,error:'Coordinate conversion failed.'});}
});

// Real terrain endpoints use JSON stdin, avoiding Python source interpolation.
function terrainOptions(body: any) {
  const { bbox, source = 'terrain', offline = false } = body;
  if (!Array.isArray(bbox) || bbox.length !== 4 || bbox.some((v: unknown) => typeof v !== 'number' || !Number.isFinite(v)) ||
      !(bbox[0] >= -180 && bbox[0] < bbox[2] && bbox[2] <= 180 && bbox[1] >= -85 && bbox[1] < bbox[3] && bbox[3] <= 85)) {
    throw new Error('Invalid bbox: use west, south, east, north within ±85° latitude.');
  }
  if ((!['terrain', 'srtm'].includes(source)&&!/^dem:[a-f0-9]{32}$/.test(source)) || typeof offline !== 'boolean') throw new Error('Invalid terrain source or offline option.');
  return { bbox, source, offline };
}
const terrainError = (stderr: string) => stderr.trim().split('\n').pop()?.replace(/^ValueError: /, '') || 'Terrain data unavailable';

app.post('/api/python/topo/import-hgt', (req, res) => {
  const { name, content } = req.body;
  if (typeof name !== 'string' || !/^[NS]\d{2}[EW]\d{3}\.hgt$/i.test(name) || typeof content !== 'string' ||
      !/^[A-Za-z0-9+/]*={0,2}$/.test(content)) return res.status(400).json({ success: false, error: 'Use an SRTM file named N36E003.hgt (or S/W).' });
  const lat = Number(name.slice(1, 3)) * (name[0].toUpperCase() === 'S' ? -1 : 1);
  const lon = Number(name.slice(4, 7)) * (name[3].toUpperCase() === 'W' ? -1 : 1);
  const data = Buffer.from(content, 'base64');
  if ((lat < -85 || lat >= 85 || lon < -180 || lon >= 180 || ![1201*1201*2, 3601*3601*2].includes(data.length))) {
    return res.status(400).json({ success: false, error: 'Invalid HGT bounds or size. Expected 1201×1201 or 3601×3601 signed 16-bit samples.' });
  }
  const dir = path.join(CACHE_DIR, 'terrain', 'srtm');
  fs.mkdirSync(dir, { recursive: true });
  const filename = name.slice(0, 7).toUpperCase() + '.hgt';
  fs.writeFileSync(path.join(dir, filename), data);
  res.json({ success: true, name: filename, bbox: [lon, lat, lon+1, lat+1] });
});

app.post('/api/python/topo/arcgis', async (req, res) => {
  try {
    const terrain = terrainOptions(req.body);
    const { resolution = 256, interval = 25, azimuth = 315, altitude = 45, z_factor = 1, hydrology = true, above_sea_only = true } = req.body;
    if (![64,128,256,512].includes(resolution) || typeof hydrology !== 'boolean' || typeof above_sea_only !== 'boolean' ||
        ![[interval,0.1,10000],[azimuth,0,360],[altitude,1,90],[z_factor,0.1,10]].every(([v,min,max]) => typeof v==='number' && Number.isFinite(v) && v>=min && v<=max)) {
      return res.status(400).json({success:false,error:'Invalid terrain analysis parameters.'});
    }
    const result = await executePython(['-c','import sys,json; from sas_planet_py.arcgis_export import build_package; p=json.load(sys.stdin); print(json.dumps(build_package(**p),allow_nan=False))'],
      {...terrain, resolution, interval, azimuth, altitude, z_factor, hydrology, above_sea_only, target_crs:req.body.target_crs||'EPSG:4326', output_dir:EXPORTS_DIR});
    if (result.code!==0) return res.status(422).json({success:false,error:terrainError(result.stderr)});
    res.json({success:true,result:JSON.parse(result.stdout)});
  } catch(e:any) {res.status(400).json({success:false,error:e.message});}
});

app.post('/api/python/topo/contour', async (req, res) => {
  try {
    const options = terrainOptions(req.body);
    const { interval = 25, resolution = 256, above_sea_only = true } = req.body;
    if (typeof interval !== 'number' || !Number.isFinite(interval) || interval <= 0 || interval > 10000 ||
        !Number.isInteger(resolution) || resolution < 32 || resolution > 512 || typeof above_sea_only !== 'boolean') {
      return res.status(400).json({ success: false, error: 'Use a positive contour interval and a grid resolution between 32 and 512.' });
    }
    const result = await executePython(['-c', 
      'import json,sys; from sas_planet_py.topography import TopographicEngine; p=json.load(sys.stdin); resolution=p.pop("resolution"); print(json.dumps(TopographicEngine.generate_contour_geojson(rows=resolution,cols=resolution,**p),allow_nan=False))'
    ], { ...options, interval, resolution, above_sea_only });
    if (result.code !== 0) return res.status(422).json({ success: false, error: terrainError(result.stderr) });
    res.json({ success: true, contours: JSON.parse(result.stdout) });
  } catch (e: any) {
    res.status(400).json({ success: false, error: e.message });
  }
});

app.post('/api/python/topo/render', async (req, res) => {
  try {
    const options = terrainOptions(req.body);
    const { width = 512, height = 512 } = req.body;
    if (![width, height].every(n => Number.isInteger(n) && n >= 32 && n <= 1024)) return res.status(400).json({ success: false, error: 'Raster size must be 32–1024 pixels.' });
    const outFileName = 'topo_' + Date.now() + '.bmp';
    const result = await executePython(['-c',
      'import json,sys; from sas_planet_py.topography import TopographicEngine; p=json.load(sys.stdin); print(json.dumps(TopographicEngine.render_topographic_bmp(**p),allow_nan=False))'
    ], { ...options, width, height, output_filepath: path.join(EXPORTS_DIR, outFileName) });
    if (result.code !== 0) return res.status(422).json({ success: false, error: terrainError(result.stderr) });
    const data = JSON.parse(result.stdout);
    data.download_url = '/exports/' + outFileName;
    data.world_file_url = '/exports/' + outFileName.replace('.bmp', '.bpw');
    res.json({ success: true, result: data });
  } catch (e: any) {
    res.status(400).json({ success: false, error: e.message });
  }
});

// 14. Spatial Analysis (Buffer, Slope, Viewshed, Convex Hull)
app.post('/api/python/analysis/buffer', async (req, res) => {
  const { lat, lon, radius = 1000.0 } = req.body;
  const pyCode = `
import json
from sas_planet_py.analysis import SpatialAnalysis
ring = SpatialAnalysis.point_buffer(${lat}, ${lon}, ${radius})
geojson = {
    "type": "Feature",
    "properties": {"radius_m": ${radius}, "center": [${lat}, ${lon}]},
    "geometry": {"type": "Polygon", "coordinates": [ring]}
}
print(json.dumps(geojson))
`;
  const result = await executePython(['-c', pyCode]);
  try {
    res.json({ success: true, buffer: JSON.parse(result.stdout) });
  } catch (e) {
    res.status(500).json({ success: false, error: result.stderr });
  }
});

app.post('/api/python/analysis/slope', async (req, res) => {
  const { lat, lon } = req.body;
  const pyCode = `
import json
from sas_planet_py.analysis import SpatialAnalysis
res = SpatialAnalysis.analyze_slope_at(${lat}, ${lon})
print(json.dumps(res))
`;
  const result = await executePython(['-c', pyCode]);
  try {
    res.json({ success: true, data: JSON.parse(result.stdout) });
  } catch (e) {
    res.status(500).json({ success: false, error: result.stderr });
  }
});

app.post('/api/python/analysis/viewshed', async (req, res) => {
  const { observer, target, obs_height = 2.0, target_height = 2.0 } = req.body;
  const pyCode = `
import json
from sas_planet_py.analysis import SpatialAnalysis
res = SpatialAnalysis.line_of_sight(
    tuple(${JSON.stringify(observer)}),
    tuple(${JSON.stringify(target)}),
    obs_height_m=${obs_height},
    target_height_m=${target_height}
)
print(json.dumps(res))
`;
  const result = await executePython(['-c', pyCode]);
  try {
    res.json({ success: true, data: JSON.parse(result.stdout) });
  } catch (e) {
    res.status(500).json({ success: false, error: result.stderr });
  }
});


// Persistent local cache jobs survive application restarts in a paused state.
const cacheJobs=new CacheJobs(mapCache,path.join(CACHE_DIR,'jobs'),async(bytes)=>{const result=await executePython(['-c','import sys,json,io,base64;from PIL import Image;b=base64.b64decode(json.load(sys.stdin)["image"]);im=Image.open(io.BytesIO(b));im.verify();im=Image.open(io.BytesIO(b));im.load();assert im.size==(256,256),"Tile must be 256x256"'],{image:bytes.toString('base64')});if(result.code!==0)throw Error('Downloaded repair image failed validation. Original retained.');});
app.get('/api/cache/jobs',(_req,res)=>res.json({jobs:cacheJobs.list()}));
app.post('/api/cache/jobs',(req,res)=>{try{res.json({success:true,job:cacheJobs.add(req.body)});}catch(e:any){res.status(400).json({error:e.message});}});
app.post('/api/cache/jobs/:id/:action',(req,res)=>{try{res.json({success:true,job:cacheJobs.control(req.params.id,req.params.action)});}catch(e:any){res.status(400).json({error:e.message});}});
app.post('/api/cache/coverage',async(req,res)=>{try{res.json(await cacheJobs.coverage(req.body));}catch(e:any){res.status(400).json({error:e.message});}});
const studioOperations=new Set(['field_gpx','field_track','field_grid','field_coordinates','field_coverage','field_route','field_package','project_save','project_list','project_load','project_backups','project_pack','project_import','catalog_list','catalog_import','catalog_import_marks','catalog_query','qa_checkpoints','qa_dem','qa_topology','validate_edit','atlas','print_split','print3d','sheets25k','scene3d','terrain_prepare','dem_list','dem_mosaic','dem_crop','watershed','viewshed','volume','veg_index','georeference','layout','buildings','gpkg_export','gpkg_import','cache_scan','cogo','geom_ops','terrain_path','digitize_raster','topo_sheet']);
app.post('/api/studio/upload/:kind',express.raw({type:'application/octet-stream',limit:'512mb'}),async(req,res)=>{
 try{const kind=req.params.kind;const original=path.basename(decodeURIComponent(String(req.headers['x-file-name']||'Local file')));const vectorExt=path.extname(original).toLowerCase();const allowedVectorExt=new Set(['.kml','.kmz','.gpx','.geojson','.json','.zip','.sml','.db3']);if(!['dem','scan','gpkg','project','raster','photo','vector'].includes(kind)||!Buffer.isBuffer(req.body)||(kind==='vector'&&!allowedVectorExt.has(vectorExt)))return res.status(400).json({error:'Select a supported binary file.'});
 const id=randomUUID().replaceAll('-','');const dir=kind==='dem'?path.join(CACHE_DIR,'terrain','geotiff'):path.join(CACHE_DIR,'studio');fs.mkdirSync(dir,{recursive:true});const extension=kind==='vector'?vectorExt:({dem:'.tif',scan:'.png',gpkg:'.gpkg',project:'.sasgis',raster:'.tif',photo:'.jpg'} as any)[kind];const filename=path.join(dir,id+extension);fs.writeFileSync(filename,req.body);
 const result=await executePython(['-m','sas_planet_py.studio','inspect'],{id,kind,extension,name:original});
 if(result.code!==0){fs.unlinkSync(filename);return res.status(422).json({error:terrainError(result.stderr)});}try{res.json({success:true,result:JSON.parse(result.stdout)});}catch{res.status(500).json({error:'Cannot inspect file.'});}}catch(e:any){res.status(400).json({error:e.message});}
});
app.post('/api/studio/:operation',async(req,res)=>{
 if(!studioOperations.has(req.params.operation))return res.status(404).json({error:'Unknown GIS operation.'});
 const result=await executePython(['-m','sas_planet_py.studio',req.params.operation],req.body);
 if(result.code!==0)return res.status(422).json({error:terrainError(result.stderr)});
 try{res.json({success:true,result:JSON.parse(result.stdout)});}catch{res.status(500).json({error:'Invalid GIS result.'});}
});

// Setup Vite development server
async function startServer() {
  const isDev = process.env.NODE_ENV !== 'production';

  if (isDev) {
    const { createServer: createViteServer } = await import('vite');
    const vite = await createViteServer({
      server: { middlewareMode: true, watch: { ignored: ['**/public/exports/**', '**/cache/**', '**/cache_gmt/**', '**/releases/**', '**/build/**', '**/__pycache__/**'] } },
      appType: 'spa'
    });
    app.use(vite.middlewares);
  } else {
    app.use(express.static(path.join(__dirname, 'dist')));
    app.get('*', (req, res) => {
      res.sendFile(path.join(__dirname, 'dist', 'index.html'));
    });
  }

  const listener = app.listen(PORT, HOST, () => {
    const address = listener.address();
    const port = address && typeof address === 'object' ? address.port : PORT;
    const url = 'http://' + (HOST === '0.0.0.0' ? '127.0.0.1' : HOST) + ':' + port + '/';
    if (process.env.SAS_READY_FILE) fs.writeFileSync(process.env.SAS_READY_FILE, JSON.stringify({url,port,pid:process.pid,instance:process.env.SAS_INSTANCE_ID || ''}),'utf8');
    console.log('[SAS.Planet Python Studio] Server running on ' + url);
  });
  listener.on('error', error => {console.error(error);process.exitCode=1;});
}

startServer();
