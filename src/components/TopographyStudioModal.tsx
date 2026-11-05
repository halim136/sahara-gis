import React, { useEffect, useRef, useState } from 'react';
import { X, Mountain, Download, RefreshCw, Upload, CheckCircle2, AlertCircle } from 'lucide-react';
import type { AppSettings } from '../utils/settings';
import { BoundingBox } from '../types';

interface Props {
  settings: AppSettings;
  isOpen: boolean;
  onClose: () => void;
  bbox: BoundingBox;
  onApplyContoursToMap: (geojson: any) => void;
  lang: 'ar' | 'en';
  isOfflineMode?: boolean;
}

export const TopographyStudioModal: React.FC<Props> = ({ settings, isOpen, onClose, bbox, onApplyContoursToMap, lang, isOfflineMode = false }) => {
  const isAr = lang === 'ar';
  const [interval, setInterval] = useState(settings.contourInterval);
  const [resolution, setResolution] = useState(settings.terrainResolution);
  const [source, setSource] = useState<string>(settings.terrainSource);
  const [aboveSea, setAboveSea] = useState(true);
  const [busy, setBusy] = useState('');
  const [status, setStatus] = useState('');
  const [error, setError] = useState(false);
  const [contours, setContours] = useState<any>(null);
  const [raster, setRaster] = useState<any>(null);
  const [imported, setImported] = useState<string[]>([]);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  if (!isOpen) return null;

  const request = async (kind: 'contour' | 'render') => {
    setBusy(kind); setStatus(''); setError(false);
    const abort = new AbortController();
    controller.current = abort;
    try {
      const res = await fetch('/api/python/topo/' + kind, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: abort.signal,
        body: JSON.stringify({ bbox: [bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat],
          source, offline: isOfflineMode, interval, resolution, above_sea_only: aboveSea, width: 768, height: 768 })
      });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.error || 'Terrain request failed');
      if (kind === 'contour') {
        setContours(data.contours); onApplyContoursToMap(data.contours);
        setStatus(data.contours.features.length ? (isAr ? 'تم استخراج خطوط التسوية من بيانات ارتفاع حقيقية.' : 'Contours generated from real elevation data.')
          : (isAr ? 'لا توجد خطوط عند الفاصل المختار. جرّب فاصلاً أصغر أو غيّر المنطقة.' : 'No contours at this interval. Try a smaller interval or another region.'));
      } else {
        setRaster(data.result);
        setStatus(isAr ? 'تم إنشاء الخريطة الطبوغرافية.' : 'Topographic raster created.');
      }
    } catch (e: any) {
      if (e.name !== 'AbortError') { setStatus(e.message); setError(true); }
    } finally { setBusy(''); }
  };

  const importHgt = async (files: FileList | null) => {
    if (!files?.length) return;
    setBusy('import'); setStatus(''); setError(false);
    const abort = new AbortController(); controller.current = abort;
    try {
      for (const file of Array.from(files)) {
        if (!/^[NS]\d{2}[EW]\d{3}\.hgt$/i.test(file.name) || ![1201*1201*2,3601*3601*2].includes(file.size)) {
          throw new Error(isAr ? 'اختر ملف SRTM HGT صالحاً مثل N36E003.hgt بدقة 1201 أو 3601.' : 'Choose a valid SRTM HGT file, e.g. N36E003.hgt, with 1201 or 3601 samples per side.');
        }
        const content = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]);
          reader.onerror = () => reject(new Error('Cannot read HGT file')); reader.readAsDataURL(file);
        });
        const res = await fetch('/api/python/topo/import-hgt', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          signal: abort.signal, body: JSON.stringify({ name: file.name, content }) });
        const data = await res.json();
        if (!res.ok || !data.success) throw new Error(data.error || 'SRTM import failed');
        setImported(prev => [...new Set([...prev, data.name])]);
      }
      setSource('srtm'); setStatus(isAr ? 'تم استيراد ملفات الارتفاع. يمكنك الآن توليد خطوط التسوية محلياً.' : 'HGT files imported. You can now generate contours locally.');
    } catch (e: any) { if (e.name !== 'AbortError') { setStatus(e.message); setError(true); } }
    finally { setBusy(''); }
  };

  const download = () => {
    if (!contours) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(contours, null, 2)], { type: 'application/geo+json' }));
    const a = document.createElement('a'); a.href = url;
    a.download = 'contours_' + contours.properties.interval + 'm.geojson'; a.click(); URL.revokeObjectURL(url);
  };
  const meta = contours?.properties;
  const btn = 'px-3 py-2 rounded border border-slate-700 bg-slate-800 hover:bg-slate-700 disabled:opacity-40 flex items-center justify-center gap-2';
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 bg-black/80 backdrop-blur-xs">
      <section role="dialog" aria-modal="true" aria-labelledby="topo-title" className="w-full max-w-4xl max-h-[90vh] overflow-y-auto rounded-lg border border-slate-700 bg-slate-900 text-slate-200 shadow-2xl text-xs">
        <div className="flex justify-between items-center p-4 border-b border-slate-800">
          <h2 id="topo-title" className="font-bold text-sm flex items-center gap-2"><Mountain className="w-5 h-5 text-amber-400" />{isAr ? 'خطوط التسوية والتضاريس الحقيقية' : 'Real Terrain & Contours'}</h2>
          <button onClick={onClose} aria-label={isAr ? 'إغلاق' : 'Close'} className="p-1 hover:bg-slate-800 rounded"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-4 space-y-4">
          <p className="text-slate-400">{isAr ? 'المنطقة المحددة أو المشهد الحالي' : 'Selection or current map view'} <span dir="ltr" className="font-mono text-cyan-300">{bbox.min_lon.toFixed(4)}, {bbox.min_lat.toFixed(4)} → {bbox.max_lon.toFixed(4)}, {bbox.max_lat.toFixed(4)}</span> · WGS84</p>
          <fieldset disabled={Boolean(busy)} className="space-y-4 disabled:opacity-60">
            <div className="grid sm:grid-cols-2 gap-4">
              <label className="space-y-2"><span className="block">{isAr ? 'مصدر الارتفاعات' : 'Elevation source'}</span>
                <select value={source} onChange={e => setSource(e.target.value)} className="w-full p-2 bg-slate-950 border border-slate-700 rounded">
                  <option value="terrain">Mapzen Terrain Tiles</option><option value="srtm">{isAr ? 'ملفات SRTM HGT المحلية' : 'Local SRTM HGT files'}</option>
                </select>
              </label>
              <label className="space-y-2"><span className="block">{isAr ? 'دقة شبكة الاستخراج' : 'Extraction grid'}</span>
                <select value={resolution} onChange={e => setResolution(Number(e.target.value))} className="w-full p-2 bg-slate-950 border border-slate-700 rounded">
                  {[128,256,512].map(n => <option key={n} value={n}>{n} × {n}</option>)}
                </select>
              </label>
            </div>
            <p className="text-slate-400 leading-relaxed">{isAr ? 'تُحمّل بيانات Mapzen عند الحاجة وتُحفظ للاستخدام لاحقاً. حجم الشبكة لا يزيد دقة المصدر؛ حدّد منطقة أصغر لإظهار تفاصيل أكثر. لا تُستخدم ارتفاعات اصطناعية عند تعذر التحميل.' : 'Mapzen data downloads on demand and is cached. Grid size does not increase source accuracy; select a smaller area for more detail. Unavailable data is never replaced with synthetic heights.'}</p>
            {isOfflineMode && <p className="text-amber-300">{isAr ? 'وضع عدم الاتصال: تُستخدم البيانات المخزنة أو ملفات SRTM فقط.' : 'Offline: cached terrain or local SRTM files only.'}</p>}
            <label className={btn + ' cursor-pointer w-fit'}><Upload className="w-4 h-4" />{isAr ? 'استيراد ملفات SRTM (.hgt)' : 'Import SRTM (.hgt)'}
              <input type="file" accept=".hgt" multiple disabled={Boolean(busy)} className="sr-only" onChange={e => { void importHgt(e.target.files); e.target.value = ''; }} />
            </label>
            {imported.length > 0 && <p className="font-mono text-emerald-300" dir="ltr">{imported.join(', ')}</p>}
            <div className="block space-y-2"><span>{isAr ? 'الفاصل الرأسي بين خطوط التسوية (متر)' : 'Contour interval (meters)'}</span>
              <div className="flex flex-wrap gap-2 mt-2">{[5,10,20,25,50,100,250].map(n => <button key={n} aria-pressed={interval === n} onClick={() => setInterval(n)} className={'px-3 py-2 rounded border ' + (interval === n ? 'bg-amber-600 border-amber-400 text-white' : 'border-slate-700 bg-slate-950')}>{n} m</button>)}</div>
            </div>
            <label className="flex gap-2 items-center"><input type="checkbox" checked={aboveSea} onChange={e => setAboveSea(e.target.checked)} />{isAr ? 'إخفاء خطوط الارتفاع صفر وما دون مستوى البحر' : 'Exclude zero and below sea level contours'}</label>
            <div className="flex flex-wrap gap-2">
              <button className={btn + ' flex-1 !bg-amber-600 text-white'} onClick={() => void request('contour')}>{busy === 'contour' ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Mountain className="w-4 h-4" />}{isAr ? 'توليد وعرض خطوط التسوية' : 'Generate & show contours'}</button>
              <button className={btn} onClick={() => void request('render')}>{busy === 'render' ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}{isAr ? 'إنشاء خريطة تضاريس BMP + BPW' : 'Render terrain BMP + BPW'}</button>
            </div>
          </fieldset>
          {busy && <p role="status" className="text-cyan-300">{isAr ? 'جارٍ معالجة بيانات الارتفاع…' : 'Processing elevation data…'}</p>}
          {status && <p role={error ? 'alert' : 'status'} className={'p-3 rounded border flex items-center gap-2 ' + (error ? 'border-rose-800 text-rose-300' : 'border-emerald-800 text-emerald-300')}>{error ? <AlertCircle className="w-4 h-4 shrink-0" /> : <CheckCircle2 className="w-4 h-4 shrink-0" />}{status}</p>}
          {meta && <div className="p-3 rounded border border-slate-700 space-y-2">
            <p>{meta.source} · {meta.line_count} {isAr ? 'خط' : 'lines'} · {meta.min_elevation.toFixed(1)}–{meta.max_elevation.toFixed(1)} m</p>
            <p className="text-amber-300">{isAr ? 'تباعد عينات الشبكة:' : 'Grid sample spacing:'} {meta.sample_spacing_m} m · {isAr ? 'حجم بكسل المصدر التقريبي:' : 'Approx. source pixel size:'} {meta.source_pixel_size_m} m</p>
            <p className="text-slate-400">{meta.attribution}</p>
            <button onClick={download} className={btn}><Download className="w-4 h-4" />{isAr ? 'تصدير خطوط التسوية GeoJSON' : 'Export contours as GeoJSON'}</button>
          </div>}
          {raster && <div className="flex flex-wrap gap-2"><a className={btn} href={raster.download_url} download>{isAr ? 'تنزيل خريطة التضاريس' : 'Download terrain raster'} (.BMP)</a><a className={btn} href={raster.world_file_url} download>{isAr ? 'ملف الإسناد الجغرافي' : 'World file'} (.BPW, EPSG:4326)</a></div>}
          <p className="text-slate-500">{isAr ? 'بيانات التضاريس:' : 'Terrain data:'} <a href="https://registry.opendata.aws/terrain-tiles/" target="_blank" rel="noreferrer" className="underline">Mapzen / AWS Open Data</a> · <a href="https://github.com/tilezen/joerd/blob/master/docs/attribution.md" target="_blank" rel="noreferrer" className="underline">{isAr ? 'المصادر والإسناد' : 'Sources & attribution'}</a></p>
        </div>
      </section>
    </div>
  );
};
