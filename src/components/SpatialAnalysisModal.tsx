import React, { useState } from 'react';
import {
  X,
  PieChart,
  CircleDot,
  TrendingUp,
  Eye,
  ShieldAlert,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Compass,
  ArrowRight,
  Maximize2
} from 'lucide-react';
import { MarkItem } from '../types';
import { DraggableWindow } from './DraggableWindow';

interface SpatialAnalysisModalProps {
  isOpen: boolean;
  onClose: () => void;
  centerCoords: { lat: number; lon: number };
  marks: MarkItem[];
  onAddBufferToMap: (polygonCoords: [number, number][], name: string) => void;
  lang: 'ar' | 'en';
}

export const SpatialAnalysisModal: React.FC<SpatialAnalysisModalProps> = ({
  isOpen,
  onClose,
  centerCoords,
  marks,
  onAddBufferToMap,
  lang
}) => {
  const isAr = lang === 'ar';
  const [activeTab, setActiveTab] = useState<'buffer' | 'slope' | 'viewshed' | 'convexhull'>('buffer');

  // Buffer Tab
  const [bufferLat, setBufferLat] = useState<string>(String(centerCoords.lat.toFixed(5)));
  const [bufferLon, setBufferLon] = useState<string>(String(centerCoords.lon.toFixed(5)));
  const [bufferRadius, setBufferRadius] = useState<number>(1000);
  const [bufferLoading, setBufferLoading] = useState<boolean>(false);
  const [bufferResult, setBufferResult] = useState<any>(null);

  // Slope Tab
  const [slopeLat, setSlopeLat] = useState<string>(String(centerCoords.lat.toFixed(5)));
  const [slopeLon, setSlopeLon] = useState<string>(String(centerCoords.lon.toFixed(5)));
  const [slopeLoading, setSlopeLoading] = useState<boolean>(false);
  const [slopeResult, setSlopeResult] = useState<any>(null);

  // Viewshed / LOS Tab
  const [obsLat, setObsLat] = useState<string>(String(centerCoords.lat.toFixed(5)));
  const [obsLon, setObsLon] = useState<string>(String(centerCoords.lon.toFixed(5)));
  const [obsHeight, setObsHeight] = useState<number>(2.0);
  const [tgtLat, setTgtLat] = useState<string>(String((centerCoords.lat + 0.04).toFixed(5)));
  const [tgtLon, setTgtLon] = useState<string>(String((centerCoords.lon + 0.04).toFixed(5)));
  const [tgtHeight, setTgtHeight] = useState<number>(2.0);
  const [losLoading, setLosLoading] = useState<boolean>(false);
  const [losResult, setLosResult] = useState<any>(null);

  if (!isOpen) return null;

  // 1. Run Buffer Analysis
  const handleRunBuffer = async () => {
    setBufferLoading(true);
    try {
      const lat = parseFloat(bufferLat);
      const lon = parseFloat(bufferLon);
      const res = await fetch('/api/python/analysis/buffer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lat, lon, radius: bufferRadius })
      });
      const data = await res.json();
      if (data.success) {
        setBufferResult(data.buffer);
        const ring = data.buffer.geometry.coordinates[0];
        const pts = ring.map((c: [number, number]) => [c[1], c[0]] as [number, number]);
        onAddBufferToMap(pts, `Buffer ${bufferRadius}m`);
      }
    } catch (e: any) {
      alert(`Buffer error: ${e.message}`);
    } finally {
      setBufferLoading(false);
    }
  };

  // 2. Run Slope Analysis
  const handleRunSlope = async () => {
    setSlopeLoading(true);
    try {
      const lat = parseFloat(slopeLat);
      const lon = parseFloat(slopeLon);
      const res = await fetch('/api/python/analysis/slope', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lat, lon })
      });
      const data = await res.json();
      if (data.success) {
        setSlopeResult(data.data);
      }
    } catch (e: any) {
      alert(`Slope error: ${e.message}`);
    } finally {
      setSlopeLoading(false);
    }
  };

  // 3. Run Line of Sight (LOS)
  const handleRunLos = async () => {
    setLosLoading(true);
    try {
      const oLat = parseFloat(obsLat);
      const oLon = parseFloat(obsLon);
      const tLat = parseFloat(tgtLat);
      const tLon = parseFloat(tgtLon);
      const res = await fetch('/api/python/analysis/viewshed', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          observer: [oLat, oLon],
          target: [tLat, tLon],
          obs_height: obsHeight,
          target_height: tgtHeight
        })
      });
      const data = await res.json();
      if (data.success) {
        setLosResult(data.data);
      }
    } catch (e: any) {
      alert(`LOS error: ${e.message}`);
    } finally {
      setLosLoading(false);
    }
  };

  return (
    <DraggableWindow>
      <div className="relative w-full max-w-4xl max-h-[90vh] flex flex-col bg-slate-900 border border-slate-700 rounded-lg shadow-2xl overflow-hidden text-slate-200">
        {/* Title Bar */}
        <div className="flex items-center justify-between px-4 py-2.5 bg-slate-950 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <PieChart className="w-5 h-5 text-purple-400" />
            <h2 className="text-sm font-bold text-white">
              {isAr ? 'نماذج تحليل البيانات المكانية والجيوديسية (Spatial Analysis Models)' : 'Spatial Analysis & Geodesic Models'}
            </h2>
            <span className="text-[10px] bg-purple-500/20 text-purple-300 border border-purple-500/30 px-2 py-0.5 rounded font-mono">
              GIS Analytics
            </span>
          </div>

          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tab Selector */}
        <div className="flex border-b border-slate-800 bg-slate-950 px-2 text-xs">
          <button
            onClick={() => setActiveTab('buffer')}
            className={`flex items-center gap-2 px-4 py-2.5 font-semibold border-b-2 transition-all ${
              activeTab === 'buffer'
                ? 'border-purple-500 text-purple-400 bg-slate-900/60'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <CircleDot className="w-4 h-4" />
            <span>{isAr ? 'نطاقات الحرم (Buffer Analysis)' : 'Geodesic Buffer'}</span>
          </button>

          <button
            onClick={() => setActiveTab('slope')}
            className={`flex items-center gap-2 px-4 py-2.5 font-semibold border-b-2 transition-all ${
              activeTab === 'slope'
                ? 'border-amber-500 text-amber-400 bg-slate-900/60'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <TrendingUp className="w-4 h-4" />
            <span>{isAr ? 'درجات الانحدار والتضاريس (Slope)' : 'Slope & Aspect'}</span>
          </button>

          <button
            onClick={() => setActiveTab('viewshed')}
            className={`flex items-center gap-2 px-4 py-2.5 font-semibold border-b-2 transition-all ${
              activeTab === 'viewshed'
                ? 'border-cyan-500 text-cyan-400 bg-slate-900/60'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Eye className="w-4 h-4" />
            <span>{isAr ? 'خط الرؤية والعوائق (Line of Sight)' : 'Line of Sight (LOS)'}</span>
          </button>
        </div>

        {/* Content Body */}
        <div className="p-4 overflow-y-auto space-y-4 text-xs">
          {/* TAB 1: BUFFER */}
          {activeTab === 'buffer' && (
            <div className="space-y-4">
              <div className="bg-slate-950/80 p-3.5 rounded-lg border border-slate-800 space-y-3">
                <div className="font-semibold text-slate-200 flex items-center gap-2">
                  <CircleDot className="w-4 h-4 text-purple-400" />
                  <span>{isAr ? 'توليد نطاق حرم جيوديسي (Geodesic Buffer Zone):' : 'Geodesic Buffer Configuration:'}</span>
                </div>
                <p className="text-slate-400 text-[11px] leading-relaxed">
                  {isAr
                    ? 'يحسب هذا النموذج مضلع الحرم الجيوديسي الدقيق على سطح الأرض الكروي حول النقطة المحددة، مع مراعاة تشوه المسافات في الإسقاط، ويقوم بإسقاطه مباشرة على الخريطة.'
                    : 'Computes a true geodesic circular buffer polygon around the coordinate point and projects it directly onto the map.'}
                </p>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="block text-slate-300 font-semibold mb-1">{isAr ? 'خط العرض (Lat):' : 'Latitude:'}</label>
                    <input
                      type="text"
                      value={bufferLat}
                      onChange={(e) => setBufferLat(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 font-mono text-slate-200"
                    />
                  </div>

                  <div>
                    <label className="block text-slate-300 font-semibold mb-1">{isAr ? 'خط الطول (Lon):' : 'Longitude:'}</label>
                    <input
                      type="text"
                      value={bufferLon}
                      onChange={(e) => setBufferLon(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 font-mono text-slate-200"
                    />
                  </div>

                  <div>
                    <label className="block text-slate-300 font-semibold mb-1">{isAr ? 'نصف القطر (Radius):' : 'Buffer Radius:'}</label>
                    <select
                      value={bufferRadius}
                      onChange={(e) => setBufferRadius(Number(e.target.value))}
                      className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-slate-200 font-mono"
                    >
                      <option value="250">250 meters</option>
                      <option value="500">500 meters</option>
                      <option value="1000">1,000 meters (1 km)</option>
                      <option value="2500">2,500 meters (2.5 km)</option>
                      <option value="5000">5,000 meters (5 km)</option>
                      <option value="10000">10,000 meters (10 km)</option>
                    </select>
                  </div>
                </div>

                <button
                  onClick={handleRunBuffer}
                  disabled={bufferLoading}
                  className="w-full py-2.5 px-4 rounded-lg bg-purple-600 hover:bg-purple-500 text-white font-bold transition-all shadow-md flex items-center justify-center gap-2 disabled:bg-slate-800 disabled:text-slate-500"
                >
                  {bufferLoading ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>{isAr ? 'جاري حساب النطاق الجيوديسي عبر بايثون...' : 'Calculating Buffer in Python...'}</span>
                    </>
                  ) : (
                    <>
                      <CircleDot className="w-4 h-4" />
                      <span>{isAr ? 'حساب نطاق الحرم وإسقاطه على الخريطة' : 'Calculate & Display Buffer Polygon'}</span>
                    </>
                  )}
                </button>
              </div>

              {bufferResult && (
                <div className="p-3 bg-purple-950/40 border border-purple-800 text-purple-200 rounded-lg text-xs space-y-1">
                  <div className="flex items-center gap-2 font-bold text-sm text-purple-300">
                    <CheckCircle2 className="w-4 h-4 text-purple-400" />
                    <span>{isAr ? 'تم حساب نطاق الحرم الجيوديسي بنجاح!' : 'Buffer Calculated Successfully!'}</span>
                  </div>
                  <div>{isAr ? 'نصف القطر:' : 'Radius:'} <strong>{bufferRadius.toLocaleString()} m</strong></div>
                  <div>{isAr ? 'المساحة المغطاة:' : 'Covered Area:'} <strong>{(Math.PI * (bufferRadius / 1000)**2).toFixed(2)} km²</strong> ({Math.round(Math.PI * (bufferRadius / 100)**2).toLocaleString()} hectares)</div>
                </div>
              )}
            </div>
          )}

          {/* TAB 2: SLOPE & ASPECT */}
          {activeTab === 'slope' && (
            <div className="space-y-4">
              <div className="bg-slate-950/80 p-3.5 rounded-lg border border-slate-800 space-y-3">
                <div className="font-semibold text-slate-200 flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-amber-400" />
                  <span>{isAr ? 'تحليل درجات الانحدار والتضاريس (Horn Algorithm):' : 'Slope & Aspect Analysis:'}</span>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-slate-300 font-semibold mb-1">{isAr ? 'خط العرض (Lat):' : 'Latitude:'}</label>
                    <input
                      type="text"
                      value={slopeLat}
                      onChange={(e) => setSlopeLat(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 font-mono text-slate-200"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-300 font-semibold mb-1">{isAr ? 'خط الطول (Lon):' : 'Longitude:'}</label>
                    <input
                      type="text"
                      value={slopeLon}
                      onChange={(e) => setSlopeLon(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 font-mono text-slate-200"
                    />
                  </div>
                </div>

                <button
                  onClick={handleRunSlope}
                  disabled={slopeLoading}
                  className="w-full py-2.5 px-4 rounded-lg bg-amber-600 hover:bg-amber-500 text-white font-bold transition-all shadow-md flex items-center justify-center gap-2 disabled:bg-slate-800 disabled:text-slate-500"
                >
                  {slopeLoading ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>{isAr ? 'جاري تحليل درجات الانحدار...' : 'Calculating Slope...'}</span>
                    </>
                  ) : (
                    <>
                      <TrendingUp className="w-4 h-4" />
                      <span>{isAr ? 'بدء تحليل الانحدار والاتجاه' : 'Analyze Slope & Aspect'}</span>
                    </>
                  )}
                </button>
              </div>

              {slopeResult && (
                <div className="p-4 bg-slate-950 rounded-lg border border-slate-800 space-y-3">
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center font-mono">
                    <div className="p-2 rounded bg-slate-900 border border-slate-800">
                      <span className="text-[10px] text-slate-400 block">{isAr ? 'الارتفاع' : 'Elevation'}</span>
                      <strong className="text-lg text-emerald-400">{slopeResult.elevation_m}m</strong>
                    </div>

                    <div className="p-2 rounded bg-slate-900 border border-slate-800">
                      <span className="text-[10px] text-slate-400 block">{isAr ? 'درجة الانحدار' : 'Slope Deg'}</span>
                      <strong className="text-lg text-amber-400">{slopeResult.slope_degrees}°</strong>
                    </div>

                    <div className="p-2 rounded bg-slate-900 border border-slate-800">
                      <span className="text-[10px] text-slate-400 block">{isAr ? 'نسبة الانحدار' : 'Slope %'}</span>
                      <strong className="text-lg text-cyan-400">{slopeResult.slope_percent}%</strong>
                    </div>

                    <div className="p-2 rounded bg-slate-900 border border-slate-800">
                      <span className="text-[10px] text-slate-400 block">{isAr ? 'اتجاه السفح' : 'Aspect'}</span>
                      <strong className="text-lg text-purple-400">{slopeResult.aspect_degrees}°</strong>
                    </div>
                  </div>

                  <div className="p-2.5 rounded bg-slate-900 border border-slate-800 flex items-center justify-between text-xs">
                    <span className="text-slate-400">{isAr ? 'تصنيف الخطورة والتضاريس:' : 'Terrain Hazard Category:'}</span>
                    <span
                      className="px-2.5 py-0.5 rounded font-bold"
                      style={{ color: slopeResult.hazard_color }}
                    >
                      {slopeResult.hazard_category}
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 3: LINE OF SIGHT (LOS) */}
          {activeTab === 'viewshed' && (
            <div className="space-y-4">
              <div className="bg-slate-950/80 p-3.5 rounded-lg border border-slate-800 space-y-3">
                <div className="font-semibold text-slate-200 flex items-center gap-2">
                  <Eye className="w-4 h-4 text-cyan-400" />
                  <span>{isAr ? 'تحليل خط الرؤية والعوائق التضاريسية (Line of Sight):' : 'Line of Sight Obstruction Model:'}</span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {/* Observer */}
                  <div className="space-y-2 p-3 bg-slate-900 rounded border border-slate-800">
                    <strong className="text-cyan-400 text-xs block">{isAr ? 'نقطة الملاحظ / المراقب (Observer):' : 'Observer Point:'}</strong>
                    <div className="grid grid-cols-2 gap-2">
                      <input
                        type="text"
                        value={obsLat}
                        onChange={(e) => setObsLat(e.target.value)}
                        placeholder="Lat"
                        className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs font-mono"
                      />
                      <input
                        type="text"
                        value={obsLon}
                        onChange={(e) => setObsLon(e.target.value)}
                        placeholder="Lon"
                        className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs font-mono"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] text-slate-400">{isAr ? 'ارتفاع المراقب (متر):' : 'Eye Height (m):'}</label>
                      <input
                        type="number"
                        value={obsHeight}
                        onChange={(e) => setObsHeight(Number(e.target.value))}
                        className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs font-mono"
                      />
                    </div>
                  </div>

                  {/* Target */}
                  <div className="space-y-2 p-3 bg-slate-900 rounded border border-slate-800">
                    <strong className="text-amber-400 text-xs block">{isAr ? 'نقطة الهدف (Target):' : 'Target Point:'}</strong>
                    <div className="grid grid-cols-2 gap-2">
                      <input
                        type="text"
                        value={tgtLat}
                        onChange={(e) => setTgtLat(e.target.value)}
                        placeholder="Lat"
                        className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs font-mono"
                      />
                      <input
                        type="text"
                        value={tgtLon}
                        onChange={(e) => setTgtLon(e.target.value)}
                        placeholder="Lon"
                        className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs font-mono"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] text-slate-400">{isAr ? 'ارتفاع الهدف (متر):' : 'Target Height (m):'}</label>
                      <input
                        type="number"
                        value={tgtHeight}
                        onChange={(e) => setTgtHeight(Number(e.target.value))}
                        className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs font-mono"
                      />
                    </div>
                  </div>
                </div>

                <button
                  onClick={handleRunLos}
                  disabled={losLoading}
                  className="w-full py-2.5 px-4 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-bold transition-all shadow-md flex items-center justify-center gap-2 disabled:bg-slate-800 disabled:text-slate-500"
                >
                  {losLoading ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>{isAr ? 'جاري تحليل مسار شعاع الرؤية...' : 'Analyzing Line of Sight...'}</span>
                    </>
                  ) : (
                    <>
                      <Eye className="w-4 h-4" />
                      <span>{isAr ? 'بدء فحص الرؤية المباشرة (Line of Sight)' : 'Check Line of Sight'}</span>
                    </>
                  )}
                </button>
              </div>

              {losResult && (
                <div className={`p-4 rounded-lg border space-y-2 ${
                  losResult.visible
                    ? 'bg-emerald-950/40 border-emerald-800 text-emerald-200'
                    : 'bg-rose-950/40 border-rose-800 text-rose-200'
                }`}>
                  <div className="flex items-center gap-2 font-bold text-sm">
                    {losResult.visible ? (
                      <>
                        <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                        <span>{isAr ? 'خط الرؤية مفتوح ومباشر دون عوائق تضاريسية!' : 'Clear Line of Sight (Visible)!'}</span>
                      </>
                    ) : (
                      <>
                        <ShieldAlert className="w-5 h-5 text-rose-400" />
                        <span>{isAr ? 'خط الرؤية محجوب بتضاريس مرتفعة!' : 'Line of Sight is Blocked by Terrain!'}</span>
                      </>
                    )}
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 font-mono text-xs pt-2">
                    <div>{isAr ? 'المسافة الإجمالية:' : 'Total Distance:'} <strong>{losResult.total_distance_km} km</strong></div>
                    <div>{isAr ? 'ارتفاع المراقب:' : 'Observer Z:'} <strong>{losResult.observer_elevation_m}m</strong></div>
                    <div>{isAr ? 'ارتفاع الهدف:' : 'Target Z:'} <strong>{losResult.target_elevation_m}m</strong></div>
                  </div>

                  {!losResult.visible && losResult.obstruction && (
                    <div className="p-2.5 bg-black/40 rounded border border-rose-900 text-[11px] font-mono text-rose-300">
                      {isAr ? 'نقطة العائق الأكبر:' : 'Obstruction Point:'} عند مسافة {losResult.obstruction.distance_m}m بارتفاع {losResult.obstruction.elevation_m}m (يحجب الشعاع بمقدار {losResult.obstruction.obstruction_height_m}m).
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </DraggableWindow>
  );
};
