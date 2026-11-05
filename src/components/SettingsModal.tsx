import React, {useState} from 'react';
import {X, Settings, Check, RotateCcw, Plus, Trash2, Layers} from 'lucide-react';
import {AppSettings, DEFAULT_SETTINGS, normalizeSettings} from '../utils/settings';
import {DraggableWindow} from './DraggableWindow';
import {MapSource} from '../types';
import {buildCustomSource} from '../utils/customSources';
export function SettingsModal({settings,sources,customSources=[],onCustomSourcesChange,onSave,onClose}:{settings:AppSettings;sources:MapSource[];customSources?:MapSource[];onCustomSourcesChange?:(list:MapSource[])=>void;onSave:(s:AppSettings)=>void;onClose:()=>void}) {
  const [draft,setDraft] = useState(settings); const [tab,setTab] = useState('display');
  const ar = settings.language === 'ar'; const t=(a:string,e:string)=>ar?a:e;
  const [csName,setCsName]=useState(''),[csKind,setCsKind]=useState<'xyz'|'tms'|'wms'>('xyz'),[csUrl,setCsUrl]=useState(''),[csZoom,setCsZoom]=useState(19),[csLayers,setCsLayers]=useState(''),[csCategory,setCsCategory]=useState<MapSource['category']>('Satellite'),[csError,setCsError]=useState('');
  const addCustomSource=()=>{try{const source=buildCustomSource({name:csName,kind:csKind,url:csUrl,maxZoom:csZoom,wmsLayers:csLayers,category:csCategory});onCustomSourcesChange?.([...customSources,source]);setCsName('');setCsUrl('');setCsLayers('');setCsError('');}catch(e:any){setCsError(e.message);}};
  const set=<K extends keyof AppSettings>(k:K,v:AppSettings[K])=>setDraft(s=>({...s,[k]:v}));
  const toggle=(k:keyof AppSettings,a:string,e:string)=><label className="settings-check"><input type="checkbox" checked={Boolean(draft[k])} onChange={ev=>setDraft(s=>({...s,[k]:ev.target.checked}))}/>{t(a,e)}</label>;
  return <DraggableWindow onKeyDown={e=>{if(e.key==='Escape')onClose();}}>
    <section className="desktop-dialog w-full max-w-2xl max-h-[90vh] overflow-auto" role="dialog" aria-modal="true" aria-labelledby="settings-title">
      <div className="desktop-dialog-title"><h2 id="settings-title"><Settings size={17}/>{t('إعدادات البرنامج','Application settings')}</h2><button onClick={onClose} aria-label={t('إغلاق','Close')}><X size={18}/></button></div>
      <div className="desktop-tabs">{[['display','العرض والتنقل','Display & navigation'],['coordinates','الإحداثيات','Coordinates'],['terrain','التضاريس والتحليل','Terrain & analysis'],['sources','مصادر مخصّصة','Custom sources']].map(([id,a,e])=><button key={id} aria-pressed={tab===id} onClick={()=>setTab(id)}>{t(a,e)}</button>)}</div>
      <div className="p-5 space-y-4 text-sm">
        {tab==='display'?<>
          <div className="grid sm:grid-cols-2 gap-4"><label>{t('المظهر','Appearance')}<select value={draft.theme} onChange={e=>set('theme',e.target.value as AppSettings['theme'])}><option value="classic">{t('SAS.Planet الكلاسيكي الفاتح','SAS.Planet classic light')}</option><option value="dark">{t('داكن','Dark')}</option></select></label><label>{t('اللغة','Language')}<select value={draft.language} onChange={e=>set('language',e.target.value as 'ar'|'en')}><option value="ar">العربية</option><option value="en">English</option></select></label></div>
          <label className="block">{t('خريطة الأساس عند التشغيل','Startup base map')}<select value={draft.defaultSource} onChange={e=>set('defaultSource',e.target.value)}>{sources.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
          <div className="grid sm:grid-cols-2 gap-3">{toggle('wheelZoom','التكبير بعجلة الفأرة','Mouse wheel zoom')}{toggle('animations','تحريك الخريطة بسلاسة','Animate map navigation')}{toggle('showZoomRail','شريط التكبير الجانبي','Side zoom control')}{toggle('showMapTools','شريط المفضلة والتحليل','Favorites & analysis toolbar')}{toggle('showStatusBar','شريط الإحداثيات والحالة','Coordinates & status bar')}{toggle('rememberView','تذكر آخر مشهد عند التشغيل','Restore last map view')}</div>
        </>:tab==='coordinates'?<>
          <label className="block">{t('نظام عرض الإحداثيات','Coordinate display system')}<select value={draft.coordinateSystem} onChange={e=>set('coordinateSystem',e.target.value as AppSettings['coordinateSystem'])}>
            <option value="dms">WGS84 — {t('درجات / دقائق / ثوانٍ','Degrees / minutes / seconds')}</option>
            <option value="decimal">WGS84 — {t('درجات عشرية','Decimal degrees')}</option>
            <option value="utm_wgs84">UTM — WGS84</option>
            <option value="utm_nord_sahara">UTM — Nord Sahara 1959</option>
          </select></label>
          {draft.coordinateSystem==='utm_nord_sahara'&&<>
            <label className="block">{t('منطقة UTM Nord Sahara','UTM Nord Sahara zone')}<select value={draft.nordSaharaZone} onChange={e=>set('nordSaharaZone',Number(e.target.value) as AppSettings['nordSaharaZone'])}>
              <option value={0}>{t('تلقائي حسب الموقع','Automatic by location')}</option>
              {[29,30,31,32].map(zone=><option key={zone} value={zone}>{zone}N — EPSG:{30700+zone}</option>)}
            </select></label>
            <p className="text-xs opacity-75">{t('مثال: المنطقة 31N لوسط الجزائر وبجاية، والمنطقة 32N لشرق الجزائر.','Example: zone 31N for central Algeria and Béjaïa; zone 32N for eastern Algeria.')}</p>
            <p className="text-xs opacity-75">{t('تحويل المرجع المستخدم: EPSG:1253، بدقة تقريبية 44 متراً.','Datum transformation: EPSG:1253, approximate accuracy 44 meters.')}</p>
          </>}
          <p className="text-xs opacity-75">{t('يُطبّق الاختيار على إحداثيات المؤشر في شريط الحالة، ويُحفظ عند إغلاق البرنامج.','Applies to cursor coordinates in the status bar and is remembered after closing the application.')}</p>
          <p className="text-xs opacity-75">{t('هذا إعداد للعرض؛ نظام إحداثيات ملفات التصدير يُحدد من أداة التصدير.','This setting controls display; exported files use the coordinate system specified by the export tool.')}</p>
          {!draft.showStatusBar&&<p className="text-xs">{t('فعّل شريط الإحداثيات والحالة من تبويب العرض لرؤية الإحداثيات.','Enable the coordinates and status bar in the Display tab to see coordinates.')}</p>}
        </>:tab==='terrain'?<>
          <p className="text-xs opacity-75">{t('تُطبق هذه القيم افتراضياً عند فتح استوديو التضاريس. الارتفاعات بالمتر؛ تكبير الشبكة لا يزيد دقة المصدر.','These defaults apply when opening the terrain studio. Elevations are in meters; a denser grid does not improve source accuracy.')}</p>
          <div className="grid sm:grid-cols-2 gap-4"><label>{t('مصدر الارتفاعات','Elevation source')}<select value={draft.terrainSource} onChange={e=>set('terrainSource',e.target.value as 'terrain'|'srtm')}><option value="terrain">Mapzen Terrain Tiles</option><option value="srtm">SRTM HGT</option></select></label><label>{t('حجم شبكة التحليل','Analysis grid size')}<select value={draft.terrainResolution} onChange={e=>set('terrainResolution',Number(e.target.value))}>{[128,256,512].map(n=><option key={n} value={n}>{n} × {n}</option>)}</select></label><label>{t('فاصل خطوط التسوية (م)','Contour interval (m)')}<select value={draft.contourInterval} onChange={e=>set('contourInterval',Number(e.target.value))}>{[5,10,20,25,50,100,250].map(n=><option key={n} value={n}>{n}</option>)}</select></label><label>{t('سمت الإضاءة (درجة)','Light azimuth (degrees)')}<input type="number" min={0} max={360} value={draft.azimuth} onChange={e=>set('azimuth',Number(e.target.value))}/></label><label>{t('ارتفاع الشمس (درجة)','Sun altitude (degrees)')}<input type="number" min={1} max={90} value={draft.altitude} onChange={e=>set('altitude',Number(e.target.value))}/></label><label>{t('معامل المبالغة الرأسية','Vertical exaggeration')}<input type="number" min={0.1} max={10} step={0.1} value={draft.zFactor} onChange={e=>set('zFactor',Number(e.target.value))}/></label></div>
          <p className="text-xs opacity-75">{t('المعامل 1 هو الافتراضي للبيانات المترية. خرائط التحليل تُحسب من الارتفاعات الفعلية؛ المبالغة الرأسية تطبق على الظلال فقط.','Use factor 1 for meter elevations. Terrain analysis uses true elevations; exaggeration applies only to hillshade.')}</p>
        </>:<>
          <p className="text-xs opacity-75">{t('أضف مصادر خرائط خاصة بك (XYZ / TMS / WMS) مثل أورثوفوتو الجزائر أو Sentinel. تظهر في قائمة خريطة الأساس. تُحفظ في هذا المتصفح ولا تُخزَّن في الكاش.','Add your own map sources (XYZ / TMS / WMS) such as Algeria orthophoto or Sentinel. They appear in the base-map list. Saved in this browser; not written to the tile cache.')}</p>
          <div className="grid sm:grid-cols-2 gap-3">
            <label>{t('الاسم','Name')}<input value={csName} onChange={e=>setCsName(e.target.value)} placeholder={t('مثال: أورثوفوتو الجزائر','e.g. Algeria orthophoto')}/></label>
            <label>{t('النوع','Type')}<select value={csKind} onChange={e=>setCsKind(e.target.value as any)}><option value="xyz">XYZ</option><option value="tms">TMS</option><option value="wms">WMS</option></select></label>
            <label className="sm:col-span-2" dir="ltr">{csKind==='wms'?t('رابط خدمة WMS','WMS service URL'):t('قالب الرابط (XYZ/TMS)','URL template (XYZ/TMS)')}<input value={csUrl} onChange={e=>setCsUrl(e.target.value)} placeholder={csKind==='wms'?'https://host/wms?':'https://host/{z}/{x}/{y}.png'}/></label>
            {csKind==='wms'&&<label className="sm:col-span-2">{t('اسم الطبقة (WMS)','WMS layer name')}<input value={csLayers} onChange={e=>setCsLayers(e.target.value)} placeholder="ortho_2020"/></label>}
            <label>{t('الفئة','Category')}<select value={csCategory} onChange={e=>setCsCategory(e.target.value as MapSource['category'])}>{['Satellite','Hybrid','Map','Topographic','Terrain'].map(c=><option key={c} value={c}>{c}</option>)}</select></label>
            <label>{t('أقصى تقريب','Max zoom')}<input type="number" min={1} max={23} value={csZoom} onChange={e=>setCsZoom(Number(e.target.value))}/></label>
          </div>
          {csError&&<p className="text-xs text-red-600">{csError}</p>}
          <button className="desktop-button primary" onClick={addCustomSource}><Plus size={14}/>{t('إضافة المصدر','Add source')}</button>
          <div className="space-y-1">
            {customSources.length===0?<p className="text-xs opacity-60">{t('لا مصادر مخصّصة بعد.','No custom sources yet.')}</p>:customSources.map(s=>(
              <div key={s.id} className="flex items-center justify-between gap-2 text-xs border rounded px-2 py-1.5">
                <span className="flex items-center gap-2 min-w-0"><Layers size={13} className="shrink-0"/><span className="truncate"><b>{s.name}</b> · {s.kind?.toUpperCase()} · {s.category}</span></span>
                <button className="p-1 rounded hover:bg-red-50 text-red-600 shrink-0" title={t('حذف','Delete')} onClick={()=>onCustomSourcesChange?.(customSources.filter(x=>x.id!==s.id))}><Trash2 size={14}/></button>
              </div>
            ))}
          </div>
        </>}
      </div>
      <div className="desktop-dialog-footer"><button className="desktop-button" onClick={()=>setDraft({...DEFAULT_SETTINGS})}><RotateCcw size={14}/>{t('استعادة الافتراضي','Restore defaults')}</button><div className="flex gap-2"><button className="desktop-button" onClick={onClose}>{t('إلغاء','Cancel')}</button><button className="desktop-button primary" onClick={()=>onSave(normalizeSettings(draft))}><Check size={15}/>{t('حفظ وتطبيق','Save & apply')}</button></div></div>
    </section>
  </DraggableWindow>;
}
