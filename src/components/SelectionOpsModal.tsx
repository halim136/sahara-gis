import React, { useState, useEffect, useRef } from 'react';
import {
  X,
  Download,
  Image as ImageIcon,
  Database,
  Terminal,
  Play,
  CheckCircle2,
  AlertCircle,
  Copy,
  ExternalLink,
  Layers,
  FileCheck,
  RefreshCw,
  Sliders,
  HardDrive,
  Upload,
  MapPin
} from 'lucide-react';
import { BoundingBox, MapSource, DownloadJobState } from '../types';
import { calculateTilesCountInBbox } from '../utils/geoUtils';

interface SelectionOpsModalProps {
  isOpen: boolean;
  onClose: () => void;
  bbox: BoundingBox;
  currentSource: MapSource;
  sources: MapSource[];
  lang: 'ar' | 'en';
  onCacheUpdated?: () => void;
  onImport?: (marks: any[]) => void;
  onApplyImportedSelection?: (bbox: BoundingBox, polygon?: [number, number][]) => void;
}

export const SelectionOpsModal: React.FC<SelectionOpsModalProps> = ({
  isOpen,
  onClose,
  bbox,
  currentSource,
  sources,
  lang,
  onCacheUpdated,
  onImport,
  onApplyImportedSelection
}) => {
  const isAr = lang === 'ar';
  const [activeTab, setActiveTab] = useState<'download' | 'stitch' | 'vector' | 'mbtiles' | 'python'>('download');

  // Download Tab State
  const [selectedSourceId, setSelectedSourceId] = useState<string>(currentSource.id);
  const [selectedZooms, setSelectedZooms] = useState<number[]>([14, 15, 16]);
  const [storageType, setStorageType] = useState<string>('gm1');
  const [concurrency, setConcurrency] = useState<number>(6);
  const [activeJob, setActiveJob] = useState<DownloadJobState | null>(null);
  const [downloadError, setDownloadError] = useState<string>('');

  // Stitch Tab State
  const [stitchZoom, setStitchZoom] = useState<number>(15);
  const [stitchFormat, setStitchFormat] = useState<string>('bmp');
  const [stitchCrs, setStitchCrs] = useState<string>('EPSG:3857');
  const [isStitching, setIsStitching] = useState<boolean>(false);
  const [stitchResult, setStitchResult] = useState<any>(null);
  const [stitchError, setStitchError] = useState<string>('');

  // Python Script Execution State
  const [pythonConsoleOutput, setPythonConsoleOutput] = useState<string>('');
  const [isRunningPython, setIsRunningPython] = useState<boolean>(false);
  const [copiedCode, setCopiedCode] = useState<boolean>(false);
  const vectorInput = useRef<HTMLInputElement>(null);
  const [vectorBusy, setVectorBusy] = useState(false);
  const [vectorError, setVectorError] = useState('');
  const [vectorResult, setVectorResult] = useState<any>(null);
  const [selectedVectorMark, setSelectedVectorMark] = useState(0);

  // Calculate tiles for download
  const { totalTiles, zoomBreakdown } = calculateTilesCountInBbox(
    bbox.min_lon,
    bbox.min_lat,
    bbox.max_lon,
    bbox.max_lat,
    selectedZooms
  );
  const estimatedSizeMb = (totalTiles * 18) / 1024; // avg ~18KB per tile

  // Calculate dimensions for stitch
  const stitchTiles = calculateTilesCountInBbox(
    bbox.min_lon,
    bbox.min_lat,
    bbox.max_lon,
    bbox.max_lat,
    [stitchZoom]
  );
  const stitchBreakdown = stitchTiles.zoomBreakdown[0] || { xCount: 1, yCount: 1, tiles: 1 };
  const stitchWidthPx = stitchBreakdown.xCount * 256;
  const stitchHeightPx = stitchBreakdown.yCount * 256;

  // Polling for download job status
  useEffect(() => {
    let interval: any = null;
    if (activeJob && (activeJob.status === 'running' || activeJob.status === 'idle' || activeJob.status === 'paused')) {
      interval = setInterval(async () => {
        try {
          const res = await fetch(`/api/python/download-status/${activeJob.job_id}`);
          if (res.ok) {
            const data = await res.json();
            setActiveJob(data);
            if (data.status === 'completed' || data.status === 'error') {
              clearInterval(interval);
              onCacheUpdated?.();
            }
          }
        } catch (_) {}
      }, 700);
    }
    return () => clearInterval(interval);
  }, [activeJob?.job_id, activeJob?.status]);

  if (!isOpen) return null;

  // Handle Start Download
  const handleStartDownload = async () => {
    setDownloadError('');
    try {
      const res = await fetch('/api/python/download-batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_id: selectedSourceId,
          bbox: [bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat],
          zooms: selectedZooms,
          storage_type: storageType,
          concurrency
        })
      });
      const data = await res.json();
      if (data.success) {
        setActiveJob(data.job);
      } else {
        setDownloadError(data.error || 'Failed to start download');
      }
    } catch (err: any) {
      setDownloadError(err.message || 'Network error');
    }
  };

  const controlJob=async(action:string)=>{if(!activeJob)return;const response=await fetch('/api/cache/jobs/'+activeJob.job_id+'/'+action,{method:'POST'});const data=await response.json();if(response.ok)setActiveJob(data.job);else setDownloadError(data.error);};
  // Handle Stitch
  const handleStartStitch = async () => {
    setIsStitching(true);
    setStitchError('');
    setStitchResult(null);

    try {
      const res = await fetch('/api/python/stitch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_id: selectedSourceId,
          bbox: [bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat],
          zoom: stitchZoom,
          format: stitchFormat,
          target_crs: stitchCrs
        })
      });
      const data = await res.json();
      if (data.success) {
        setStitchResult(data.result);
      } else {
        setStitchError(data.error || 'Stitching failed');
      }
    } catch (err: any) {
      setStitchError(err.message || 'Network error during stitch');
    } finally {
      setIsStitching(false);
    }
  };

  const handleVectorFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setVectorBusy(true); setVectorError(''); setVectorResult(null);
    try {
      const response = await fetch('/api/studio/upload/vector', {
        method: 'POST', headers: { 'Content-Type': 'application/octet-stream', 'X-File-Name': encodeURIComponent(file.name) }, body: file
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Vector import failed');
      setVectorResult(data.result); setSelectedVectorMark(0);
      onImport?.(data.result.marks || []);
    } catch (error: any) { setVectorError(error.message || 'Vector import failed'); }
    finally { setVectorBusy(false); }
  };

  const applyVectorSelection = () => {
    const mark = vectorResult?.marks?.[selectedVectorMark];
    const points: [number, number][] = mark?.type === 'point' ? [mark.coords] : mark?.coords || [];
    if (!points.length) return;
    const lons = points.map((p: [number, number]) => p[0]), lats = points.map((p: [number, number]) => p[1]);
    onApplyImportedSelection?.({ min_lon: Math.min(...lons), min_lat: Math.min(...lats), max_lon: Math.max(...lons), max_lat: Math.max(...lats) }, mark.type === 'polygon' ? points : undefined);
  };

  // Generate Python Code for current selection
  const generatedPythonCode = `#!/usr/bin/env python3
"""
SAS.Planet Batch Processing Script
Generated automatically for Region:
BBox: [${bbox.min_lon.toFixed(5)}, ${bbox.min_lat.toFixed(5)}, ${bbox.max_lon.toFixed(5)}, ${bbox.max_lat.toFixed(5)}]
Source: ${selectedSourceId}
"""

import sys
from sas_planet_py.tile_downloader import TileDownloader
from sas_planet_py.tile_stitcher import TileStitcher
from sas_planet_py.geocalc import vincenty_distance, polygon_area_sq_meters

bbox = (${bbox.min_lon.toFixed(6)}, ${bbox.min_lat.toFixed(6)}, ${bbox.max_lon.toFixed(6)}, ${bbox.max_lat.toFixed(6)})
source_id = "${selectedSourceId}"
zooms = ${JSON.stringify(selectedZooms)}

print("=== SAS.Planet Python Batch Processor ===")
print(f"Target BBox: {bbox}")
print(f"Source: {source_id} | Zooms: {zooms}")

# 1. Download tiles
downloader = TileDownloader()
job = downloader.create_job(
    job_id="script_batch",
    source_id=source_id,
    bbox=bbox,
    zooms=zooms,
    storage_type="${storageType}",
    storage_path=None,
    concurrency=${concurrency}
)

print(f"Downloading {job.total_tiles} tiles...")
def on_progress(p):
    sys.stdout.write(f"\\rProgress: {p['progress_percent']}% | Downloaded: {p['downloaded']} | Speed: {p['speed_kb_s']} KB/s")
    sys.stdout.flush()

downloader.run_job(job, on_progress)
print("\\nDownload finished successfully!")

# 2. Stitch high-resolution image with WorldFile
print("\\nStitching composite raster at zoom ${stitchZoom}...")
stitch_res = TileStitcher.stitch_bbox(
    source_id=source_id,
    bbox=bbox,
    zoom=${stitchZoom},
    output_image_path="public/exports/stitched_map.bmp"
)
print("Stitch completed:")
print(f"- Image: {stitch_res['image_path']} ({stitch_res['width']}x{stitch_res['height']} px)")
print(f"- WorldFile: {stitch_res['world_file_path']}")
`;

  // Run Python Code
  const handleRunPython = async () => {
    setIsRunningPython(true);
    setPythonConsoleOutput(isAr ? 'جاري تشغيل سكربت بايثون على الخادم...\n' : 'Executing Python script on server...\n');
    try {
      const res = await fetch('/api/python/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: generatedPythonCode })
      });
      const data = await res.json();
      setPythonConsoleOutput((prev) => prev + (data.stdout || '') + (data.stderr ? `\nERRORS:\n${data.stderr}` : ''));
      onCacheUpdated?.();
    } catch (e: any) {
      setPythonConsoleOutput((prev) => prev + `\nExecution Error: ${e.message}`);
    } finally {
      setIsRunningPython(false);
    }
  };

  const handleCopyCode = () => {
    navigator.clipboard.writeText(generatedPythonCode);
    setCopiedCode(true);
    setTimeout(() => setCopiedCode(false), 2000);
  };

  const toggleZoom = (z: number) => {
    if (selectedZooms.includes(z)) {
      if (selectedZooms.length > 1) {
        setSelectedZooms(selectedZooms.filter((x) => x !== z));
      }
    } else {
      setSelectedZooms([...selectedZooms, z].sort((a, b) => a - b));
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 bg-black/75 backdrop-blur-xs">
      <div className="relative w-full max-w-4xl max-h-[92vh] flex flex-col bg-slate-900 border border-slate-700 rounded-lg shadow-2xl overflow-hidden text-slate-200 animate-in fade-in zoom-in-95 duration-150">
        {/* Title Bar */}
        <div className="flex items-center justify-between px-4 py-2.5 bg-slate-950 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <Download className="w-5 h-5 text-emerald-400" />
            <h2 className="text-sm font-bold text-white">
              {isAr ? 'عمليات معالجة المنطقة المحددة (Selection Operations)' : 'Operations with Selected Area'}
            </h2>
            <span className="text-[11px] text-slate-400 bg-slate-800 px-2 py-0.5 rounded font-mono">
              SAS.Planet Core
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* BBox Coordinates Banner */}
        <div className="px-4 py-1.5 bg-slate-950/60 border-b border-slate-800 flex items-center justify-between text-[11px] font-mono text-slate-400 overflow-x-auto">
          <span>
            {isAr ? 'الإحداثيات الجغرافية:' : 'Coordinates:'}{' '}
            <strong className="text-amber-400">
              {bbox.min_lon.toFixed(4)}, {bbox.min_lat.toFixed(4)}
            </strong>{' '}
            {isAr ? 'إلى' : 'to'}{' '}
            <strong className="text-amber-400">
              {bbox.max_lon.toFixed(4)}, {bbox.max_lat.toFixed(4)}
            </strong>
          </span>
          <span className="text-slate-500">
            WGS84 | EPSG:3857
          </span>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-slate-800 bg-slate-950 px-2 text-xs">
          <button
            onClick={() => setActiveTab('download')}
            className={`flex items-center gap-2 px-4 py-2.5 font-semibold border-b-2 transition-all ${
              activeTab === 'download'
                ? 'border-emerald-500 text-emerald-400 bg-slate-900/60'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Download className="w-4 h-4" />
            <span>{isAr ? 'تحميل البلاطات (Download)' : 'Download Tiles'}</span>
          </button>

          <button
            onClick={() => setActiveTab('stitch')}
            className={`flex items-center gap-2 px-4 py-2.5 font-semibold border-b-2 transition-all ${
              activeTab === 'stitch'
                ? 'border-blue-500 text-blue-400 bg-slate-900/60'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <ImageIcon className="w-4 h-4" />
            <span>{isAr ? 'دمج وتصدير الصور (Stitch)' : 'Stitch Image'}</span>
          </button>

          <button
            onClick={() => setActiveTab('mbtiles')}
            className={`flex items-center gap-2 px-4 py-2.5 font-semibold border-b-2 transition-all ${
              activeTab === 'mbtiles'
                ? 'border-purple-500 text-purple-400 bg-slate-900/60'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Database className="w-4 h-4" />
            <span>{isAr ? 'تصدير MBTiles (SQLite)' : 'Export MBTiles'}</span>
          </button>

          <button
            onClick={() => setActiveTab('vector')}
            className={`flex items-center gap-2 px-4 py-2.5 font-semibold border-b-2 transition-all ${
              activeTab === 'vector' ? 'border-teal-500 text-teal-400 bg-slate-900/60' : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Upload className="w-4 h-4" />
            <span>{isAr ? 'استيراد تحديد / طبقة' : 'Import selection / layer'}</span>
          </button>

          <button
            onClick={() => setActiveTab('python')}
            className={`flex items-center gap-2 px-4 py-2.5 font-semibold border-b-2 transition-all ${
              activeTab === 'python'
                ? 'border-amber-500 text-amber-400 bg-slate-900/60'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Terminal className="w-4 h-4" />
            <span>{isAr ? 'شفرة بايثون (Python Script)' : 'Python Script'}</span>
          </button>
        </div>

        {/* Tab Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* TAB 1: DOWNLOAD */}
          {activeTab === 'download' && (
            <div className="space-y-4">
              {/* Map Source Selector */}
              <div className="bg-slate-950/70 p-3 rounded-lg border border-slate-800">
                <label className="block text-xs font-semibold text-slate-300 mb-2">
                  {isAr ? 'مصدر الخريطة المستهدف للتحميل:' : 'Target Map Source:'}
                </label>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {sources.map((src) => (
                    <button
                      key={src.id}
                      onClick={() => setSelectedSourceId(src.id)}
                      className={`text-start px-2.5 py-1.5 rounded text-xs border transition-all ${
                        selectedSourceId === src.id
                          ? 'bg-blue-600/30 border-blue-500 text-blue-200 font-semibold'
                          : 'bg-slate-900 border-slate-800 text-slate-400 hover:bg-slate-800'
                      }`}
                    >
                      <div className="truncate">{src.name}</div>
                      <div className="text-[10px] text-slate-500">{src.category}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Zooms Checklist */}
              <div className="bg-slate-950/70 p-3 rounded-lg border border-slate-800">
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-semibold text-slate-300">
                    {isAr ? 'مستويات التكبير المطلوبة (Zoom Levels):' : 'Zoom Levels to Download:'}
                  </label>
                  <div className="flex items-center gap-2 text-xs">
                    <button
                      onClick={() => setSelectedZooms([12, 13, 14, 15, 16, 17])}
                      className="text-blue-400 hover:underline"
                    >
                      {isAr ? 'تحديد قياسي (12-17)' : 'Default (12-17)'}
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-5 sm:grid-cols-10 gap-1.5">
                  {Array.from({ length: 20 }, (_, i) => i + 1).map((z) => {
                    const isChecked = selectedZooms.includes(z);
                    return (
                      <button
                        key={z}
                        onClick={() => toggleZoom(z)}
                        className={`py-1.5 rounded text-xs font-mono font-bold transition-all border ${
                          isChecked
                            ? 'bg-emerald-600 text-white border-emerald-500 shadow-xs'
                            : 'bg-slate-900 text-slate-400 border-slate-800 hover:bg-slate-800'
                        }`}
                      >
                        Z{z}
                      </button>
                    );
                  })}
                </div>

                {/* Calculation Summary Box */}
                <div className="mt-3 p-2.5 rounded bg-slate-900 border border-slate-800 flex items-center justify-between text-xs font-mono">
                  <div className="flex items-center gap-2">
                    <Layers className="w-4 h-4 text-emerald-400" />
                    <span>
                      {isAr ? 'إجمالي البلاطات المتوقعة:' : 'Calculated Total Tiles:'}{' '}
                      <strong className="text-emerald-300 text-sm">{totalTiles.toLocaleString()}</strong>
                    </span>
                  </div>
                  <div className="text-slate-400">
                    {isAr ? 'الحجم التقديري:' : 'Est. Size:'}{' '}
                    <strong className="text-amber-300">~{estimatedSizeMb.toFixed(1)} MB</strong>
                  </div>
                </div>
              </div>

              {/* Storage & Thread Configuration */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="bg-slate-950/70 p-3 rounded-lg border border-slate-800">
                  <label className="block text-xs font-semibold text-slate-300 mb-2">
                    {isAr ? 'صيغة التخزين / الكاش:' : 'Storage Engine:'}
                  </label>
                  <select
                    value={storageType}
                    onChange={(e) => setStorageType(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-200"
                  >
                    <option value="gm1">cache_gmt — Global Mapper (SAS.Planet)</option>
                    <option value="sas">SAS.Planet Directory (/z{15}/.../x.../y...)</option>
                    <option value="osm">OSM / TMS Directory (/{'{z}'}/{'{x}'}/{'{y}'}.png)</option>
                    <option value="mbtiles">MBTiles SQLite 1.3 Container (.mbtiles)</option>
                  </select>
                </div>

                <div className="bg-slate-950/70 p-3 rounded-lg border border-slate-800">
                  <div className="flex justify-between text-xs font-semibold text-slate-300 mb-1">
                    <span>{isAr ? 'عدد خيوط التنزيل المتزامنة:' : 'Concurrency (Threads):'}</span>
                    <span className="text-blue-400">{concurrency} Threads</span>
                  </div>
                  <input
                    type="range"
                    min="1"
                    max="12"
                    value={concurrency}
                    onChange={(e) => setConcurrency(Number(e.target.value))}
                    className="w-full accent-blue-500"
                  />
                  <div className="flex justify-between text-[10px] text-slate-500 mt-1">
                    <span>1 (Safe)</span>
                    <span>6 (Optimal)</span>
                    <span>12 (Fast)</span>
                  </div>
                </div>
              </div>

              {/* Progress & Status */}
              {activeJob&&storageType==='gm1'&&<div className="flex gap-2 my-2"><button className="desktop-button" onClick={()=>void controlJob(activeJob.status==='paused'?'resume':'pause')}>{activeJob.status==='paused'?(isAr?'استئناف':'Resume'):(isAr?'إيقاف مؤقت':'Pause')}</button><button className="desktop-button" onClick={()=>void controlJob('cancel')}>{isAr?'إلغاء التنزيل':'Cancel download'}</button><small>{isAr?'يمكن متابعة الأعمال من أدوات GIS ← الكاش والتنزيل.':'Manage saved jobs in GIS tools → Cache & jobs.'}</small></div>}
                {activeJob && (
                <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 space-y-2">
                  <div className="flex justify-between text-xs font-mono">
                    <span className="text-slate-300 font-semibold">
                      {isAr ? 'حالة التنزيل:' : 'Status:'}{' '}
                      <span className={activeJob.status === 'completed' ? 'text-emerald-400' : 'text-blue-400'}>
                        {activeJob.status.toUpperCase()}
                      </span>
                    </span>
                    <span className="text-amber-400">
                      {activeJob.progress_percent}% ({activeJob.downloaded + activeJob.cached} / {activeJob.total_tiles})
                    </span>
                  </div>

                  {/* Progress Bar */}
                  <div className="w-full bg-slate-800 rounded-full h-2.5 overflow-hidden">
                    <div
                      className="bg-emerald-500 h-2.5 rounded-full transition-all duration-300"
                      style={{ width: `${activeJob.progress_percent}%` }}
                    />
                  </div>

                  <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono">
                    <span>{isAr ? 'جديد:' : 'New:'} {activeJob.downloaded}</span>
                    <span>{isAr ? 'مخزن مسبقاً:' : 'Cached:'} {activeJob.cached}</span>
                    <span>{isAr ? 'فشل:' : 'Failed:'} {activeJob.failed}</span>
                    <span>{isAr ? 'السرعة:' : 'Speed:'} {activeJob.speed_kb_s} KB/s</span>
                  </div>
                </div>
              )}

              {downloadError && (
                <div className="p-2.5 rounded bg-rose-950/40 border border-rose-800 text-rose-300 text-xs flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
                  <span>{downloadError}</span>
                </div>
              )}

              {/* Download Action Button */}
              <button
                onClick={handleStartDownload}
                disabled={activeJob?.status === 'running'}
                className="w-full py-2.5 px-4 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-sm shadow-md transition-all flex items-center justify-center gap-2 disabled:bg-slate-800 disabled:text-slate-500"
              >
                <Download className="w-4 h-4" />
                <span>
                  {activeJob?.status === 'running'
                    ? (isAr ? 'جاري التنزيل في الخلفية...' : 'Downloading in Background...')
                    : (isAr ? 'بدء تنزيل البلاطات (Start Download)' : 'Start Batch Download')}
                </span>
              </button>
            </div>
          )}

          {/* TAB 2: STITCH / COMBINE */}
          {activeTab === 'stitch' && (
            <div className="space-y-4">
              <div className="bg-slate-950/70 p-3 rounded-lg border border-slate-800 space-y-3">
                <div className="text-xs text-slate-300">
                  {isAr
                    ? 'تقوم هذه الميزة بتجميع كل بلاطات المنطقة المحددة عند مستوى التكبير المختار في صورة واحدة فائقة الدقة مرفقة بملف الإسناد الجغرافي (WorldFile / GeoTIFF).'
                    : 'Stitches all map tiles in the selected bounding box at the chosen zoom level into a single high-resolution georeferenced raster with WorldFile.'}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">
                      {isAr ? 'مستوى التكبير المستهدف (Stitch Zoom):' : 'Stitch Zoom Level:'}
                    </label>
                    <select
                      value={stitchZoom}
                      onChange={(e) => setStitchZoom(Number(e.target.value))}
                      className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-200"
                    >
                      {Array.from({ length: 18 }, (_, i) => i + 3).map((z) => (
                        <option key={z} value={z}>
                          Zoom {z} ({stitchZoom === z ? `${stitchWidthPx}x${stitchHeightPx} px` : ''})
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">
                      {isAr ? 'صيغة الإخراج (Output Format):' : 'Output Format:'}
                    </label>
                    <select
                      value={stitchFormat}
                      onChange={(e) => setStitchFormat(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-200"
                    >
                      <option value="bmp">Windows 24-bit BMP + WorldFile (.bpw + .prj)</option>
                      <option value="geotiff">GeoTIFF (embedded CRS)</option>
                      <option value="jpg">JPEG + WorldFile (.jgw)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">
                      {isAr ? 'نظام إسناد الناتج:' : 'Output coordinate system:'}
                    </label>
                    <select value={stitchCrs} onChange={(e) => setStitchCrs(e.target.value)} className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-200">
                      <option value="EPSG:3857">Web Mercator — EPSG:3857</option>
                      <option value="EPSG:4326">WGS 84 geographic — EPSG:4326</option>
                      <option value="EPSG:30729">Nord Sahara 1959 / UTM 29N — EPSG:30729</option>
                      <option value="EPSG:30730">Nord Sahara 1959 / UTM 30N — EPSG:30730</option>
                      <option value="EPSG:30731">Nord Sahara 1959 / UTM 31N — EPSG:30731</option>
                      <option value="EPSG:30732">Nord Sahara 1959 / UTM 32N — EPSG:30732</option>
                    </select>
                  </div>
                </div>
                <p className="text-[11px] text-slate-400">{isAr ? 'عند اختيار Nord Sahara يعاد إسقاط البكسلات فعلياً، ويضاف ملف .prj مع WorldFile. اختر منطقة UTM المطابقة للورقة.' : 'Nord Sahara reprojects pixels before the WorldFile is written and adds a .prj sidecar. Choose the matching UTM zone.'}</p>

                {/* Dimension Preview */}
                <div className="p-3 bg-slate-900 rounded border border-slate-800 text-xs font-mono space-y-1">
                  <div className="flex justify-between text-slate-300">
                    <span>{isAr ? 'أبعاد الصورة الناتجة:' : 'Composite Dimensions:'}</span>
                    <strong className="text-cyan-300">{stitchWidthPx} x {stitchHeightPx} Pixels</strong>
                  </div>
                  <div className="flex justify-between text-slate-400 text-[11px]">
                    <span>{isAr ? 'عدد البلاطات:' : 'Tiles Count:'}</span>
                    <span>{stitchBreakdown.xCount} x {stitchBreakdown.yCount} = {stitchBreakdown.tiles} tiles</span>
                  </div>
                </div>
              </div>

              {/* Stitch Action Button */}
              <button
                onClick={handleStartStitch}
                disabled={isStitching}
                className="w-full py-2.5 px-4 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-bold text-sm shadow-md transition-all flex items-center justify-center gap-2 disabled:bg-slate-800 disabled:text-slate-500"
              >
                {isStitching ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>{isAr ? 'جاري دمج البلاطات عبر بايثون...' : 'Stitching Tiles with Python...'}</span>
                  </>
                ) : (
                  <>
                    <ImageIcon className="w-4 h-4" />
                    <span>{isAr ? 'تنفيذ الدمج واستخراج الصورة الجغرافية (Stitch)' : 'Generate Stitched Raster'}</span>
                  </>
                )}
              </button>

              {stitchError && (
                <div className="p-2.5 rounded bg-rose-950/40 border border-rose-800 text-rose-300 text-xs flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
                  <span>{stitchError}</span>
                </div>
              )}

              {/* Success Result & Download Links */}
              {stitchResult && (
                <div className="p-3.5 bg-emerald-950/40 border border-emerald-800 rounded-lg space-y-3">
                  <div className="flex items-center gap-2 text-emerald-300 text-sm font-bold">
                    <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                    <span>{isAr ? 'تم دمج الصورة الجغرافية بنجاح!' : 'Map Raster Stitched Successfully!'}</span>
                  </div>

                  <div className="text-xs text-slate-300 font-mono space-y-1">
                    <div>{isAr ? 'الأبعاد:' : 'Size:'} {stitchResult.width} x {stitchResult.height} px ({stitchResult.total_tiles} tiles)</div>
                    <div>{isAr ? 'نظام الإحداثيات:' : 'CRS:'} {stitchResult.crs_name || stitchResult.crs || stitchCrs}</div>
                  </div>

                  <div className="flex gap-2">
                    <a
                      href={stitchResult.download_url}
                      download
                      className="flex-1 py-2 px-3 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold text-center transition-colors flex items-center justify-center gap-1.5"
                    >
                      <Download className="w-3.5 h-3.5" />
                      <span>{isAr ? `تحميل الصورة (.${(stitchResult.format || stitchFormat || 'bmp').toUpperCase()})` : `Download Image (.${(stitchResult.format || stitchFormat || 'bmp').toUpperCase()})`}</span>
                    </a>

                    <a
                      href={stitchResult.world_file_url}
                      download
                      className="py-2 px-3 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold text-center transition-colors flex items-center justify-center gap-1.5"
                    >
                      <FileCheck className="w-3.5 h-3.5" />
                      <span>{isAr ? 'تحميل ملف الإسناد (WorldFile)' : 'Download WorldFile'}</span>
                    </a>
                    {stitchResult.projection_file_url && <a href={stitchResult.projection_file_url} download className="py-2 px-3 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold text-center transition-colors flex items-center justify-center gap-1.5"><MapPin className="w-3.5 h-3.5"/><span>.prj</span></a>}
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === 'vector' && (
            <div className="space-y-4">
              <input ref={vectorInput} className="hidden" type="file" accept=".kml,.kmz,.gpx,.geojson,.json,.zip,.sml,.db3" onChange={handleVectorFile} />
              <div className="p-4 rounded-lg border border-slate-800 bg-slate-950/70 space-y-3 text-xs">
                <div className="flex items-start gap-2 text-slate-300"><Upload className="w-5 h-5 text-teal-400 shrink-0"/><p>{isAr ? 'استورد حدوداً أو مسارات صادرة من SAS.Planet لتظهر كطبقة علامات، ثم اعتمد أي مضلع كتحديد للتحميل أو التحليل أو الدمج.' : 'Import boundaries or routes exported from SAS.Planet. They appear as map marks; use a polygon as the current selection for download, analysis, or stitch.'}</p></div>
                <button onClick={() => vectorInput.current?.click()} disabled={vectorBusy} className="w-full py-2.5 px-4 rounded-lg bg-teal-600 hover:bg-teal-500 text-white font-bold flex items-center justify-center gap-2 disabled:bg-slate-800"><Upload className="w-4 h-4"/>{vectorBusy ? (isAr ? 'جاري قراءة الملف…' : 'Reading file…') : (isAr ? 'اختيار ملف KML / KMZ / GPX / GeoJSON / Shapefile ZIP / SML / DB3' : 'Choose KML / KMZ / GPX / GeoJSON / Shapefile ZIP / SML / DB3')}</button>
                <p className="text-[11px] text-slate-400">{isAr ? 'ملف Shapefile يُرفع كملف ZIP واحد يحتوي .shp و .shx و .dbf و .prj. لا يُقبل ملف .shp منفرداً لأن معلوماته ومرجعه ناقصان.' : 'Upload Shapefile as one ZIP containing .shp, .shx, .dbf and .prj. A lone .shp is incomplete and is not accepted.'}</p>
                <p className="text-[11px] text-slate-400">{isAr ? 'شبكة تقسيم الخرائط الجزائرية (قاعدة علامات SAS.Planet ‎.sml‎ أو ‎.db3‎): تُستورد المضلعات مع الحقول id و nom و type و n_50000 و coup و num فقط.' : 'Algeria map-sheet grid (SAS.Planet .sml or .db3 marks database): polygons import with only the id, nom, type, n_50000, coup and num fields.'}</p>
              </div>
              {vectorError && <div className="p-2.5 rounded bg-rose-950/40 border border-rose-800 text-rose-300 text-xs flex items-center gap-2"><AlertCircle className="w-4 h-4 shrink-0"/><span>{vectorError}</span></div>}
              {vectorResult && <div className="p-4 rounded-lg border border-teal-800 bg-teal-950/25 space-y-3">
                <p className="text-sm font-bold text-teal-200">{isAr ? 'تم الاستيراد:' : 'Imported:'} {vectorResult.marks?.length || 0} {isAr ? 'عنصرًا' : 'features'} · {String(vectorResult.format || '').toUpperCase()}</p>
                {!!vectorResult.marks?.length && <><select value={selectedVectorMark} onChange={e=>setSelectedVectorMark(Number(e.target.value))} className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-2 text-xs text-slate-200">{vectorResult.marks.map((mark:any,index:number)=><option key={mark.id || index} value={index}>{mark.name || `Feature ${index+1}`} — {mark.type}</option>)}</select><button onClick={applyVectorSelection} className="w-full py-2 px-3 rounded bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold flex items-center justify-center gap-2"><MapPin className="w-4 h-4"/>{isAr ? 'اعتماد العنصر كتحديد والانتقال إليه' : 'Use feature as selection and zoom to it'}</button></>}
              </div>}
            </div>
          )}

          {/* TAB 3: MBTILES */}
          {activeTab === 'mbtiles' && (
            <div className="space-y-4">
              <div className="bg-slate-950/70 p-3.5 rounded-lg border border-slate-800 space-y-3">
                <div className="flex items-center gap-2 text-purple-300 font-bold text-sm">
                  <Database className="w-4 h-4" />
                  <span>{isAr ? 'تصدير كاش MBTiles (SQLite 1.3)' : 'Export MBTiles SQLite Container'}</span>
                </div>
                <p className="text-xs text-slate-400">
                  {isAr
                    ? 'صيغة MBTiles هي الحاوية القياسية المفتوحة لتخزين بلاطات الخرائط في ملف SQLite واحد. متوافقة تماماً مع تطبيقات الملاحة مثل OruxMaps وOsmAnd وQGIS وبرامج الـ GIS المكتبية.'
                    : 'MBTiles is an open SQLite-based single-file tile format supported by QGIS, OsmAnd, OruxMaps, Mapbox, and desktop GIS suites.'}
                </p>

                <div className="p-3 bg-slate-900 rounded border border-slate-800 text-xs font-mono space-y-1">
                  <div>{isAr ? 'المصدر:' : 'Source:'} {currentSource.name}</div>
                  <div>{isAr ? 'المستويات المختارة:' : 'Selected Zooms:'} {selectedZooms.join(', ')}</div>
                  <div>{isAr ? 'عدد البلاطات:' : 'Total Tiles:'} {totalTiles.toLocaleString()}</div>
                </div>

                <button
                  onClick={() => {
                    setStorageType('mbtiles');
                    setActiveTab('download');
                  }}
                  className="w-full py-2.5 px-4 rounded-lg bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs transition-colors flex items-center justify-center gap-2"
                >
                  <Download className="w-4 h-4" />
                  <span>{isAr ? 'تنزيل وحفظ مباشرة في ملف MBTiles' : 'Download Directly to MBTiles'}</span>
                </button>
              </div>
            </div>
          )}

          {/* TAB 4: GENERATED PYTHON CODE */}
          {activeTab === 'python' && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-amber-400 flex items-center gap-1.5">
                  <Terminal className="w-4 h-4" />
                  {isAr ? 'شفرة بايثون المولدة لعمليات SAS.Planet:' : 'Generated SAS.Planet Python Code:'}
                </span>

                <div className="flex items-center gap-2">
                  <button
                    onClick={handleCopyCode}
                    className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition-colors"
                  >
                    <Copy className="w-3.5 h-3.5" />
                    <span>{copiedCode ? (isAr ? 'تم النسخ!' : 'Copied!') : (isAr ? 'نسخ الشفرة' : 'Copy')}</span>
                  </button>

                  <button
                    onClick={handleRunPython}
                    disabled={isRunningPython}
                    className="flex items-center gap-1.5 px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs shadow-sm transition-all disabled:opacity-50"
                  >
                    <Play className="w-3.5 h-3.5 fill-current" />
                    <span>{isRunningPython ? (isAr ? 'جاري التشغيل...' : 'Running...') : (isAr ? 'تشغيل بايثون فوري' : 'Run Python')}</span>
                  </button>
                </div>
              </div>

              {/* Code Box */}
              <div className="relative">
                <pre className="p-3 bg-slate-950 border border-slate-800 rounded-lg text-emerald-400 text-xs font-mono max-h-60 overflow-y-auto leading-relaxed select-text">
                  {generatedPythonCode}
                </pre>
              </div>

              {/* Terminal Output */}
              {pythonConsoleOutput && (
                <div className="space-y-1">
                  <div className="text-[11px] font-mono text-slate-400">
                    {isAr ? 'مخرجات الطرفية (Python Terminal Output):' : 'Python Terminal Output:'}
                  </div>
                  <pre className="p-3 bg-black/90 border border-slate-800 rounded-lg text-slate-200 text-xs font-mono max-h-48 overflow-y-auto leading-relaxed whitespace-pre-wrap select-text">
                    {pythonConsoleOutput}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
