import {CRS_OPTIONS,studioRequest} from './AdvancedGisWorkbench';
import React, {useEffect,useRef,useState} from 'react';
import {X, Mountain, Download, Play, RefreshCw, Map, Layers, CheckCircle2, AlertCircle} from 'lucide-react';
import {BoundingBox} from '../types';
import {AppSettings} from '../utils/settings';
export interface TerrainOverlay {url:string; bbox:[number,number,number,number];name:string;}
interface Metadata {source:string;source_pixel_size_m:number;rows:number;cols:number;crs:string;interval:number;contour_lines:number;nodata_samples:number;bbox:[number,number,number,number];ground_cell_size_m:{east_west:number;north_south:number};statistics:Record<string,{min:number|null;max:number|null;mean:number|null;valid_cells:number}>;attribution:string;}
interface Result {download_url:string;size_mb:number;previews:Record<string,string>;metadata:Metadata;}
const PRODUCTS:Record<string,[string,string,string]>={relief:['خريطة طبوغرافية ملونة','Topographic relief','m'],dem:['نموذج الارتفاع الرقمي','Digital elevation model','m'],slope:['الانحدار — Horn','Slope — Horn','°'],aspect:['اتجاه السفوح','Aspect','°'],hillshade:['ظلال التضاريس','Hillshade','0–255'],tpi:['الموضع الطبوغرافي TPI','Topographic position (TPI)','m'],roughness:['خشونة السطح','Surface roughness','m'],filled_dem:['ارتفاعات بعد ملء المنخفضات','Depression-filled DEM','m'],fill_depth:['عمق ملء المنخفضات','Depression fill depth','m'],flow_direction:['اتجاه الجريان D8','D8 flow direction','D8'],flow_accumulation:['تراكم الجريان','Flow accumulation','cells']};
export function TerrainWorkbench({bbox,settings,isOfflineMode,onClose,onApply}:{bbox:BoundingBox;settings:AppSettings;isOfflineMode:boolean;onClose:()=>void;onApply:(overlay:TerrainOverlay)=>void}) {
  const ar=settings.language==='ar';const t=(a:string,e:string)=>ar?a:e;
  const [resolution,setResolution]=useState(settings.terrainResolution);const [interval,setInterval]=useState(settings.contourInterval);const [source,setSource]=useState<string>(settings.terrainSource);
  const [azimuth,setAzimuth]=useState(settings.azimuth);const [altitude,setAltitude]=useState(settings.altitude);const [zFactor,setZFactor]=useState(settings.zFactor);const [hydrology,setHydrology]=useState(true);const [aboveSea,setAboveSea]=useState(true);
  const [targetCrs,setTargetCrs]=useState(settings.coordinateSystem==='utm_nord_sahara'?(settings.nordSaharaZone?'EPSG:'+String(30700+settings.nordSaharaZone):'utm_ns_auto'):'utm_wgs84_auto');
  const [localDems,setLocalDems]=useState<any[]>([]);useEffect(()=>{studioRequest('dem_list',{}).then(d=>setLocalDems(d.dems)).catch(()=>{});},[]);
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [result,setResult]=useState<Result|null>(null);const [layer,setLayer]=useState('relief');const [tab,setTab]=useState('preview');const abort=useRef<AbortController|null>(null);
  useEffect(()=>()=>abort.current?.abort(),[]);
  const generate=async()=>{setBusy(true);setError('');const controller=new AbortController();abort.current=controller;
    try{const response=await fetch('/api/python/topo/arcgis',{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({bbox:[bbox.min_lon,bbox.min_lat,bbox.max_lon,bbox.max_lat],source,target_crs:targetCrs,offline:isOfflineMode,resolution,interval,azimuth,altitude,z_factor:zFactor,hydrology,above_sea_only:aboveSea})});const data=await response.json();if(!response.ok||!data.success)throw new Error(data.error||'Terrain analysis failed');setResult(data.result);setLayer('relief');}
    catch(e:any){if(e.name!=='AbortError')setError(e.message);}finally{setBusy(false);}};
  const meta=result?.metadata;const product=PRODUCTS[layer];
  return <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-3" onKeyDown={e=>{if(e.key==='Escape')onClose();}}>
    <section className="desktop-dialog terrain-workbench" role="dialog" aria-modal="true" aria-labelledby="terrain-workbench-title">
      <div className="desktop-dialog-title"><h2 id="terrain-workbench-title"><Mountain size={18}/>{t('تحليل التضاريس وتصدير خرائط ArcGIS','Terrain analysis & ArcGIS export')}</h2><button aria-label={t('إغلاق','Close')} onClick={onClose}><X size={18}/></button></div>
      <div className="terrain-workbench-body">
        <aside className="terrain-options">
          <div className="text-[11px] opacity-70 font-mono" dir="ltr">{bbox.min_lon.toFixed(4)}, {bbox.min_lat.toFixed(4)}<br/>→ {bbox.max_lon.toFixed(4)}, {bbox.max_lat.toFixed(4)}</div>
          <fieldset disabled={busy} className="space-y-3 disabled:opacity-50">
            <label>{t('مصدر الارتفاعات','Elevation source')}<select value={source} onChange={e=>setSource(e.target.value as 'terrain'|'srtm')}><option value="terrain">Mapzen Terrain Tiles</option><option value="srtm">SRTM HGT</option>{localDems.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
            <label>{t('إسقاط ملفات ArcGIS','ArcGIS output CRS')}<select value={targetCrs} onChange={e=>setTargetCrs(e.target.value)}>{CRS_OPTIONS.map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label>
            <label>{t('دقة شبكة المعالجة','Processing grid')}<select value={resolution} onChange={e=>setResolution(Number(e.target.value))}>{[64,128,256,512].map(n=><option key={n} value={n}>{n} × {n} {t('كحد أقصى','maximum')}</option>)}</select></label>
            <label>{t('الفاصل الكنتوري (متر)','Contour interval (m)')}<select value={interval} onChange={e=>setInterval(Number(e.target.value))}>{[5,10,20,25,50,100,250].map(n=><option key={n} value={n}>{n}</option>)}</select></label>
            <div className="grid grid-cols-2 gap-2"><label>{t('سمت الشمس','Azimuth')}<input type="number" min={0} max={360} value={azimuth} onChange={e=>setAzimuth(Number(e.target.value))}/></label><label>{t('ارتفاع الشمس','Altitude')}<input type="number" min={1} max={90} value={altitude} onChange={e=>setAltitude(Number(e.target.value))}/></label></div>
            <label>{t('المبالغة الرأسية للظلال','Hillshade exaggeration')}<input type="number" min={0.1} max={10} step={0.1} value={zFactor} onChange={e=>setZFactor(Number(e.target.value))}/></label>
            <label className="settings-check"><input type="checkbox" checked={hydrology} onChange={e=>setHydrology(e.target.checked)}/>{t('تحليل الجريان وملء المنخفضات','Drainage & depression filling')}</label>
            <label className="settings-check"><input type="checkbox" checked={aboveSea} onChange={e=>setAboveSea(e.target.checked)}/>{t('خطوط كنتور فوق مستوى البحر فقط','Contours above sea level only')}</label>
            <button className="desktop-button primary w-full" onClick={()=>void generate()}>{busy?<RefreshCw size={16} className="animate-spin"/>:<Play size={16}/>} {t('تحليل وتجهيز حزمة ArcGIS','Analyze & prepare ArcGIS package')}</button>
          </fieldset>
          <p className="text-[11px] opacity-75 leading-relaxed">{t('حجم الشبكة لا يزيد دقة المصدر. تصدير WGS84 مع ارتفاعات بالمتر. استعمل منطقة أصغر للحصول على تفاصيل أدق.','Grid size does not increase source accuracy. Export uses WGS84 with elevations in meters. Select a smaller region for more detail.')}</p>
          {isOfflineMode&&<p className="text-xs">{t('دون اتصال: بيانات مخزنة أو SRTM فقط.','Offline: cached terrain or local SRTM only.')}</p>}
        </aside>
        <div className="terrain-results">
          <div className="desktop-tabs">{[['preview','معاينة الطبقات','Layer preview'],['stats','النتائج والخوارزميات','Results & algorithms'],['export','التصدير إلى ArcGIS','ArcGIS export']].map(([id,a,e])=><button key={id} aria-pressed={tab===id} onClick={()=>setTab(id)}>{t(a,e)}</button>)}</div>
          {busy&&<div className="p-3 flex items-center gap-2 text-sm" role="status"><RefreshCw className="animate-spin" size={16}/>{t('جارٍ قراءة الارتفاعات وحساب التحليل وإعداد الملفات…','Reading elevations, computing terrain and preparing files…')}</div>}
          {error&&<p role="alert" className="m-4 p-3 border border-red-400 text-red-700 rounded flex gap-2"><AlertCircle size={18}/>{error}</p>}
          {!result&&!busy?<div className="terrain-empty"><Mountain size={46} strokeWidth={1}/><h3>{t('من بيانات الارتفاع إلى خريطة طبوغرافية','From elevation data to a topographic map')}</h3><p>{t('تحليل الانحدار واتجاه السفوح والظلال وخشونة التضاريس والجريان، ثم تصدير حزمة قابلة للاستخدام في ArcGIS.','Analyze slope, aspect, hillshade, roughness and drainage, then export a package for ArcGIS.')}</p><div className="flex flex-wrap gap-2 justify-center"><span>GeoTIFF</span><span>Shapefile Z</span><span>ESRI ASCII</span><span>GeoJSON</span></div></div>:null}
          {result&&meta&&<div className="p-4 space-y-3">
            <div className="terrain-result-summary"><CheckCircle2 size={17}/><span>{meta.rows} × {meta.cols} · {meta.contour_lines} {t('خط تسوية','contour lines')} · {meta.crs}</span></div>
            {tab==='preview'&&<>
              <div className="flex gap-2 items-center"><Layers size={16}/><select aria-label={t('طبقة المعاينة','Preview layer')} className="!mt-0" value={layer} onChange={e=>setLayer(e.target.value)}>{Object.keys(result.previews).map(k=><option key={k} value={k}>{t(PRODUCTS[k][0],PRODUCTS[k][1])}</option>)}</select><button className="desktop-button shrink-0" onClick={()=>{onApply({url:result.previews[layer],bbox:meta.bbox,name:t(product[0],product[1])});onClose();}}><Map size={15}/>{t('عرض على الخريطة','Show on map')}</button></div>
              <div className="terrain-preview"><img src={result.previews[layer]} alt={t(product[0],product[1])}/></div>
              <p className="text-xs opacity-75">{layer==='slope'?t('أخضر: أقل من 5°، أصفر: 15–30°، برتقالي: 30–45°، أحمر: أكثر من 45°.','Green: under 5°, yellow: 15–30°, orange: 30–45°, red: over 45°.'):layer==='aspect'?t('اتجاه الانحدار من الشمال مع عقارب الساعة؛ الرمادي = سطح مستوٍ.','Downhill bearing clockwise from north; gray = flat.'):layer==='flow_accumulation'?t('الأزرق الداكن يدل على تجمع خلايا أكثر؛ هذه خريطة جريان تضاريسي وليست توقعاً للفيضانات.','Darker blue indicates more contributing cells; this is terrain drainage, not a flood forecast.'):t('المعاينة مرتبطة بالحدود الجغرافية الفعلية للراستر.','Preview is registered to the raster geographic bounds.')}</p>
            </>}
            {tab==='stats'&&<>
              <p className="text-xs">{meta.source} · {t('حجم بكسل المصدر التقريبي','Approx. source pixel size')}: {meta.source_pixel_size_m} m<br/>{t('تباعد شبكة الناتج','Output ground spacing')}: {meta.ground_cell_size_m.east_west.toFixed(1)} × {meta.ground_cell_size_m.north_south.toFixed(1)} m · NoData: {meta.nodata_samples}</p>
              <div className="overflow-auto"><table className="terrain-stats"><thead><tr><th>{t('الطبقة','Layer')}</th><th>{t('الأدنى','Min')}</th><th>{t('الأعلى','Max')}</th><th>{t('المتوسط','Mean')}</th></tr></thead><tbody>{Object.entries(meta.statistics).map(([k,v])=><tr key={k}><td>{t(PRODUCTS[k][0],PRODUCTS[k][1])} ({PRODUCTS[k][2]})</td><td>{v.min?.toFixed(2)??'—'}</td><td>{v.max?.toFixed(2)??'—'}</td><td>{k==='aspect'||k==='flow_direction'?'—':v.mean?.toFixed(2)??'—'}</td></tr>)}</tbody></table></div>
              <p className="text-xs leading-relaxed opacity-80">Horn 3×3 · TPI 3×3 · Priority-Flood · D8<br/>{t('حساب المشتقات بمسافات أرضية مترية حسب خط العرض. تُستبعد الحواف والجوار الناقص من المشتقات. تراكم الجريان هو عدد الخلايا المساهمة دون الخلية الحالية، والمنخفضات المملوءة محفوظة في طبقة منفصلة.','Derivatives use latitude-dependent ground distances in meters; borders and incomplete neighborhoods are NoData. Accumulation counts upstream cells excluding the current cell. Filled elevations are kept in a separate raster.')}</p>
            </>}
            {tab==='export'&&<>
              <div className="terrain-export-card"><Download size={28}/><h3>{t('حزمة خرائط ArcGIS جاهزة','ArcGIS map package ready')}</h3><p>GeoTIFF Float32 · PolyLineZ SHP · ASC · GeoJSON · {meta.crs}</p><a href={result.download_url} download className="desktop-button primary">{t('تنزيل حزمة ArcGIS','Download ArcGIS package')} (.ZIP, {result.size_mb} MB)</a></div>
              <ol className="list-decimal ps-5 text-sm space-y-2"><li>{t('فك ضغط الحزمة في مجلد واحد.','Extract the ZIP into one folder.')}</li><li>{t('في ArcGIS استخدم Add Data وأضف relief.tif و contours.shp.','In ArcGIS, use Add Data and load relief.tif and contours.shp.')}</li><li>{t('أضف dem.tif و slope.tif وبقية الطبقات للتحليل.','Add dem.tif, slope.tif and the other layers for analysis.')}</li><li>{t('الراستر وملف SHP بالإسقاط المختار، وGeoJSON بنظام WGS84.','Rasters and SHP use the selected output CRS; GeoJSON uses WGS84.')}</li></ol>
              <p className="text-xs opacity-75">{t('تتضمن الحزمة دليل استخدام وملف بيانات وصفية وسكربت تحميل اختياري لـ ArcGIS Pro.','Includes usage instructions, metadata and an optional ArcGIS Pro loader script.')}</p>
            </>}
            <p className="text-[10px] opacity-60">{meta.attribution}</p>
          </div>}
        </div>
      </div>
      <div className="desktop-dialog-footer"><span className="text-xs opacity-70">{t('تحليل بيانات ارتفاع حقيقية','Real elevation data analysis')}</span><button className="desktop-button" onClick={onClose}>{t('إغلاق','Close')}</button></div>
    </section>
  </div>;
}
