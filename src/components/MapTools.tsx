import { storeAppValue } from '../utils/portableState';
import React, { useEffect, useRef, useState } from 'react';
import type L from 'leaflet';
import { ArrowLeft, ArrowRight, Scan, Star, Trash2, Eye, EyeOff, Mountain, X } from 'lucide-react';
import { MapSource } from '../types';

export interface ContourDisplay { visible: boolean; majorOnly: boolean; opacity: number; }
interface SavedView { id: string; name: string; lat: number; lon: number; zoom: number; source: string; }
const STORAGE = 'sas:saved-views:v1';
function readViews(): SavedView[] {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE) || '[]');
    return Array.isArray(raw) ? raw.filter(v => typeof v.id === 'string' && typeof v.name === 'string' &&
      typeof v.source === 'string' && Number.isFinite(v.lat) && Math.abs(v.lat) <= 85 && Number.isFinite(v.lon) &&
      Math.abs(v.lon) <= 180 && Number.isInteger(v.zoom) && v.zoom >= 1 && v.zoom <= 21).slice(0, 50) : [];
  } catch { return []; }
}

export function MapTools({ lang, currentSource, sources, onSelectSource, onSelectView, onOpenTopography, contours, display, onDisplayChange, onClearContours }: {
  lang: 'ar' | 'en'; currentSource: MapSource; sources: MapSource[]; onSelectSource: (s: MapSource) => void;
  onSelectView: () => void; onOpenTopography: () => void; contours: any;
  display: ContourDisplay; onDisplayChange: (d: ContourDisplay) => void; onClearContours: () => void;
}) {
  const ar = lang === 'ar';
  const [saved, setSaved] = useState(readViews);
  const [open, setOpen] = useState(false);
  useEffect(()=>{const show=()=>setOpen(true);window.addEventListener('sas:open-favorites',show);return()=>window.removeEventListener('sas:open-favorites',show);},[]);
  const [name, setName] = useState('');
  const [message, setMessage] = useState('');
  const [nav, setNav] = useState({ back: false, forward: false });
  const history = useRef<{ views: {lat: number; lon: number; zoom: number}[]; index: number; replay: boolean }>({ views: [], index: -1, replay: false });
  const map = () => (window as any).__SAS_MAP as L.Map | undefined;
  useEffect(() => {
    let detach = () => {};
    const attach = () => {
      detach(); const m = map(); if (!m) return;
      history.current = { views: [], index: -1, replay: false };
      const record = () => {
        const h = history.current;
        if (h.replay) h.replay = false;
        else {
          const c = m.getCenter(); const v = { lat: c.lat, lon: c.lng, zoom: m.getZoom() };
          const last = h.views[h.index];
          if (!last || Math.abs(last.lat-v.lat) > 1e-8 || Math.abs(last.lon-v.lon) > 1e-8 || last.zoom !== v.zoom) {
            h.views = [...h.views.slice(0, h.index+1), v].slice(-50); h.index = h.views.length-1;
          }
        }
        setNav({ back: h.index > 0, forward: h.index < h.views.length-1 });
      };
      record(); m.on('moveend', record); detach = () => { m.off('moveend', record); };
    };
    window.addEventListener('sas:map-ready', attach); attach();
    return () => { window.removeEventListener('sas:map-ready', attach); detach(); };
  }, []);
  const navigate = (delta: number) => {
    const m = map(); const h = history.current; const i = h.index+delta;
    if (!m || i < 0 || i >= h.views.length) return;
    h.index = i; h.replay = true; const v = h.views[i]; m.setView([v.lat,v.lon],v.zoom,{ animate:false });
  };
  const persist = (next: SavedView[]) => {
    setSaved(next);
    try { storeAppValue(STORAGE, JSON.stringify(next)); setMessage(''); }
    catch { setMessage(ar ? 'تعذر حفظ المفضلة في المتصفح.' : 'Browser could not persist favorites.'); }
  };
  const save = () => {
    const m = map(); if (!m || !name.trim()) return;
    if (saved.length >= 50) { setMessage(ar ? 'الحد الأقصى 50 موقعاً. احذف موقعاً أولاً.' : 'Maximum 50 places. Delete one first.'); return; }
    const c = m.getCenter(); persist([...saved,{ id: crypto.randomUUID(), name:name.trim(),lat:c.lat,lon:c.wrap().lng,zoom:m.getZoom(),source:currentSource.id }]); setName('');
  };
  const button = 'p-1.5 rounded border border-slate-700 bg-slate-950 hover:bg-slate-800 disabled:opacity-30 flex items-center gap-1.5';
  const icon = (file: string) => <img src={'/assets/sasplanet/' + file} alt="" className="w-4 h-4 object-contain" />;
  return <>
    {open && <section className="fixed top-14 end-3 z-[1100] p-3 w-80 max-w-[90vw] rounded border border-slate-700 bg-slate-900 shadow-2xl space-y-2 text-slate-300 text-[11px]">
      <div className="flex items-center justify-between"><strong className="text-slate-200">{ar ? 'المواقع المحفوظة' : 'Saved places'} ({saved.length})</strong><button className="p-1 text-slate-400 hover:text-white" onClick={() => setOpen(false)} aria-label={ar ? 'إغلاق' : 'Close'}><X className="w-4 h-4" /></button></div>
      <button className={button + ' w-full justify-center'} onClick={onSelectView}><Scan className="w-4 h-4 text-cyan-400" />{ar ? 'تحديد كامل المشهد الحالي' : 'Select current map extent'}</button>
      <form className="flex gap-2" onSubmit={e => {e.preventDefault(); save();}}><input aria-label={ar ? 'اسم الموقع' : 'Place name'} maxLength={80} value={name} onChange={e => setName(e.target.value)} placeholder={ar ? 'اسم الموقع الحالي' : 'Name this location'} className="min-w-0 flex-1 bg-slate-950 rounded border border-slate-700 p-2" /><button disabled={!name.trim()} className={button} type="submit" title={ar ? 'حفظ الموقع' : 'Save place'} aria-label={ar ? 'حفظ الموقع' : 'Save place'}><Star className="w-4 h-4 text-amber-400" /></button></form>
      {message && <p role="alert" className="text-rose-300">{message}</p>}
      {!saved.length && <p className="text-slate-400 py-2">{ar ? 'احفظ موقعاً للعودة إليه مع خريطة الأساس.' : 'Save a place to restore its position and base map.'}</p>}
      <div className="max-h-64 overflow-y-auto">{saved.map(v => <div key={v.id} className="flex items-center gap-2 border-t border-slate-800">
        <button className="flex-1 text-start p-2 hover:bg-slate-800 truncate" onClick={() => { const s = sources.find(s => s.id === v.source); if (s) onSelectSource(s); map()?.setView([v.lat,v.lon],v.zoom); setOpen(false); }}>{v.name}<span className="block font-mono text-slate-500">{v.lat.toFixed(4)}, {v.lon.toFixed(4)} · z{v.zoom}</span></button>
        <button className="p-2 text-rose-400" onClick={() => persist(saved.filter(s => s.id !== v.id))} aria-label={(ar ? 'حذف ' : 'Delete ') + v.name}><Trash2 className="w-4 h-4" /></button>
      </div>)}</div>
    </section>}
    {contours && <section className="fixed bottom-16 end-3 z-[1090] p-2.5 rounded border border-slate-700 bg-slate-900 shadow-2xl flex flex-wrap items-center gap-2 text-slate-300 text-[11px]">
      <Mountain className="w-4 h-4 text-amber-400" />
      <button className={button} onClick={() => onDisplayChange({...display,visible:!display.visible})} aria-pressed={display.visible}>{display.visible ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}{ar ? 'عرض الخطوط' : 'Show contours'}</button>
      <label className="flex items-center gap-1"><input type="checkbox" checked={display.majorOnly} onChange={e => onDisplayChange({...display,majorOnly:e.target.checked})} />{ar ? 'الرئيسية فقط' : 'Index only'}</label>
      <label className="flex items-center gap-1">{ar ? 'العتامة' : 'Opacity'}<input className="w-20" type="range" min="10" max="100" value={Math.round(display.opacity*100)} onChange={e => onDisplayChange({...display,opacity:Number(e.target.value)/100})} />{Math.round(display.opacity*100)}%</label>
      <button className={button} onClick={onClearContours} title={ar ? 'إزالة طبقة التسوية' : 'Remove contour layer'} aria-label={ar ? 'إزالة طبقة التسوية' : 'Remove contour layer'}><Trash2 className="w-4 h-4 text-rose-400" /></button>
      <span className="text-amber-300">{contours.properties?.interval} m · {contours.features.length} {ar ? 'خط' : 'lines'}</span>
    </section>}
  </>;
}
