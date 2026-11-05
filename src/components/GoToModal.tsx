import React, { useState, useEffect } from 'react';
import { X, Crosshair, ArrowRight, Compass, Globe } from 'lucide-react';
import { tileToLonLat } from '../utils/geoUtils';
import { DraggableWindow } from './DraggableWindow';

interface GoToModalProps {
  isOpen: boolean;
  onClose: () => void;
  onNavigate: (lat: number, lon: number, zoom?: number) => void;
  lang: 'ar' | 'en';
  defaultNordSaharaZone?: number;
  preferNordSahara?: boolean;
}

export const GoToModal: React.FC<GoToModalProps> = ({
  isOpen,
  onClose,
  onNavigate,
  lang,
  defaultNordSaharaZone=31,
  preferNordSahara=false
}) => {
  const isAr = lang === 'ar';
  const [mode, setMode] = useState<'decimal' | 'nord_sahara' | 'tile' | 'preset'>('decimal');

  // Decimal
  const [latStr, setLatStr] = useState<string>('30.0444');
  const [lonStr, setLonStr] = useState<string>('31.2357');
  const [zoom, setZoom] = useState<number>(15);

  // UTM Nord Sahara
  const [nsZone, setNsZone] = useState<number>(31);
  const [nsEasting, setNsEasting] = useState<string>('505331.73');
  const [nsNorthing, setNsNorthing] = useState<string>('4067244.16');
  const [nsLoading, setNsLoading] = useState<boolean>(false);

  const [nsError,setNsError]=useState('');
  useEffect(()=>{if(isOpen){setNsZone(defaultNordSaharaZone);if(preferNordSahara)setMode('nord_sahara');setNsError('');}},[isOpen]);

  // Tile
  const [tileX, setTileX] = useState<string>('19227');
  const [tileY, setTileY] = useState<string>('13514');
  const [tileZ, setTileZ] = useState<number>(15);

  if (!isOpen) return null;

  const presets = [
    { name: isAr ? 'الجزائر العاصمة (Algiers)' : 'Algiers', lat: 36.7538, lon: 3.0588, z: 15 },
    { name: isAr ? 'وهران (Oran)' : 'Oran', lat: 35.6987, lon: -0.6349, z: 15 },
    { name: isAr ? 'حاسي مسعود (Hassi Messaoud)' : 'Hassi Messaoud', lat: 31.6804, lon: 6.0728, z: 14 },
    { name: isAr ? 'أهرامات الجيزة' : 'Giza Pyramids', lat: 29.9792, lon: 31.1342, z: 16 },
    { name: isAr ? 'مكة المكرمة' : 'Mecca', lat: 21.4225, lon: 39.8262, z: 16 },
    { name: isAr ? 'دبي برج خليفة' : 'Burj Khalifa, Dubai', lat: 25.1972, lon: 55.2744, z: 16 }
  ];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (mode === 'decimal') {
      const lat = parseFloat(latStr);
      const lon = parseFloat(lonStr);
      if (!isNaN(lat) && !isNaN(lon)) {
        onNavigate(lat, lon, zoom);
        onClose();
      }
    } else if (mode === 'nord_sahara') {
      const e_val = parseFloat(nsEasting);
      const n_val = parseFloat(nsNorthing);
      if (!isNaN(e_val) && !isNaN(n_val)) {
        setNsLoading(true);setNsError('');
        try {
          const res = await fetch('/api/python/nord-sahara/inverse', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ easting: e_val, northing: n_val, zone: nsZone })
          });
          const data = await res.json();
          if (data.success && data.data) {
            onNavigate(data.data.wgs84_lat, data.data.wgs84_lon, zoom);
            onClose();
          }else setNsError(data.error||'Coordinate conversion failed');
        } catch (_) {setNsError(isAr?'تعذر تحويل الإحداثيات.':'Unable to convert coordinates.');}
        setNsLoading(false);
      }
    } else if (mode === 'tile') {
      const tx = parseInt(tileX);
      const ty = parseInt(tileY);
      if (!isNaN(tx) && !isNaN(ty)) {
        const [lon, lat] = tileToLonLat(tx + 0.5, ty + 0.5, tileZ);
        onNavigate(lat, lon, tileZ);
        onClose();
      }
    }
  };

  return (
    <DraggableWindow>
      <div className="relative w-full max-w-md bg-slate-900 border border-slate-700 rounded-lg shadow-2xl overflow-hidden text-slate-200">
        <div className="flex items-center justify-between px-4 py-2.5 bg-slate-950 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <Crosshair className="w-4 h-4 text-blue-400" />
            <h2 className="text-sm font-bold text-white">
              {isAr ? 'الانتقال إلى إحداثيات (Go To Coordinates)' : 'Go To Coordinates'}
            </h2>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tab Header */}
        <div className="flex border-b border-slate-800 bg-slate-950/80 px-2 text-xs overflow-x-auto">
          <button
            onClick={() => setMode('decimal')}
            className={`px-3 py-2 border-b-2 font-medium shrink-0 ${
              mode === 'decimal' ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-400'
            }`}
          >
            {isAr ? 'عشري (WGS84)' : 'Decimal Lat/Lon'}
          </button>
          <button
            onClick={() => setMode('nord_sahara')}
            className={`px-3 py-2 border-b-2 font-medium shrink-0 ${
              mode === 'nord_sahara' ? 'border-amber-500 text-amber-400' : 'border-transparent text-slate-400'
            }`}
          >
            {isAr ? 'UTM Nord Sahara' : 'UTM Nord Sahara'}
          </button>
          <button
            onClick={() => setMode('tile')}
            className={`px-3 py-2 border-b-2 font-medium shrink-0 ${
              mode === 'tile' ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-400'
            }`}
          >
            {isAr ? 'البلاطة (Tile X/Y)' : 'Tile X/Y'}
          </button>
          <button
            onClick={() => setMode('preset')}
            className={`px-3 py-2 border-b-2 font-medium shrink-0 ${
              mode === 'preset' ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-400'
            }`}
          >
            {isAr ? 'معالم مشهورة' : 'Presets'}
          </button>
        </div>

        <div className="p-4">
          {nsError&&<p role="alert" className="text-rose-400 text-xs mb-3">{nsError}</p>}
          {mode === 'decimal' && (
            <form onSubmit={handleSubmit} className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-300 font-semibold mb-1">{isAr ? 'خط العرض (Latitude):' : 'Latitude:'}</label>
                <input
                  type="text"
                  required
                  value={latStr}
                  onChange={(e) => setLatStr(e.target.value)}
                  placeholder="30.0444"
                  className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 font-mono text-slate-200"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-semibold mb-1">{isAr ? 'خط الطول (Longitude):' : 'Longitude:'}</label>
                <input
                  type="text"
                  required
                  value={lonStr}
                  onChange={(e) => setLonStr(e.target.value)}
                  placeholder="31.2357"
                  className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 font-mono text-slate-200"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-semibold mb-1">{isAr ? 'مستوى التكبير (Zoom):' : 'Zoom Level:'}</label>
                <select
                  value={zoom}
                  onChange={(e) => setZoom(Number(e.target.value))}
                  className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-slate-200"
                >
                  {Array.from({ length: 20 }, (_, i) => i + 1).map((z) => (
                    <option key={z} value={z}>Zoom {z}</option>
                  ))}
                </select>
              </div>

              <button
                type="submit"
                className="w-full mt-2 py-2 rounded bg-blue-600 hover:bg-blue-500 text-white font-bold transition-colors"
              >
                {isAr ? 'انتقال إلى الموقع' : 'Navigate to Coordinates'}
              </button>
            </form>
          )}

          {mode === 'nord_sahara' && (
            <form onSubmit={handleSubmit} className="space-y-3 text-xs">
              <div className="p-2 rounded bg-amber-950/30 border border-amber-800/60 text-amber-300 text-[11px] leading-relaxed">
                {isAr
                  ? 'نظام UTM Nord Sahara 1959 على مجسم Clarke 1880 (RGS)، للجزائر.'
                  : 'UTM Nord Sahara 1959 on Clarke 1880 (RGS), for Algeria.'}
              </div>

              <div>
                <label className="block text-slate-300 font-semibold mb-1">{isAr ? 'النطاق (UTM Zone):' : 'UTM Zone:'}</label>
                <select
                  value={nsZone}
                  onChange={(e) => setNsZone(Number(e.target.value))}
                  className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-slate-200"
                >
                  <option value={29}>Zone 29N (9°W - Western Algeria) - EPSG:30729</option>
                  <option value={30}>Zone 30N (3°W - Western Algeria) - EPSG:30730</option>
                  <option value={31}>Zone 31N (3°E - Central Algeria / Algiers) - EPSG:30731</option>
                  <option value={32}>Zone 32N (9°E - Eastern Algeria) - EPSG:30732</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-slate-300 font-semibold mb-1">{isAr ? 'الإحداثي السيني (Easting):' : 'Easting (X):'}</label>
                  <input
                    type="text"
                    required
                    value={nsEasting}
                    onChange={(e) => setNsEasting(e.target.value)}
                    placeholder="505331.73"
                    className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 font-mono text-slate-200"
                  />
                </div>
                <div>
                  <label className="block text-slate-300 font-semibold mb-1">{isAr ? 'الإحداثي الصادي (Northing):' : 'Northing (Y):'}</label>
                  <input
                    type="text"
                    required
                    value={nsNorthing}
                    onChange={(e) => setNsNorthing(e.target.value)}
                    placeholder="4067244.16"
                    className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 font-mono text-slate-200"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-300 font-semibold mb-1">{isAr ? 'مستوى التكبير (Zoom):' : 'Zoom Level:'}</label>
                <select
                  value={zoom}
                  onChange={(e) => setZoom(Number(e.target.value))}
                  className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-slate-200"
                >
                  {Array.from({ length: 20 }, (_, i) => i + 1).map((z) => (
                    <option key={z} value={z}>Zoom {z}</option>
                  ))}
                </select>
              </div>

              <button
                type="submit"
                disabled={nsLoading}
                className="w-full mt-2 py-2 rounded bg-amber-600 hover:bg-amber-500 text-white font-bold transition-colors disabled:opacity-50"
              >
                {nsLoading ? (isAr ? 'جاري التحويل...' : 'Converting...') : (isAr ? 'تحويل والانتقال إلى موقع Nord Sahara' : 'Convert & Navigate')}
              </button>
            </form>
          )}

          {mode === 'tile' && (
            <form onSubmit={handleSubmit} className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-slate-300 font-semibold mb-1">Tile X:</label>
                  <input
                    type="number"
                    required
                    value={tileX}
                    onChange={(e) => setTileX(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 font-mono text-slate-200"
                  />
                </div>
                <div>
                  <label className="block text-slate-300 font-semibold mb-1">Tile Y:</label>
                  <input
                    type="number"
                    required
                    value={tileY}
                    onChange={(e) => setTileY(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 font-mono text-slate-200"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-300 font-semibold mb-1">Zoom:</label>
                <input
                  type="number"
                  min="1"
                  max="22"
                  value={tileZ}
                  onChange={(e) => setTileZ(Number(e.target.value))}
                  className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 font-mono text-slate-200"
                />
              </div>

              <button
                type="submit"
                className="w-full mt-2 py-2 rounded bg-blue-600 hover:bg-blue-500 text-white font-bold transition-colors"
              >
                {isAr ? 'انتقال إلى البلاطة' : 'Navigate to Tile'}
              </button>
            </form>
          )}

          {mode === 'preset' && (
            <div className="space-y-1.5 max-h-60 overflow-y-auto">
              {presets.map((p, i) => (
                <button
                  key={i}
                  onClick={() => {
                    onNavigate(p.lat, p.lon, p.z);
                    onClose();
                  }}
                  className="w-full text-start p-2 rounded bg-slate-950 hover:bg-slate-800 border border-slate-800 text-xs flex items-center justify-between transition-colors"
                >
                  <span className="font-semibold text-slate-200">{p.name}</span>
                  <span className="text-slate-500 font-mono text-[11px]">{p.lat}, {p.lon}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </DraggableWindow>
  );
};
