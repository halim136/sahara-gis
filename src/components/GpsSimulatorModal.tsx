import React, { useState, useEffect, useRef } from 'react';
import { DraggableWindow } from './DraggableWindow';
import {
  X,
  Navigation,
  Play,
  Pause,
  RotateCcw,
  Compass,
  Gauge,
  Satellite,
  Activity
} from 'lucide-react';

interface GpsSimulatorModalProps {
  isOpen: boolean;
  onClose: () => void;
  gpsPosition: { lat: number; lon: number; bearing: number } | null;
  onUpdatePosition: (pos: { lat: number; lon: number; bearing: number } | null) => void;
  lang: 'ar' | 'en';
}

// Simulation track around Giza / Cairo
const SIMULATED_TRACK: [number, number, number][] = [
  [30.0444, 31.2357, 180],
  [30.0380, 31.2320, 195],
  [30.0290, 31.2250, 210],
  [30.0150, 31.2100, 225],
  [30.0050, 31.1850, 240],
  [29.9900, 31.1600, 255],
  [29.9792, 31.1342, 270],
  [29.9850, 31.1200, 300],
  [30.0050, 31.1350, 330],
  [30.0250, 31.1700, 15],
  [30.0444, 31.2357, 45]
];

export const GpsSimulatorModal: React.FC<GpsSimulatorModalProps> = ({
  isOpen,
  onClose,
  gpsPosition,
  onUpdatePosition,
  lang
}) => {
  const isAr = lang === 'ar';
  const [isPlaying, setIsPlaying] = useState<boolean>(true);
  const [speedKmh, setSpeedKmh] = useState<number>(65);
  const [altitudeM, setAltitudeM] = useState<number>(142);
  const [stepIndex, setStepIndex] = useState<number>(0);
  const [nmeaLog, setNmeaLog] = useState<string[]>([]);
  const stepIndexRef = useRef<number>(0);

  useEffect(() => {
    let interval: ReturnType<typeof setInterval> | null = null;

    if (isOpen && isPlaying) {
      interval = setInterval(() => {
        const next = (stepIndexRef.current + 1) % SIMULATED_TRACK.length;
        stepIndexRef.current = next;
        setStepIndex(next);

        const [lat, lon, bearing] = SIMULATED_TRACK[next];
        onUpdatePosition({ lat, lon, bearing });

        // Generate simulated NMEA 0183 sentences
        const now = new Date();
        const timeStr = now.toISOString().substring(11, 19).replace(/:/g, '');
        const gprmc = `$GPRMC,${timeStr}.00,A,${(lat * 100).toFixed(4)},N,${(lon * 100).toFixed(4)},E,${(speedKmh * 0.539957).toFixed(1)},${bearing.toFixed(1)},301026,,,A*7C`;
        const gpgga = `$GPGGA,${timeStr}.00,${(lat * 100).toFixed(4)},N,${(lon * 100).toFixed(4)},E,1,08,0.9,${altitudeM}.2,M,16.5,M,,*42`;

        setNmeaLog((old) => [gprmc, gpgga, ...old.slice(0, 10)]);
      }, 1200);
    }

    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isOpen, isPlaying, speedKmh, altitudeM, onUpdatePosition]);

  if (!isOpen) return null;

  const currentPos = SIMULATED_TRACK[stepIndex];

  return (
    <DraggableWindow>
      <div className="relative w-full max-w-2xl flex flex-col bg-slate-900 border border-slate-700 rounded-lg shadow-2xl overflow-hidden text-slate-200">
        {/* Title Bar */}
        <div className="flex items-center justify-between px-4 py-2.5 bg-slate-950 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <Navigation className="w-5 h-5 text-cyan-400" />
            <h2 className="text-sm font-bold text-white">
              {isAr ? 'محاكي وتتبع نظام الملاحة GPS (NMEA 0183 Simulator)' : 'GPS Tracking & NMEA Simulator'}
            </h2>
            <span className="text-[10px] bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 px-2 py-0.5 rounded font-mono">
              3D DGPS FIX
            </span>
          </div>

          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Dashboards Grid */}
        <div className="p-4 space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
            {/* Speedometer */}
            <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 flex flex-col items-center justify-center text-center">
              <Gauge className="w-6 h-6 text-blue-400 mb-1" />
              <span className="text-slate-400 text-[10px] uppercase font-bold">{isAr ? 'السرعة' : 'Speed'}</span>
              <strong className="text-xl text-white font-mono">{speedKmh}</strong>
              <span className="text-[10px] text-slate-500">km/h</span>
            </div>

            {/* Compass Heading */}
            <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 flex flex-col items-center justify-center text-center">
              <Compass className="w-6 h-6 text-amber-400 mb-1" />
              <span className="text-slate-400 text-[10px] uppercase font-bold">{isAr ? 'الاتجاه' : 'Heading'}</span>
              <strong className="text-xl text-white font-mono">{currentPos[2]}°</strong>
              <span className="text-[10px] text-slate-500">Azimuth</span>
            </div>

            {/* Altitude */}
            <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 flex flex-col items-center justify-center text-center">
              <Activity className="w-6 h-6 text-emerald-400 mb-1" />
              <span className="text-slate-400 text-[10px] uppercase font-bold">{isAr ? 'الارتفاع' : 'Altitude'}</span>
              <strong className="text-xl text-white font-mono">{altitudeM}m</strong>
              <span className="text-[10px] text-slate-500">MSL</span>
            </div>

            {/* Satellites in view */}
            <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 flex flex-col items-center justify-center text-center">
              <Satellite className="w-6 h-6 text-cyan-400 mb-1" />
              <span className="text-slate-400 text-[10px] uppercase font-bold">{isAr ? 'الأقمار' : 'Satellites'}</span>
              <strong className="text-xl text-cyan-300 font-mono">11/14</strong>
              <span className="text-[10px] text-slate-500">HDOP: 0.85</span>
            </div>
          </div>

          {/* Controls */}
          <div className="flex items-center justify-between p-3 bg-slate-950 rounded-lg border border-slate-800">
            <div className="flex items-center gap-2">
              <button
                onClick={() => setIsPlaying(!isPlaying)}
                className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded font-bold text-xs transition-colors ${
                  isPlaying ? 'bg-amber-600 hover:bg-amber-500 text-white' : 'bg-emerald-600 hover:bg-emerald-500 text-white'
                }`}
              >
                {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                <span>{isPlaying ? (isAr ? 'إيقاف مؤقت' : 'Pause') : (isAr ? 'تشغيل المحاكاة' : 'Resume')}</span>
              </button>

              <button
                onClick={() => {
                  stepIndexRef.current = 0;
                  setStepIndex(0);
                  const [lat, lon, bearing] = SIMULATED_TRACK[0];
                  onUpdatePosition({ lat, lon, bearing });
                }}
                className="p-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
                title={isAr ? 'إعادة البدء' : 'Restart'}
              >
                <RotateCcw className="w-4 h-4" />
              </button>
            </div>

            <div className="flex items-center gap-2 text-xs">
              <span className="text-slate-400">{isAr ? 'تعديل السرعة:' : 'Speed:'}</span>
              <input
                type="range"
                min="20"
                max="180"
                value={speedKmh}
                onChange={(e) => setSpeedKmh(Number(e.target.value))}
                className="w-28 accent-cyan-500"
              />
            </div>
          </div>

          {/* NMEA Sentence Terminal */}
          <div className="space-y-1">
            <span className="text-[11px] font-mono text-slate-400 flex items-center gap-1.5">
              <span>{isAr ? 'بث جمل NMEA 0183 المباشر عبر المنفذ التسلسلي:' : 'Live Serial NMEA 0183 Stream:'}</span>
            </span>
            <div className="p-2.5 bg-black/95 border border-slate-800 rounded-lg font-mono text-[11px] text-cyan-400 max-h-36 overflow-y-auto space-y-0.5 select-text">
              {nmeaLog.map((line, i) => (
                <div key={i}>{line}</div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </DraggableWindow>
  );
};
