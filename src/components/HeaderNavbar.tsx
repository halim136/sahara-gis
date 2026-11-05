import React, {useEffect,useRef,useState} from 'react';
import {MousePointer2, SquareDashed, Ruler, Crosshair, Search, MapPin, Layers, Star, Navigation, Settings, Download, Mountain, ChartNoAxesCombined, HardDrive, Terminal, ChevronDown, Globe, Plus, Minus, Grid3X3, Trash2, Pentagon, HelpCircle, WifiOff, Columns2} from 'lucide-react';
import {MapSource,SelectionMode} from '../types';
interface HeaderNavbarProps {
  currentSource: MapSource;
  sources: MapSource[];
  overlays: MapSource[];
  activeOverlays: Set<string>;
  selectionMode: SelectionMode;
  hasSelection: boolean;
  onSelectSource: (source: MapSource) => void;
  onToggleOverlay: (overlayId: string) => void;
  onSetSelectionMode: (mode: SelectionMode) => void;
  onClearSelection: () => void;
  onOpenSelectionOps: () => void;
  onOpenPythonStudio: () => void;
  onOpenMarksManager: () => void;
  onOpenTopographyStudio: () => void;
  onOpenSpatialAnalysis: () => void;
  onOpenGpsSimulator: () => void;
  onOpenElevation: () => void;
  onOpenGoTo: () => void;
  onOpenCacheManager: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  lang: 'ar' | 'en';
  onToggleLang: () => void;
  isOfflineMode?: boolean;
  onOpenSettings: () => void;
  onOpenTerrainAnalysis: () => void;
  onToggleMapTools: () => void;
  showMapTools: boolean;
  extraTools?: React.ReactNode;
  compareSource?: MapSource | null;
  onCompareSource?: (source: MapSource | null) => void;
}


export const HeaderNavbar: React.FC<HeaderNavbarProps> = (p) => {
  const ar=p.lang==='ar'; const t=(a:string,e:string)=>ar?a:e;
  const [open,setOpen]=useState<string|null>(null); const [search,setSearch]=useState(''); const [searchError,setSearchError]=useState('');
  const root=useRef<HTMLElement>(null);
  useEffect(()=>{const close=(e:MouseEvent)=>{if(!root.current?.contains(e.target as Node))setOpen(null);}; const key=(e:KeyboardEvent)=>{if(e.key==='Escape')setOpen(null);}; document.addEventListener('mousedown',close);document.addEventListener('keydown',key);return()=>{document.removeEventListener('mousedown',close);document.removeEventListener('keydown',key);};},[]);
  const action=(fn:()=>void)=>()=>{setOpen(null);fn();};
  const item=(label:string,Icon:React.ElementType,fn:()=>void,disabled=false,checked?:boolean)=><button key={label} role="menuitem" disabled={disabled} className="desktop-menu-item" onClick={action(fn)}><Icon size={15}/><span>{label}</span>{checked!==undefined&&<span className="ms-auto">{checked?'✓':''}</span>}</button>;
  const menu=(id:string,label:string,content:React.ReactNode)=><div className="desktop-menu-holder"><button className="desktop-menu-label" aria-haspopup="menu" aria-expanded={open===id} onClick={()=>setOpen(open===id?null:id)}>{label}</button>{open===id&&<div role="menu" className="desktop-menu">{content}</div>}</div>;
  const tool=(label:string,Icon:React.ElementType,fn:()=>void,active=false,disabled=false,asset?:string)=><button className="desktop-tool" title={label} aria-label={label} aria-pressed={active} disabled={disabled} onClick={fn}>{asset?<img src={'/assets/sasplanet/'+asset} alt=""/>:<Icon size={23}/>}</button>;
  return <header ref={root} className="desktop-header">
    <div className="desktop-app-title"><img src="/assets/branding/sahara-gis.png" alt=""/><span>Sahara GIS <span className="opacity-65">— صحارى GIS</span></span><span className="ms-auto flex items-center gap-3">{p.isOfflineMode&&<span className="flex gap-1 items-center"><WifiOff size={12}/>{t('دون اتصال','Offline')}</span>}<button onClick={p.onToggleLang}>{ar?'English':'العربية'}</button></span></div>
    <div className="desktop-menu-row">
      <nav aria-label={t('القائمة الرئيسية','Main menu')} className="desktop-menubar">
        {menu('operations',t('عمليات','Operations'),<>{item(t('معالجة التحديد / استيراد ملف (KML·GPX·SML·DB3)','Process selection / import file (KML·GPX·SML·DB3)'),Download,p.onOpenSelectionOps,false)}{item(t('استوديو التضاريس و ArcGIS','Terrain & ArcGIS export'),Mountain,p.onOpenTerrainAnalysis)}{item(t('إدارة التخزين','Cache manager'),HardDrive,p.onOpenCacheManager)}</>)}
        {menu('view',t('عرض','View'),<>{item(t('شريط الأدوات الإضافي','Extra toolbar'),Layers,p.onToggleMapTools,false,p.showMapTools)}{item(t('تكبير','Zoom in'),Plus,p.onZoomIn)}{item(t('تصغير','Zoom out'),Minus,p.onZoomOut)}{item(t('إعدادات العرض','Display settings'),Settings,p.onOpenSettings)}</>)}
        {menu('source',t('المصدر','Source'),<>{item(t('إدارة التخزين وعدم الاتصال','Cache & offline mode'),HardDrive,p.onOpenCacheManager)}{item(t('إعدادات مصدر البيانات','Data source settings'),Settings,p.onOpenSettings)}</>)}
        {menu('maps',t('خرائط','Maps'),p.sources.map(s=>item(s.name,Globe,()=>p.onSelectSource(s),false,p.currentSource.id===s.id)))}
        {menu('layers',t('طبقات','Layers'),p.overlays.map(s=>item(s.name,s.is_grid?Grid3X3:Layers,()=>p.onToggleOverlay(s.id),false,p.activeOverlays.has(s.id))))}
        {menu('favorites',t('مفضلة','Favorites'),<>{item(t('المواقع المحفوظة','Saved places'),Star,()=>{if(!p.showMapTools)p.onToggleMapTools();window.dispatchEvent(new Event('sas:open-favorites'));})}{item(t('الانتقال إلى إحداثيات','Go to coordinates'),Crosshair,p.onOpenGoTo)}</>)}
        {menu('marks',t('علامات','Marks'),<>{item(t('مدير العلامات','Marks manager'),MapPin,p.onOpenMarksManager)}{item(t('رسم مسار','Draw a path'),Ruler,()=>p.onSetSelectionMode('polyline'))}{item(t('تحديد مضلع','Select polygon'),Pentagon,()=>p.onSetSelectionMode('polygon'))}</>)}
        {menu('gps','GPS',<>{item(t('اتصال GPS حقيقي','Connect real GPS'),Navigation,()=>window.dispatchEvent(new CustomEvent('sas:field-tools',{detail:'gps'})))}{item(t('مسارات GPX والتحليل','GPX tracks & analysis'),Ruler,()=>window.dispatchEvent(new CustomEvent('sas:field-tools',{detail:'tracks'})))}{item(t('محاكاة GPS','GPS simulation'),Navigation,p.onOpenGpsSimulator)}</>)}
        {menu('analysis',t('تحليل','Analysis'),<>{item(t('تحليل التضاريس و ArcGIS','Terrain analysis & ArcGIS'),ChartNoAxesCombined,p.onOpenTerrainAnalysis)}{item(t('خطوط التسوية','Contours'),Mountain,p.onOpenTopographyStudio)}{item(t('مخطط الارتفاعات','Elevation profile'),ChartNoAxesCombined,p.onOpenElevation)}{item(t('حرم مكاني وخط الرؤية','Buffer & line of sight'),Crosshair,p.onOpenSpatialAnalysis)}</>)}
        <button className="desktop-menu-label" onClick={p.onOpenSettings}>{t('إعدادات','Settings')}</button>
        {menu('help',t('مساعدة','Help'),<><p className="p-3 text-xs leading-relaxed">{t('حدّد منطقة ثم افتح تحليل التضاريس لإنشاء خرائط الارتفاعات والانحدار والجريان وحزمة ArcGIS. اضغط Esc لإغلاق القوائم.','Select a region, then open Terrain analysis for elevations, slopes, drainage and an ArcGIS package. Press Esc to close menus.')}</p>{item(t('منصة بايثون','Python console'),Terminal,p.onOpenPythonStudio)}</>)}
      </nav>
      <form className="desktop-search" onSubmit={e=>{e.preventDefault();const v=search.trim().split(/[,;\s]+/).map(Number);if(v.length===2&&v.every(Number.isFinite)&&Math.abs(v[0])<=85&&Math.abs(v[1])<=180){(window as any).__SAS_MAP?.setView(v,14);setSearchError('');}else setSearchError(t('أدخل خط العرض ثم الطول: 36.75, 3.05','Enter latitude, longitude: 36.75, 3.05'));}}><input aria-label={t('البحث بالإحداثيات','Search coordinates')} placeholder={t('خط العرض، خط الطول','Latitude, longitude')} value={search} onChange={e=>setSearch(e.target.value)}/><button title={t('انتقال','Go')} aria-label={t('انتقال','Go')}><Search size={15}/></button></form>
      {searchError&&<span role="alert" className="desktop-search-error" onClick={()=>setSearchError('')}>{searchError}</span>}
    </div>
    <div className="desktop-toolbar" role="toolbar" aria-label={t('أدوات الخريطة','Map tools')}>
      {tool(t('تحريك الخريطة','Pan map'),MousePointer2,()=>p.onSetSelectionMode('none'),p.selectionMode==='none')}
      {tool(t('تحديد مستطيل','Select rectangle'),SquareDashed,()=>p.onSetSelectionMode('rect'),p.selectionMode==='rect')}
      {tool(t('تحديد مضلع','Select polygon'),Pentagon,()=>p.onSetSelectionMode('polygon'),p.selectionMode==='polygon')}
      {tool(t('قياس المسافات','Measure distance'),Ruler,()=>p.onSetSelectionMode('polyline'),p.selectionMode==='polyline')}
      <span className="desktop-separator"/>
      {tool(t('الانتقال إلى إحداثيات','Go to coordinates'),Crosshair,p.onOpenGoTo)}
      {tool(t('معالجة التحديد','Process selection'),Download,p.onOpenSelectionOps,false,!p.hasSelection)}
      <span className="desktop-separator"/>
      <label className="desktop-source"><Globe size={22}/><select aria-label={t('خريطة الأساس','Base map')} value={p.currentSource.id} onChange={e=>{const s=p.sources.find(s=>s.id===e.target.value);if(s)p.onSelectSource(s);}}>{p.sources.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
      {p.onCompareSource&&<label className="desktop-source" title={t('مقارنة بالتمرير: اعرض طبقة ثانية على نصف الخريطة واسحب المقبض','Swipe compare: show a second layer over half the map and drag the handle')}><Columns2 size={20} className={p.compareSource?'text-amber-400':undefined}/><select aria-label={t('طبقة المقارنة','Compare layer')} value={p.compareSource?.id||''} onChange={e=>{const s=p.sources.find(s=>s.id===e.target.value);p.onCompareSource!(s||null);}}><option value="">{t('مقارنة: إيقاف','Compare: off')}</option>{p.sources.filter(s=>s.id!==p.currentSource.id).map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>}
      {tool(t('الطبقات والشبكات','Layers & grids'),Layers,()=>setOpen(open==='layers'?null:'layers'),open==='layers')}
      <span className="desktop-separator"/>
      {tool(t('المواقع المحفوظة','Saved places'),Star,()=>{if(!p.showMapTools)p.onToggleMapTools();window.dispatchEvent(new Event('sas:open-favorites'));})}
      {tool(t('مدير العلامات','Marks manager'),MapPin,p.onOpenMarksManager,false,false,'YLW-PUSHPIN.png')}
      {tool(t('مخطط الارتفاعات','Elevation profile'),ChartNoAxesCombined,p.onOpenElevation,false,false,'TrackProfile.svg')}
      {tool(t('خطوط التسوية','Contours'),Mountain,p.onOpenTopographyStudio)}
      {tool(t('تحليل التضاريس والتصدير إلى ArcGIS','Terrain analysis & ArcGIS export'),ChartNoAxesCombined,p.onOpenTerrainAnalysis)}
      <span className="desktop-separator"/>
      {tool('GPS',Navigation,p.onOpenGpsSimulator,false,false,'ARROW.png')}
      {tool(t('إدارة الكاش','Cache manager'),HardDrive,p.onOpenCacheManager)}
      {tool(t('إعدادات البرنامج','Application settings'),Settings,p.onOpenSettings)}
      {tool(t('منصة بايثون','Python console'),Terminal,p.onOpenPythonStudio)}
      {p.extraTools}
      {p.hasSelection&&tool(t('إلغاء التحديد','Clear selection'),Trash2,p.onClearSelection)}
      <span className="ms-auto desktop-toolbar-note">{t('خرائط • تضاريس • تحليل','Maps • Terrain • Analysis')}</span>
    </div>
  </header>;
};
