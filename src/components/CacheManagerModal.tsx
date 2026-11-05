import React,{useState,useEffect,useCallback} from 'react';
import {X,HardDrive,WifiOff,Wifi,DownloadCloud,RefreshCw,FolderOpen,Copy,Trash2} from 'lucide-react';
import {MapSource} from '../types';
import {DraggableWindow} from './DraggableWindow';
import {getBrowserCacheStats,clearBrowserTileCache,cacheCurrentViewportTiles} from '../utils/tileCache';

interface CacheManagerModalProps {
  isOpen:boolean;onClose:()=>void;lang:'ar'|'en';isOfflineMode:boolean;
  onToggleOfflineMode:(enabled:boolean)=>void;currentSource?:MapSource;onCacheUpdated?:()=>void;
}
interface DiskStats {total_tiles:number;total_size_mb:number;base_dir?:string;layers?:{folder:string;tiles:number;size_mb:number}[];location?:{warning?:string;source?:string};}
export const CacheManagerModal:React.FC<CacheManagerModalProps>=({isOpen,onClose,lang,isOfflineMode,onToggleOfflineMode,currentSource,onCacheUpdated})=>{
  const ar=lang==='ar';
  const [stats,setStats]=useState<DiskStats>({total_tiles:0,total_size_mb:0});
  const [legacy,setLegacy]=useState({count:0,estimatedSizeMb:0});
  const desktop=(window as any).saharaDesktop;
  const [selectedPath,setSelectedPath]=useState(''),[selecting,setSelecting]=useState(false),[copying,setCopying]=useState(false);
  const [loading,setLoading]=useState(false),[saving,setSaving]=useState(false);
  const [progress,setProgress]=useState({done:0,total:0}),[message,setMessage]=useState('');
  const refresh=useCallback(async()=>{
    setLoading(true);
    try{const response=await fetch('/api/cache/stats');if(!response.ok){const d=await response.json();throw Error(d.error||'Cache unavailable');}setStats(await response.json());setLegacy(await getBrowserCacheStats());}
    catch{setMessage(ar?'تعذر قراءة مجلد الكاش.':'Unable to read the cache folder.');}
    finally{setLoading(false);}
  },[ar]);
  useEffect(()=>{if(isOpen){setMessage('');void refresh();}},[isOpen,refresh]);
  const saveView=async()=>{
    const map=(window as any).__SAS_MAP;if(!map||!currentSource)return;
    setSaving(true);setMessage('');setProgress({done:0,total:0});
    try{
      const result=await cacheCurrentViewportTiles(map,currentSource,(done,total)=>setProgress({done,total}));
      setMessage(ar?'حُفظت '+result.saved+' بلاطة في cache_gmt، وتعذر حفظ '+result.failed+'.':'Saved '+result.saved+' tiles to cache_gmt; '+result.failed+' failed.');
      await refresh();onCacheUpdated?.();
    }catch{setMessage(ar?'تعذر حفظ المشهد الحالي.':'Unable to save the current view.');}
    finally{setSaving(false);}
  };
  const openFolder=async()=>{
    try{const result=desktop?await desktop.openCache():await (await fetch('/api/cache/open',{method:'POST'})).json();if(!result.success)throw Error(result.error||result.path);setMessage(ar?'فُتح مجلد الكاش.':'Cache folder opened.');}
    catch(e:any){setMessage((ar?'تعذر فتح المجلد. المسار: ':'Cannot open folder. Path: ')+(stats.base_dir||e.message));}
  };
  const applyPath=async(value:string)=>{
    setSelecting(true);setMessage('');
    try{const response=await fetch('/api/cache/location',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:value})});const result=await response.json();if(!response.ok)throw Error(result.error);setSelectedPath('');await refresh();onCacheUpdated?.();setMessage(ar?'تم اعتماد مجلد الكاش. أعد عرض المنطقة بمصدر الخرائط ومستوى التكبير المحفوظين.':'Cache folder selected. Display the saved source and zoom level.');}
    catch(e:any){setMessage(e.message);}finally{setSelecting(false);}
  };
  const chooseFolder=async()=>{try{if(!desktop){setSelectedPath(stats.base_dir||'');return;}const folder=await desktop.chooseCache();if(folder)await applyPath(folder);}catch(e:any){setMessage(e.message);}};
  const copyForTransfer=async()=>{if(!desktop){setMessage(ar?'انسخ مجلد cache_gmt المعروض أعلاه بالكامل إلى جانب البرنامج في الجهاز الآخر.':'Copy the whole cache_gmt folder beside the application on the other computer.');return;}setCopying(true);setMessage(ar?'جارٍ نسخ الكاش؛ قد تستغرق الخرائط الكبيرة وقتاً.':'Copying cached maps; large caches may take time.');try{const result=await desktop.copyCache();if(result.cancelled){setMessage('');return;}setMessage((ar?'تم نسخ الكاش إلى: ':'Cache copied to: ')+result.path);}catch(e:any){setMessage(e.message);}finally{setCopying(false);}};
  const copyPath=async()=>{try{await navigator.clipboard.writeText(stats.base_dir||'');setMessage(ar?'تم نسخ مسار الكاش.':'Cache folder path copied.');}catch{setMessage(stats.base_dir||'cache_gmt');}};
  const clearLegacy=async()=>{
    if(!window.confirm(ar?'حذف كاش المتصفح القديم فقط؟ ستبقى ملفات cache_gmt.':'Clear the old browser cache? Files in cache_gmt will be kept.'))return;
    await clearBrowserTileCache();setLegacy(await getBrowserCacheStats());onCacheUpdated?.();
  };
  if(!isOpen)return null;
  const button='px-3 py-2 rounded border border-slate-600 bg-slate-800 hover:bg-slate-700 text-slate-100 flex items-center justify-center gap-2 disabled:opacity-40';
  return <DraggableWindow>
    <section role="dialog" aria-modal="true" aria-labelledby="cache-title" className="w-full max-w-xl bg-slate-900 border border-slate-600 rounded-lg shadow-2xl text-slate-200 max-h-[92vh] flex flex-col overflow-hidden">
      <header className="flex items-center justify-between p-4 border-b border-slate-700 bg-slate-950">
        <h2 id="cache-title" className="font-bold flex items-center gap-2"><HardDrive size={19}/>{ar?'كاش الخرائط — cache_gmt':'Map cache — cache_gmt'}</h2>
        <button onClick={onClose} aria-label={ar?'إغلاق':'Close'}><X size={20}/></button>
      </header>
      <div className="p-4 space-y-4 overflow-y-auto text-xs">
        {message&&<p role="status" className="p-3 bg-blue-950 text-blue-100 rounded border border-blue-700">{message}</p>}
        <p className="leading-relaxed text-slate-300">{ar?'تُحفظ الخرائط كملفات صور في مجلد مستقل لكل مصدر. عند نقل البرنامج انسخ مجلده كاملاً بما فيه cache_gmt.':'Viewed and downloaded maps are saved automatically as image files, with a separate folder for each source, like SAS.Planet.'}</p>
        <div className="p-3 rounded bg-slate-950 border border-slate-700 space-y-3">
          <label htmlFor="cache-path" className="font-semibold block">{ar?'مجلد الكاش بجانب البرنامج':'Cache folder beside the application'}</label>
          <input id="cache-path" aria-label={ar?'مسار مجلد الكاش':'Cache folder path'} readOnly dir="ltr" value={stats.base_dir||(ar?'لم يُقرأ المسار بعد':'Path not available yet')} className="w-full p-2 rounded bg-slate-900 border border-slate-600 text-slate-100 font-mono text-xs"/>
          <div className="flex gap-2"><button className={button+' flex-1'} onClick={openFolder}><FolderOpen size={16}/>{ar?'فتح مجلد الكاش':'Open cache folder'}</button><button className={button} onClick={copyPath}><Copy size={15}/>{ar?'نسخ المسار':'Copy path'}</button></div>
          <div className="flex gap-2 flex-wrap"><button className={button+' flex-1'} disabled={selecting||saving} onClick={()=>void chooseFolder()}><FolderOpen size={15}/>{ar?'اختيار كاش موجود':'Choose existing cache'}</button><button className={button+' flex-1'} disabled={copying||!stats.base_dir} onClick={()=>void copyForTransfer()}><Copy size={15}/>{copying?(ar?'جارٍ النسخ…':'Copying…'):(ar?'نسخ الكاش للنقل':'Copy cache for transfer')}</button></div>
          {selectedPath&&<div className="space-y-2"><input aria-label={ar?'مسار الكاش الموجود':'Existing cache path'} dir="ltr" value={selectedPath} onChange={e=>setSelectedPath(e.target.value)} className="w-full border p-2 text-xs"/><button className={button} disabled={selecting} onClick={()=>void applyPath(selectedPath)}>{ar?'اعتماد المسار':'Use this folder'}</button></div>}
          {stats.location?.warning&&<p className="p-2 border border-amber-500">{ar?'مسار الكاش السابق غير موجود في هذا الجهاز؛ يُستخدم الآن المجلد بجانب البرنامج. اختر مكان الخرائط إن نقلتها إلى مسار آخر.':stats.location.warning}</p>}
          {stats.base_dir&&stats.total_tiles===0&&!loading&&<p className="p-2 border border-amber-500">{ar?'هذا المجلد لا يحتوي خرائط بعد. ملف توزيع البرنامج لا يضم الكاش الشخصي؛ انسخ cache_gmt من الجهاز السابق أو اختر مجلده هنا.':'This cache is empty. The clean application ZIP does not contain personal maps. Copy cache_gmt from the previous computer or choose its folder here.'}</p>}
          <pre dir="ltr" className="text-slate-300 text-[11px] leading-relaxed overflow-x-auto">{'cache_gmt/\n  sat/z15/12821/16994.jpg\n  Both/\n  ArcGIS.Imagery/\n  land/\n  osmmapMapnik/'}</pre>
          <p className="text-slate-400 leading-relaxed">{ar?'يمكن نسخ مجلدات المصادر من cache_gmt في SAS.Planet إلى هذا المجلد. تتم قراءة البلاطات الموجودة عند المصدر ومستوى التكبير نفسه.':'You can copy source folders from SAS.Planet cache_gmt into this folder. Tiles are read for the matching source and zoom level.'}</p>
        </div>
        <div className="grid grid-cols-2 gap-3"><div className="p-3 bg-slate-950 rounded border border-slate-700"><span>{ar?'البلاطات المحفوظة':'Saved tiles'}</span><strong className="block mt-1 text-xl font-mono text-cyan-300">{stats.total_tiles.toLocaleString()}</strong></div><div className="p-3 bg-slate-950 rounded border border-slate-700"><span>{ar?'الحجم على القرص':'Disk usage'}</span><strong className="block mt-1 text-xl font-mono text-amber-300">{stats.total_size_mb} MB</strong></div></div>
        {stats.layers&&<div className="max-h-36 overflow-auto rounded border border-slate-700"><table className="w-full text-xs"><thead className="bg-slate-950"><tr><th className="p-2 text-start">{ar?'مجلد المصدر':'Source folder'}</th><th>{ar?'البلاطات':'Tiles'}</th><th>MB</th></tr></thead><tbody>{stats.layers.map(layer=><tr key={layer.folder} className="border-t border-slate-700"><td dir="ltr" className="p-2 font-mono">{layer.folder}</td><td className="text-center">{layer.tiles.toLocaleString()}</td><td className="text-center">{layer.size_mb}</td></tr>)}</tbody></table></div>}
        <div className="p-3 bg-slate-950 rounded border border-slate-700 space-y-2"><div className="flex items-center justify-between gap-3"><span className="flex items-center gap-2 font-semibold">{isOfflineMode?<WifiOff size={18}/>:<Wifi size={18}/>} {ar?'وضع عدم الاتصال':'Offline mode'}</span><button role="switch" aria-checked={isOfflineMode} aria-label={ar?'وضع عدم الاتصال':'Offline mode'} className={button} onClick={()=>{onToggleOfflineMode(!isOfflineMode);}}>{isOfflineMode?(ar?'مفعّل':'On'):(ar?'غير مفعّل':'Off')}</button></div><p className="text-slate-400 leading-relaxed">{ar?'في وضع عدم الاتصال تُقرأ الخرائط من cache_gmt، ولا تُنزّل البلاطات الناقصة من الإنترنت.':'Offline mode reads maps from cache_gmt and does not download missing tiles.'}</p></div>
        <button className={button+' w-full bg-blue-900'} onClick={saveView} disabled={saving||isOfflineMode}><DownloadCloud size={17}/>{saving?(ar?'جارٍ الحفظ…':'Saving…'):(ar?'حفظ المشهد الحالي في cache_gmt':'Save current view to cache_gmt')}</button>
        <p className="text-[11px] text-slate-400">{ar?'يشمل الحفظ خريطة المصدر الحالية عند مستوى التكبير الظاهر.':'Saves the current map source at the displayed zoom level.'}</p>
        {saving&&<div role="status" className="font-mono text-center">{progress.done} / {progress.total}</div>}
        {legacy.count>0&&<div className="p-3 border border-slate-700 rounded space-y-2"><p>{ar?'كاش متصفح من النسخة السابقة: ':'Old browser cache: '}{legacy.count} {ar?'بلاطة. تُنسخ البلاطة إلى cache_gmt عند استعادتها منه.':'tiles. Recovered tiles are copied to cache_gmt.'}</p><button onClick={clearLegacy} className={button}><Trash2 size={14}/>{ar?'حذف كاش المتصفح القديم فقط':'Clear old browser cache only'}</button></div>}
      </div>
      <footer className="p-3 flex justify-between border-t border-slate-700"><button className={button} disabled={loading} onClick={()=>{void refresh();onCacheUpdated?.();}}><RefreshCw size={14} className={loading?'animate-spin':''}/>{ar?'تحديث':'Refresh'}</button><button onClick={onClose} className={button}>{ar?'إغلاق':'Close'}</button></footer>
    </section>
  </DraggableWindow>;
};
