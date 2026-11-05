import React, { useState } from 'react';
import { DraggableWindow } from './DraggableWindow';
import {
  X,
  Play,
  Copy,
  Terminal,
  FileCode,
  Check,
  RotateCcw,
  Sparkles,
  BookOpen,
  Layers,
  Database
} from 'lucide-react';

interface PythonStudioModalProps {
  isOpen: boolean;
  onClose: () => void;
  lang: 'ar' | 'en';
}

const TEMPLATES = [
  {
    id: 'downloader',
    title: 'تحميل البلاطات والتخزين (Tile Downloader & Storage)',
    titleEn: 'Batch Tile Downloader & Storage',
    code: `import json
from sas_planet_py.tile_downloader import TileDownloader
from sas_planet_py.tile_storage import FileSystemStorage

# 1. Initialize Downloader
downloader = TileDownloader()

# 2. Setup job covering Cairo center (lat: 30.04, lon: 31.23)
job = downloader.create_job(
    job_id="test_run",
    source_id="google_sat",
    bbox=(31.22, 30.03, 31.25, 30.05),
    zooms=[14, 15],
    storage_type="gm1",
    storage_path=None,
    concurrency=4
)

print(f"Total tiles calculated in region: {job.total_tiles}")
downloader.run_job(job)
print("Job finished:", json.dumps(job.to_dict(), indent=2))
`
  },
  {
    id: 'stitcher',
    title: 'دمج الصور وملف الإسناد الجغرافي (Stitcher & WorldFile)',
    titleEn: 'Stitcher & WorldFile Generator',
    code: `import json
from sas_planet_py.tile_stitcher import TileStitcher

# Stitch map tiles of selected region into a georeferenced raster
res = TileStitcher.stitch_bbox(
    source_id="esri_satellite",
    bbox=(31.22, 30.03, 31.25, 30.05),
    zoom=14,
    output_image_path="public/exports/studio_stitch.bmp",
    cache_dir=None
)

print("Stitching completed successfully:")
print(json.dumps(res, indent=2))
`
  },
  {
    id: 'geocalc',
    title: 'الحسابات الجيوديسية والمساحات (Vincenty & Geocalc)',
    titleEn: 'Vincenty Geodesic & Polygon Area',
    code: `from sas_planet_py.geocalc import vincenty_distance, polygon_area_sq_meters, path_length

# Coordinates of Alexandria to Cairo
p1 = (31.2001, 29.9187) # Alexandria (lat, lon)
p2 = (30.0444, 31.2357) # Cairo (lat, lon)

res = vincenty_distance(p1[0], p1[1], p2[0], p2[1])
print(f"Vincenty Ellipsoidal Distance: {res['distance'] / 1000.0:.2f} km")
print(f"Initial Bearing: {res['initial_bearing']}° | Final Bearing: {res['final_bearing']}°")

# Polygon Area Calculation (Spherical Excess)
triangle = [
    (30.0, 31.0),
    (30.5, 31.2),
    (30.2, 31.6)
]
area = polygon_area_sq_meters(triangle)
print(f"Geodesic Polygon Area: {area:,.2f} m² ({area / 1e6:.2f} km²)")
`
  },
  {
    id: 'projections',
    title: 'التحويلات الإسقاطية وبلاطات الخرائط (Projections & UTM)',
    titleEn: 'Projections & Tile Math',
    code: `from sas_planet_py.projections import (
    lon_lat_to_tile,
    tile_to_lon_lat,
    tile_bounds,
    lat_lon_to_utm,
    to_dms,
    MercatorProjection,
    EllipsoidalMercatorProjection
)

lat, lon, zoom = 30.0444, 31.2357, 15
tx, ty = lon_lat_to_tile(lon, lat, zoom)
nw_lon, nw_lat = tile_to_lon_lat(tx, ty, zoom)
bounds = tile_bounds(tx, ty, zoom)
utm = lat_lon_to_utm(lat, lon)

print(f"Decimal: {lat}, {lon} -> DMS: {to_dms(lat, True)}, {to_dms(lon, False)}")
print(f"Tile at Z{zoom}: X={tx}, Y={ty}")
print(f"Tile Bounding Box: {bounds}")
print(f"UTM: {utm['formatted']}")

# Forward Mercator meters
mx, my = MercatorProjection.forward(lon, lat)
print(f"EPSG:3857 Meters: X={mx:.2f}, Y={my:.2f}")
`
  },
  {
    id: 'mbtiles',
    title: 'إنشاء حاوية MBTiles SQLite (MBTiles Storage)',
    titleEn: 'MBTiles SQLite Builder',
    code: `import os
from sas_planet_py.tile_storage import MBTilesStorage

db_file = "public/exports/sample_mbtiles.mbtiles"
if os.path.exists(db_file):
    os.remove(db_file)

storage = MBTilesStorage(db_file)
storage.set_metadata("name", "Cairo Pyramids Map")
storage.set_metadata("format", "jpg")
storage.set_metadata("minzoom", "10")
storage.set_metadata("maxzoom", "15")

# Save a dummy tile in TMS coordinates
storage.save_tile(12, 2403, 1689, b"\\xFF\\xD8\\xFF\\xE0\\x00\\x10JFIF\\x00DummyTileData")

print("MBTiles Metadata:", storage.get_metadata())
print("Tile count in database:", storage.get_tile_count())
storage.close()
print(f"File created: {db_file} ({os.path.getsize(db_file)} bytes)")
`
  },
  {
    id: 'nord_sahara',
    title: 'نظام UTM Nord Sahara 1959 / Voirol 1960',
    titleEn: 'UTM Nord Sahara (Clarke 1880 RGS)',
    code: `import json
from sas_planet_py.nord_sahara import wgs84_to_utm_nord_sahara, utm_nord_sahara_to_wgs84

# Test Algiers coordinates (WGS84 GPS Lat/Lon)
wgs_lat, wgs_lon = 36.7538, 3.0588

# 1. Forward transformation: WGS84 -> UTM Nord Sahara (Clarke 1880 RGS)
utm_ns = wgs84_to_utm_nord_sahara(wgs_lat, wgs_lon)
print("=== WGS84 to UTM Nord Sahara ===")
print("Datum:", utm_ns['datum'])
print("Projection EPSG:", utm_ns['epsg'])
print("Formatted:", utm_ns['formatted'])
print(f"Easting: {utm_ns['easting']} m | Northing: {utm_ns['northing']} m | Zone: {utm_ns['zone']}N")
print(f"Nord Sahara Lat/Lon: {utm_ns['lat_nord_sahara']}°, {utm_ns['lon_nord_sahara']}°")

# 2. Inverse transformation: UTM Nord Sahara -> WGS84 GPS
inv = utm_nord_sahara_to_wgs84(utm_ns['easting'], utm_ns['northing'], utm_ns['zone'])
print("\\n=== Inverse back to WGS84 GPS ===")
print(f"WGS84: {inv['wgs84_lat']}°, {inv['wgs84_lon']}°")
`
  },
  {
    id: 'topo_contours',
    title: 'استخراج خطوط الكنتور الطبوغرافية (Contours & DEM)',
    titleEn: 'Topographic Contours & DEM',
    code: `import json
from sas_planet_py.topography import TopographicEngine

# Region Bounding Box: [min_lon, min_lat, max_lon, max_lat]
bbox = (31.10, 29.90, 31.25, 30.05)
interval = 25.0  # 25m contour interval

print(f"Generating DEM and Contours for BBox: {bbox} at {interval}m interval...")
contours = TopographicEngine.generate_contour_geojson(bbox, interval=interval, rows=25, cols=25)

print(f"Generated {len(contours['features'])} contour line levels.")
print(f"Min Elevation: {contours['properties']['min_elevation']} m")
print(f"Max Elevation: {contours['properties']['max_elevation']} m")

# Sample contour feature
sample = contours['features'][0]
print(f"First contour line level: {sample['properties']['elevation']}m (Index: {sample['properties']['is_index']})")
`
  },
  {
    id: 'spatial_analysis',
    title: 'تحليل نطاقات الحرم وخط الرؤية (Buffer & Viewshed)',
    titleEn: 'Spatial Buffer & Line of Sight',
    code: `import json
from sas_planet_py.analysis import SpatialAnalysis

center_lat, center_lon = 30.0444, 31.2357

# 1. Geodesic Buffer Analysis (1000m radius)
buffer_ring = SpatialAnalysis.point_buffer(center_lat, center_lon, radius_meters=1000.0, num_points=16)
print(f"Geodesic Buffer (1km) created with {len(buffer_ring)} perimeter points.")

# 2. Slope and Terrain Hazard Analysis
slope = SpatialAnalysis.analyze_slope_at(center_lat, center_lon)
print(f"\\nTerrain Slope at {center_lat}, {center_lon}:")
print(f"Slope: {slope['slope_degrees']}° ({slope['slope_percent']}%) | Aspect: {slope['aspect_degrees']}°")
print(f"Hazard: {slope['hazard_category']}")

# 3. Line of Sight (LOS) between 2 points
target_lat, target_lon = 30.08, 31.26
los = SpatialAnalysis.line_of_sight((center_lat, center_lon), (target_lat, target_lon), obs_height_m=2.0, target_height_m=2.0)
print(f"\\nLine of Sight to ({target_lat}, {target_lon}):")
print(f"Distance: {los['total_distance_km']} km | Visible: {los['visible']}")
`
  }
];

export const PythonStudioModal: React.FC<PythonStudioModalProps> = ({
  isOpen,
  onClose,
  lang
}) => {
  const isAr = lang === 'ar';
  const [selectedTemplate, setSelectedTemplate] = useState(TEMPLATES[0]);
  const [code, setCode] = useState(TEMPLATES[0].code);
  const [terminalOutput, setTerminalOutput] = useState<string>('');
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);

  if (!isOpen) return null;

  const handleSelectTemplate = (t: typeof TEMPLATES[0]) => {
    setSelectedTemplate(t);
    setCode(t.code);
    setTerminalOutput('');
  };

  const handleRun = async () => {
    setIsRunning(true);
    setTerminalOutput(isAr ? '>>> جاري تشغيل الشفرة في بيئة بايثون...\n' : '>>> Running Python script in backend...\n');
    try {
      const res = await fetch('/api/python/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code })
      });
      const data = await res.json();
      let output = `>>> Exit code: ${data.code} (${data.elapsed}s)\n`;
      if (data.stdout) output += data.stdout;
      if (data.stderr) output += `\n[STDERR]:\n${data.stderr}`;
      setTerminalOutput((prev) => prev + output);
    } catch (e: any) {
      setTerminalOutput((prev) => prev + `\nNetwork/API Error: ${e.message}`);
    } finally {
      setIsRunning(false);
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <DraggableWindow>
      <div className="relative w-full max-w-5xl h-[88vh] flex flex-col bg-slate-900 border border-slate-700 rounded-lg shadow-2xl overflow-hidden text-slate-200">
        {/* Title Bar */}
        <div className="flex items-center justify-between px-4 py-2.5 bg-slate-950 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <Terminal className="w-5 h-5 text-emerald-400" />
            <h2 className="text-sm font-bold text-white">
              {isAr ? 'منصة بايثون التفاعلية لبرنامج SAS.Planet' : 'SAS.Planet Python GIS Studio & REPL'}
            </h2>
            <span className="text-[10px] bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 px-2 py-0.5 rounded font-mono">
              sas_planet_py v26.08.08
            </span>
          </div>

          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Studio Content Grid */}
        <div className="flex-1 grid grid-cols-1 md:grid-cols-12 overflow-hidden">
          {/* Left / Start: Template Scripts Navigator */}
          <div className="md:col-span-4 bg-slate-950/80 border-e border-slate-800 p-3 flex flex-col gap-2 overflow-y-auto">
            <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5 px-1">
              <BookOpen className="w-3.5 h-3.5 text-blue-400" />
              <span>{isAr ? 'نماذج سكربتات جاهزة للتشغيل:' : 'Ready-to-Run Scripts:'}</span>
            </div>

            <div className="space-y-1.5">
              {TEMPLATES.map((t) => (
                <button
                  key={t.id}
                  onClick={() => handleSelectTemplate(t)}
                  className={`w-full text-start p-2.5 rounded-lg text-xs transition-all border ${
                    selectedTemplate.id === t.id
                      ? 'bg-emerald-600/20 border-emerald-500/50 text-emerald-200 font-semibold shadow-xs'
                      : 'bg-slate-900/60 border-slate-800/80 text-slate-300 hover:bg-slate-800'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <FileCode className="w-4 h-4 text-emerald-400 shrink-0" />
                    <span className="leading-snug">{isAr ? t.title : t.titleEn}</span>
                  </div>
                </button>
              ))}
            </div>

            {/* Architecture Card */}
            <div className="mt-auto p-3 rounded-lg bg-slate-900 border border-slate-800 text-[11px] text-slate-400 space-y-1.5">
              <div className="font-semibold text-slate-200 flex items-center gap-1">
                <Sparkles className="w-3.5 h-3.5 text-amber-400" />
                <span>{isAr ? 'عن مكتبة sas_planet_py:' : 'About sas_planet_py:'}</span>
              </div>
              <p className="leading-relaxed">
                {isAr
                  ? 'إعادة صياغة كاملة ونظيفة بالبايثون لجميع وحدات دلفي (Delphi/Pascal) الأساسية في SAS.Planet، بما في ذلك محرك التحميل المتعدد، حسابات فنسنتي الجيوديسية، والتخزين في صيغ SAS وMBTiles.'
                  : 'Pure Python reproduction of SAS.Planet Delphi/Pascal architecture: multi-threaded tile downloader, Vincenty geodetic calculations, and MBTiles SQLite storage.'}
              </p>
            </div>
          </div>

          {/* Right / End: Code Editor & Terminal */}
          <div className="md:col-span-8 flex flex-col bg-slate-900 overflow-hidden">
            {/* Editor Action Bar */}
            <div className="flex items-center justify-between px-3 py-2 bg-slate-950/90 border-b border-slate-800 text-xs">
              <span className="font-mono text-slate-300 text-[11px] font-semibold">
                {isAr ? selectedTemplate.title : selectedTemplate.titleEn}
              </span>

              <div className="flex items-center gap-2">
                <button
                  onClick={handleCopy}
                  className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
                >
                  {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copied ? (isAr ? 'تم النسخ!' : 'Copied!') : (isAr ? 'نسخ' : 'Copy')}</span>
                </button>

                <button
                  onClick={handleRun}
                  disabled={isRunning}
                  className="flex items-center gap-1.5 px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-bold transition-all shadow-sm disabled:opacity-50"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                  <span>{isRunning ? (isAr ? 'جاري التشغيل...' : 'Running...') : (isAr ? 'تشغيل الشفرة (Run)' : 'Run Script')}</span>
                </button>
              </div>
            </div>

            {/* Code Textarea */}
            <div className="flex-1 p-2 bg-slate-950 font-mono text-xs overflow-hidden">
              <textarea
                value={code}
                onChange={(e) => setCode(e.target.value)}
                spellCheck={false}
                className="w-full h-full p-2 bg-transparent text-emerald-300 outline-none resize-none leading-relaxed font-mono selection:bg-emerald-800/40"
              />
            </div>

            {/* Terminal Console Output */}
            <div className="h-48 border-t border-slate-800 bg-black/95 flex flex-col overflow-hidden">
              <div className="flex items-center justify-between px-3 py-1 bg-slate-950 border-b border-slate-800 text-[11px] text-slate-400 font-mono">
                <span className="flex items-center gap-1.5">
                  <Terminal className="w-3.5 h-3.5 text-emerald-400" />
                  <span>{isAr ? 'مخرجات الطرفية (Console Output)' : 'Console Output'}</span>
                </span>
                {terminalOutput && (
                  <button
                    onClick={() => setTerminalOutput('')}
                    className="hover:text-slate-200 transition-colors"
                  >
                    {isAr ? 'مسح المخرجات' : 'Clear'}
                  </button>
                )}
              </div>
              <pre className="flex-1 p-2.5 text-slate-200 text-xs font-mono overflow-y-auto whitespace-pre-wrap leading-relaxed select-text">
                {terminalOutput || (isAr ? 'اضغط على "تشغيل الشفرة (Run)" لرؤية المخرجات الحية هنا...' : 'Click "Run Script" to see live Python execution output here...')}
              </pre>
            </div>
          </div>
        </div>
      </div>
    </DraggableWindow>
  );
};
