import React, { useState, useEffect } from 'react';
import { X, Activity, Mountain, TrendingUp, TrendingDown, RefreshCw } from 'lucide-react';
import { ElevationSample } from '../types';
import { DraggableWindow } from './DraggableWindow';

interface ElevationProfileModalProps {
  isOpen: boolean;
  onClose: () => void;
  pathCoords: [number, number][]; // [lat, lon]
  lang: 'ar' | 'en';
  isOfflineMode?: boolean;
}

const DEMO_COORDS: [number, number][] = [
  [30.0444, 31.2357],
  [30.0131, 31.2089],
  [29.9792, 31.1342]
];

export const ElevationProfileModal: React.FC<ElevationProfileModalProps> = ({
  isOpen,
  onClose,
  pathCoords,
  isOfflineMode = false,
  lang
}) => {
  const isAr = lang === 'ar';
  const [samples, setSamples] = useState<ElevationSample[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState<boolean>(true);
  const [hoveredSample, setHoveredSample] = useState<ElevationSample | null>(null);

  const activeCoords = pathCoords && pathCoords.length >= 2 ? pathCoords : DEMO_COORDS;

  useEffect(() => {
    if (!isOpen) return;
    let isMounted = true;
    setLoading(true);
    setError(''); setSamples([]); setHoveredSample(null);

    fetch('/api/python/elevation', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ coords: activeCoords, samples: 45, offline: isOfflineMode })
    })
      .then((r) => r.json())
      .then((data) => {
        if (!data.success) throw new Error(data.error || 'Cannot load terrain');
        if (isMounted && data.success) {
          setSamples(data.profile);
        }
      })
      .catch((e) => { if (isMounted) setError(e.message); })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [isOpen, activeCoords, isOfflineMode]);

  if (!isOpen) return null;

  const minElev = samples.length > 0 ? Math.min(...samples.map((s) => s.elevation_m)) : 0;
  const maxElev = samples.length > 0 ? Math.max(...samples.map((s) => s.elevation_m)) : 100;
  const totalDistKm = samples.length > 0 ? samples[samples.length - 1].distance_km : 0;

  // Calculate ascent / descent
  let totalAscent = 0;
  let totalDescent = 0;
  for (let i = 0; i < samples.length - 1; i++) {
    const diff = samples[i + 1].elevation_m - samples[i].elevation_m;
    if (diff > 0) totalAscent += diff;
    else totalDescent += Math.abs(diff);
  }

  // SVG Chart Dimensions
  const svgWidth = 650;
  const svgHeight = 220;
  const padding = 35;
  const chartW = svgWidth - padding * 2;
  const chartH = svgHeight - padding * 2;

  const getSvgX = (s: ElevationSample) => {
    if (totalDistKm === 0) return padding;
    return padding + (s.distance_km / totalDistKm) * chartW;
  };

  const getSvgY = (s: ElevationSample) => {
    const range = Math.max(1, maxElev - minElev);
    return padding + chartH - ((s.elevation_m - minElev) / range) * chartH;
  };

  const pointsStr = samples.map((s) => `${getSvgX(s)},${getSvgY(s)}`).join(' ');
  const areaPolygonStr = samples.length > 0
    ? `${padding},${padding + chartH} ${pointsStr} ${padding + chartW},${padding + chartH}`
    : '';

  return (
    <DraggableWindow>
      <div className="relative w-full max-w-3xl flex flex-col bg-slate-900 border border-slate-700 rounded-lg shadow-2xl overflow-hidden text-slate-200">
        {/* Title Bar */}
        <div className="flex items-center justify-between px-4 py-2.5 bg-slate-950 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-emerald-400" />
            <h2 className="text-sm font-bold text-white">
              {isAr ? 'مخطط التضاريس والارتفاعات (Elevation Profile)' : 'Elevation & Terrain Profile'}
            </h2>
            <span className="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded font-mono">
              SAS.Planet Terrain
            </span>
          </div>

          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Stats Row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 p-3 bg-slate-950/70 border-b border-slate-800 text-xs">
          <div className="p-2 rounded bg-slate-900 border border-slate-800">
            <span className="text-slate-400 text-[11px] block">{isAr ? 'المسافة الكلية:' : 'Total Distance:'}</span>
            <strong className="text-cyan-300 text-sm font-mono">{totalDistKm} km</strong>
          </div>
          <div className="p-2 rounded bg-slate-900 border border-slate-800">
            <span className="text-slate-400 text-[11px] block">{isAr ? 'أدنى / أعلى ارتفاع:' : 'Min / Max Elevation:'}</span>
            <strong className="text-amber-300 text-sm font-mono">{minElev}m / {maxElev}m</strong>
          </div>
          <div className="p-2 rounded bg-slate-900 border border-slate-800">
            <span className="text-slate-400 text-[11px] block">{isAr ? 'إجمالي الصعود:' : 'Total Ascent:'}</span>
            <strong className="text-emerald-300 text-sm font-mono">+{Math.round(totalAscent)}m</strong>
          </div>
          <div className="p-2 rounded bg-slate-900 border border-slate-800">
            <span className="text-slate-400 text-[11px] block">{isAr ? 'إجمالي الهبوط:' : 'Total Descent:'}</span>
            <strong className="text-rose-300 text-sm font-mono">-{Math.round(totalDescent)}m</strong>
          </div>
        </div>

        {/* Chart View */}
        <div className="p-4 flex flex-col items-center justify-center bg-slate-950">
          {loading ? (
            <div className="py-20 flex items-center gap-2 text-slate-400 text-xs">
              <RefreshCw className="w-5 h-5 animate-spin text-emerald-400" />
              <span>{isAr ? 'جاري حساب الارتفاعات التضاريسية عبر بايثون...' : 'Calculating Terrain Elevation in Python...'}</span>
            </div>
          ) : error ? <p role="alert" className="p-8 text-rose-300">{error}</p> : (
            <div className="w-full flex flex-col items-center">
              <svg
                viewBox={`0 0 ${svgWidth} ${svgHeight}`}
                className="w-full h-auto max-h-64 overflow-visible"
              >
                {/* Horizontal Grid lines */}
                {[0, 0.25, 0.5, 0.75, 1.0].map((ratio, idx) => {
                  const y = padding + chartH * ratio;
                  const elevVal = Math.round(maxElev - ratio * (maxElev - minElev));
                  return (
                    <g key={idx}>
                      <line
                        x1={padding}
                        y1={y}
                        x2={padding + chartW}
                        y2={y}
                        stroke="#334155"
                        strokeDasharray="2, 2"
                      />
                      <text
                        x={padding - 6}
                        y={y + 4}
                        fill="#94a3b8"
                        fontSize="9"
                        textAnchor="end"
                        fontFamily="monospace"
                      >
                        {elevVal}m
                      </text>
                    </g>
                  );
                })}

                {/* Shaded Area */}
                <polygon
                  points={areaPolygonStr}
                  fill="url(#elevGrad)"
                  opacity="0.35"
                />

                {/* Elevation Line */}
                <polyline
                  points={pointsStr}
                  fill="none"
                  stroke="#10b981"
                  strokeWidth="2.5"
                  strokeLinejoin="round"
                />

                {/* Data Points */}
                {samples.map((s, idx) => (
                  <circle
                    key={idx}
                    cx={getSvgX(s)}
                    cy={getSvgY(s)}
                    r={hoveredSample?.index === s.index ? 5 : 2}
                    fill={hoveredSample?.index === s.index ? '#34d399' : '#10b981'}
                    className="cursor-pointer transition-all"
                    onMouseEnter={() => setHoveredSample(s)}
                  />
                ))}

                {/* Gradient Definition */}
                <defs>
                  <linearGradient id="elevGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#10b981" stopOpacity="0.8" />
                    <stop offset="100%" stopColor="#10b981" stopOpacity="0.05" />
                  </linearGradient>
                </defs>
              </svg>

              {/* Hovered Sample Tooltip */}
              {hoveredSample && (
                <div className="mt-2 text-xs font-mono text-slate-300 bg-slate-900 px-3 py-1 rounded border border-slate-800">
                  {isAr ? 'المسافة:' : 'Distance:'} <strong className="text-cyan-300">{hoveredSample.distance_km} km</strong> |{' '}
                  {isAr ? 'الارتفاع:' : 'Elevation:'} <strong className="text-emerald-400">{hoveredSample.elevation_m}m</strong> |{' '}
                  {hoveredSample.lat.toFixed(5)}°, {hoveredSample.lon.toFixed(5)}°
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </DraggableWindow>
  );
};
