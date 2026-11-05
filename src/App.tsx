import {FieldLayers,emptyField,type FieldState} from './components/FieldLayers';
import {FieldWorkbench} from './components/FieldWorkbench';
import {Globe2,Map as MapIcon,Building2,BriefcaseBusiness} from 'lucide-react';
import {ProfessionalWorkbench} from './components/ProfessionalWorkbench';
import {useHistoryState} from './utils/history';
import {AlgeriaSheetGrid} from './components/AlgeriaSheetGrid';
import {storeAppValue} from './utils/portableState';
import {AdvancedGisWorkbench} from './components/AdvancedGisWorkbench';
import {WindowTaskbar} from './components/WindowTaskbar';
import {GisPreview} from './components/GisPreview';
import {pathMeasurement,distanceText} from './utils/measurement';
import sourceDefinitions from '../sas_planet_py/map_sources.json';
import React, { useState, useEffect, useCallback, useMemo, Suspense, lazy } from 'react';
import { SettingsModal } from './components/SettingsModal';
import { TerrainWorkbench, TerrainOverlay } from './components/TerrainWorkbench';
import { AppSettings, loadSettings, saveSettings } from './utils/settings';
import { loadCustomSources, saveCustomSources } from './utils/customSources';
import { MapTools, ContourDisplay } from './components/MapTools';
import { HeaderNavbar } from './components/HeaderNavbar';
import { MapCanvas } from './components/MapCanvas';
import { StatusBar } from './components/StatusBar';
import { SelectionOpsModal } from './components/SelectionOpsModal';
import { PythonStudioModal } from './components/PythonStudioModal';
import { MarksManagerModal } from './components/MarksManagerModal';
import { ElevationProfileModal } from './components/ElevationProfileModal';
import { GpsSimulatorModal } from './components/GpsSimulatorModal';
import { GoToModal } from './components/GoToModal';
import { CacheManagerModal } from './components/CacheManagerModal';
import { TopographyStudioModal } from './components/TopographyStudioModal';
import { SpatialAnalysisModal } from './components/SpatialAnalysisModal';
import {
  MapSource,
  SelectionMode,
  BoundingBox,
  MarkItem,
  CoordinatesState
} from './types';
import { getFullCoordinateState } from './utils/geoUtils';
import { getStoredOfflineMode, setStoredOfflineMode } from './utils/tileCache';

const Terrain3DViewer=lazy(()=>import('./components/Terrain3DViewer'));

// Shared with Python and the disk cache service.
const DEFAULT_SOURCES = Object.values(sourceDefinitions.MAP_SOURCES) as MapSource[];

const DEFAULT_OVERLAYS: MapSource[] = [
  {
    id: 'google_hybrid_overlay',
    name: 'Google Labels & Roads (تسميات وطرق)',
    category: 'Overlay',
    url_template: 'https://mt{s}.google.com/vt/lyrs=h&x={x}&y={y}&z={z}',
    subdomains: ['0', '1', '2', '3'],
    max_zoom: 22,
    is_overlay: true
  },
  {
    id: 'openseamap',
    name: 'OpenSeaMap (منارات وممرات بحرية)',
    category: 'Overlay',
    url_template: 'https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png',
    max_zoom: 18,
    is_overlay: true
  },
  {
    id: 'grid_tiles',
    name: 'Tile Coordinates Grid (شبكة ترقيم البلاطات X/Y/Z)',
    category: 'Grid',
    url_template: '',
    max_zoom: 22,
    is_grid: true,
    is_overlay: true
  },
  {
    id: 'grid_degree',
    name: 'Lat/Lon Degree Grid (شبكة خطوط الطول والعرض)',
    category: 'Grid',
    url_template: '',
    max_zoom: 22,
    is_grid: true,
    is_overlay: true
  }
];

const INITIAL_MARKS: MarkItem[] = [
  {
    id: 'mark_1',
    name: 'أهرامات الجيزة (Giza Pyramids)',
    type: 'point',
    coords: [31.1342, 29.9792],
    description: 'أحد عجائب العالم القديم - موقع أثري فريد',
    color: '#f59e0b',
    category: 'معالم أثرية (Monuments)'
  },
  {
    id: 'mark_2',
    name: 'قلعة صلاح الدين (Cairo Citadel)',
    type: 'point',
    coords: [31.2599, 30.0299],
    description: 'موقع إستراتيجي تاريخي يطل على مدينة القاهرة',
    color: '#ef4444',
    category: 'معالم تاريخية (Historic)'
  },
  {
    id: 'mark_3',
    name: 'جزيرة الزمالك (Zamalek Island)',
    type: 'linestring',
    coords: [
      [31.220, 30.070],
      [31.225, 30.055],
      [31.223, 30.040],
      [31.218, 30.055]
    ],
    description: 'مسار ضفاف نهر النيل في الزمالك',
    color: '#10b981',
    category: 'مسارات (Tracks)'
  }
];

const DEFAULT_ELEVATION_PATH: [number, number][] = [
  [30.0444, 31.2357],
  [30.0131, 31.2089],
  [29.9792, 31.1342]
];

export default function App() {
  const [settings, setSettings] = useState<AppSettings>(loadSettings);
  const [lang, setLang] = useState<'ar' | 'en'>(() => loadSettings().language);
  const [sheetGridOpen,setSheetGridOpen]=useState(false);
 const [fieldOpen,setFieldOpen]=useState(false),[fieldTab,setFieldTab]=useState('layers'),[fieldError,setFieldError]=useState('');
 const [field,setField]=useState<FieldState>(()=>{try{return {...emptyField,...JSON.parse(localStorage.getItem('sas:field:v1')||'null')};}catch{return emptyField;}});
 useEffect(()=>{try{const raw=JSON.stringify(field);if(raw.length>4500000)throw Error('Layer settings exceed 4.5 MB; reduce large GeoJSON layers.');storeAppValue('sas:field:v1',raw);}catch(e:any){setFieldError(e.message);}},[field]);
 useEffect(()=>{const open=(e:any)=>{setFieldTab(e.detail||'layers');setFieldOpen(true);setProfessionalOpen(false);setStudioOpen(false);setSheetGridOpen(false);setIsGpsSimulatorOpen(false);};window.addEventListener('sas:field-tools',open);return()=>window.removeEventListener('sas:field-tools',open);},[]);
 const [professionalOpen,setProfessionalOpen]=useState(false),[catalogId,setCatalogId]=useState('');
 const [analyses,setAnalyses]=useState<any[]>(()=>{try{return JSON.parse(localStorage.getItem('sas:analyses:v1')||'[]');}catch{return [];}});
 const [camera3D,setCamera3D]=useState<any>(()=>{try{return JSON.parse(localStorage.getItem('sas:camera3d:v1')||'null');}catch{return null;}});
 useEffect(()=>{const analysis=(e:any)=>setAnalyses(a=>[{...e.detail,at:new Date().toISOString()},...a].slice(0,30));const camera=(e:any)=>setCamera3D(e.detail);window.addEventListener('sas:analysis-result',analysis);window.addEventListener('sas:3d-session',camera);return()=>{window.removeEventListener('sas:analysis-result',analysis);window.removeEventListener('sas:3d-session',camera);};},[]);
 useEffect(()=>{storeAppValue('sas:analyses:v1',JSON.stringify(analyses));},[analyses]);
 useEffect(()=>{storeAppValue('sas:camera3d:v1',JSON.stringify(camera3D));},[camera3D]);
  const [terrain3dOpen,setTerrain3dOpen]=useState(false);
  const [terrain3dRegion,setTerrain3dRegion]=useState<BoundingBox|null>(null);
  const [studioOpen,setStudioOpen]=useState(false);
  const [studioPreview,setStudioPreview]=useState<any>(null);
  const [studioDrawing,setStudioDrawing]=useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsError, setSettingsError] = useState('');
  const [terrainAnalysisOpen, setTerrainAnalysisOpen] = useState(false);
  const [terrainOverlay, setTerrainOverlay] = useState<TerrainOverlay | null>(null);
  const isAr = lang === 'ar';

  // Base Map & Overlays
  const [customSources, setCustomSources] = useState<MapSource[]>(() => loadCustomSources());
  const allSources = useMemo(() => [...DEFAULT_SOURCES, ...customSources], [customSources]);
  const updateCustomSources = useCallback((list: MapSource[]) => { setCustomSources(list); saveCustomSources(list); }, []);
  const [currentSource, setCurrentSource] = useState<MapSource>(() => DEFAULT_SOURCES.find(s=>s.id===loadSettings().defaultSource) || DEFAULT_SOURCES[0]);
  const [compareSource, setCompareSource] = useState<MapSource | null>(null);
  const [activeOverlays, setActiveOverlays] = useState<Set<string>>(new Set(['google_hybrid_overlay']));

  // Cursor & Coordinates State
  const [coordsState, setCoordsState] = useState<CoordinatesState>(
    getFullCoordinateState(30.0444, 31.2357, 13)
  );

  // Selection
  const [selectionMode, setSelectionMode] = useState<SelectionMode>('none');
  const [selectedBbox, setSelectedBbox] = useState<BoundingBox | null>(null);
  const [selectedPolygon, setSelectedPolygon] = useState<[number, number][] | null>(null);
  const [measurementPoints, setMeasurementPoints] = useState<[number, number][]>([]);
  const [digitize, setDigitize] = useState<null | 'linestring' | 'polygon'>(null);
  const [digitizeName, setDigitizeName] = useState<string>('');

  // Marks
  const markHistory = useHistoryState<MarkItem[]>(()=>{try{return JSON.parse(localStorage.getItem('sas:marks:v1')||'null')||INITIAL_MARKS;}catch{return INITIAL_MARKS;}});
  const marks=markHistory.value,setMarks=markHistory.set;
  useEffect(()=>{try{storeAppValue('sas:marks:v1',JSON.stringify(marks));}catch{}},[marks]);

  // GPS Simulation
  const [gpsPosition, setGpsPosition] = useState<{ lat: number; lon: number; bearing: number } | null>(null);
  const [gpsTrack, setGpsTrack] = useState<[number, number][]>([]);

  // Modals Visibility
  const [isSelectionOpsOpen, setIsSelectionOpsOpen] = useState<boolean>(false);
  const [isPythonStudioOpen, setIsPythonStudioOpen] = useState<boolean>(false);
  const [isMarksManagerOpen, setIsMarksManagerOpen] = useState<boolean>(false);
  const [isElevationOpen, setIsElevationOpen] = useState<boolean>(false);
  const [isGpsSimulatorOpen, setIsGpsSimulatorOpen] = useState<boolean>(false);
  const [isGoToOpen, setIsGoToOpen] = useState<boolean>(false);
  const [isCacheManagerOpen, setIsCacheManagerOpen] = useState<boolean>(false);
  const [isTopoStudioOpen, setIsTopoStudioOpen] = useState<boolean>(false);
  const [isSpatialAnalysisOpen, setIsSpatialAnalysisOpen] = useState<boolean>(false);
  const [activeContourGeoJson, setActiveContourGeoJson] = useState<any>(null);

  const [contourDisplay, setContourDisplay] = useState<ContourDisplay>({ visible: true, majorOnly: false, opacity: 0.75 });
  const [topoRegion, setTopoRegion] = useState<BoundingBox | null>(null);

  // Offline Mode State
  const [isOfflineMode, setIsOfflineMode] = useState<boolean>(() => getStoredOfflineMode());

  const handleToggleOfflineMode = useCallback((enabled: boolean) => {
    setIsOfflineMode(enabled);
    setStoredOfflineMode(enabled);
  }, []);

  useEffect(() => {
    const onOfflineChanged = (e: any) => {
      if (e?.detail?.enabled !== undefined) {
        setIsOfflineMode(e.detail.enabled);
      }
    };
    window.addEventListener('sas:offline-mode-changed', onOfflineChanged);
    return () => {
      window.removeEventListener('sas:offline-mode-changed', onOfflineChanged);
    };
  }, []);

  // Cache stats
  const [cacheStats, setCacheStats] = useState({ total_tiles: 0, total_size_mb: 0 });

  const fetchCacheStats = useCallback(async () => {
    try {
      const res = await fetch('/api/cache/stats');
      if (res.ok) {
        const data = await res.json();
        setCacheStats(data);
      }
    } catch (_) {}
  }, []);

  useEffect(() => {
    fetchCacheStats();
  }, [fetchCacheStats]);

  // Mouse movement updater
  const handleMouseMoveCoords = useCallback((lat: number, lon: number, zoom: number) => {
    setCoordsState(getFullCoordinateState(lat, lon, zoom));
  }, []);

  const handleToggleOverlay = (overlayId: string) => {
    setActiveOverlays((prev) => {
      const next = new Set(prev);
      if (next.has(overlayId)) {
        next.delete(overlayId);
      } else {
        next.add(overlayId);
      }
      return next;
    });
  };

  const handleClearSelection = () => {
    setSelectedBbox(null);
    setSelectedPolygon(null);
    setMeasurementPoints([]);
    setSelectionMode('none');
  };

  // Convert polygon or bbox into active BoundingBox for Selection Operations
  const activeBbox: BoundingBox = selectedBbox || (
    selectedPolygon && selectedPolygon.length > 0
      ? {
          min_lon: Math.min(...selectedPolygon.map((p) => p[1])),
          min_lat: Math.min(...selectedPolygon.map((p) => p[0])),
          max_lon: Math.max(...selectedPolygon.map((p) => p[1])),
          max_lat: Math.max(...selectedPolygon.map((p) => p[0]))
        }
      : { min_lon: 31.20, min_lat: 30.00, max_lon: 31.28, max_lat: 30.08 }
  );

  const hasSelection = Boolean(selectedBbox || (selectedPolygon && selectedPolygon.length > 1));

  const currentMapBounds = (): BoundingBox | null => {
    const map = (window as any).__SAS_MAP;
    if (!map) return null;
    const b = map.getBounds();
    return { min_lon: Math.max(-180, b.getWest()), min_lat: Math.max(-85, b.getSouth()),
      max_lon: Math.min(180, b.getEast()), max_lat: Math.min(85, b.getNorth()) };
  };
  const openTopography = () => {
    const region = hasSelection ? activeBbox : currentMapBounds();
    if (!region) return;
    setTopoRegion(region); setIsTopoStudioOpen(true);
  };

  const openTerrainAnalysis = () => {
    const region = hasSelection ? activeBbox : currentMapBounds();
    if (region) { setTopoRegion(region); setTerrainAnalysisOpen(true); }
  };
  const applySettings = (next: AppSettings) => {
    setSettings(next); setLang(next.language);
    if (next.defaultSource !== settings.defaultSource) setCurrentSource(DEFAULT_SOURCES.find(s=>s.id===next.defaultSource) || DEFAULT_SOURCES[0]);
    try { saveSettings(next); setSettingsError(''); }
    catch { setSettingsError(next.language==='ar'?'تم تطبيق الإعدادات، لكن تعذر حفظها في المتصفح.':'Settings applied, but browser storage is unavailable.'); }
    setSettingsOpen(false);
  };

  const handleUpdateGpsPosition = useCallback((pos: { lat: number; lon: number; bearing: number } | null) => {
    setGpsPosition(pos);
    if (pos) {
      setGpsTrack((prev) => [...prev, [pos.lat, pos.lon]]);
    }
  }, []);

  return (
    <div className={`flex flex-col h-screen w-screen sas-desktop overflow-hidden font-['Cairo',sans-serif] ${settings.theme === 'dark' ? 'sas-dark' : 'sas-classic'} ${isAr ? 'rtl' : 'ltr'}`}>
      {/* Header & Main Menu / Toolbars */}
      <HeaderNavbar
        currentSource={currentSource}
        sources={allSources}
        compareSource={compareSource}
        onCompareSource={setCompareSource}
        overlays={DEFAULT_OVERLAYS}
        activeOverlays={activeOverlays}
        selectionMode={selectionMode}
        hasSelection={hasSelection}
        onSelectSource={setCurrentSource}
        onToggleOverlay={handleToggleOverlay}
        onSetSelectionMode={setSelectionMode}
        onClearSelection={handleClearSelection}
        onOpenSelectionOps={() => setIsSelectionOpsOpen(true)}
        onOpenPythonStudio={() => setIsPythonStudioOpen(true)}
        onOpenMarksManager={() => setIsMarksManagerOpen(true)}
        onDigitizeLine={()=>{setDigitize('linestring');setDigitizeName('');setSelectedPolygon(null);setMeasurementPoints([]);setSelectionMode('polyline');}}
        onDigitizePolygon={()=>{setDigitize('polygon');setDigitizeName('');setSelectedPolygon(null);setMeasurementPoints([]);setSelectionMode('polygon');}}
        onOpenTopographyStudio={openTopography}
        onOpenSpatialAnalysis={() => setIsSpatialAnalysisOpen(true)}
        onOpenGpsSimulator={() => setIsGpsSimulatorOpen(true)}
        onOpenElevation={() => setIsElevationOpen(true)}
        onOpenGoTo={() => setIsGoToOpen(true)}
        onOpenCacheManager={() => setIsCacheManagerOpen(true)}
        onZoomIn={() => {
          const map = (window as any).__SAS_MAP;
          if (map) map.zoomIn();
        }}
        onZoomOut={() => {
          const map = (window as any).__SAS_MAP;
          if (map) map.zoomOut();
        }}
        lang={lang}
        onToggleLang={() => applySettings({...settings, language:lang==='ar'?'en':'ar'})}
        isOfflineMode={isOfflineMode}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenTerrainAnalysis={openTerrainAnalysis}
        extraTools={<div className="desktop-feature-tools" role="group" aria-label={isAr?'أدوات العرض والتحليل':'Display and analysis tools'}>
          <button className="desktop-feature-tool feature-earth" title={isAr?'عرض الأرض 3D':'3D Earth view'} aria-label={isAr?'عرض الأرض 3D':'3D Earth view'} onClick={()=>{const region=hasSelection?activeBbox:currentMapBounds();if(region){setTerrain3dRegion(region);setTerrain3dOpen(true);}}}><Globe2 size={22}/></button>
          <button className="desktop-feature-tool feature-sheets" title={isAr?'تقسيم الجزائر 1:25000':'Algeria sheets 1:25,000'} aria-label={isAr?'تقسيم الجزائر 1:25000':'Algeria sheets 1:25,000'} aria-pressed={sheetGridOpen} onClick={()=>{setFieldOpen(false);setSheetGridOpen(v=>!v);setProfessionalOpen(false);setStudioOpen(false);}}><MapIcon size={22}/></button>
          <button className="desktop-feature-tool feature-gis" title={isAr?'أدوات GIS والمباني':'GIS tools & buildings'} aria-label={isAr?'أدوات GIS والمباني':'GIS tools & buildings'} aria-pressed={studioOpen} onClick={()=>{setFieldOpen(false);setStudioOpen(v=>!v);setProfessionalOpen(false);setSheetGridOpen(false);}}><Building2 size={22}/></button>
          <button className="desktop-feature-tool feature-professional" title={isAr?'الأدوات الاحترافية':'Professional tools'} aria-label={isAr?'الأدوات الاحترافية':'Professional tools'} aria-pressed={professionalOpen} onClick={()=>{setFieldOpen(false);setProfessionalOpen(v=>!v);setStudioOpen(false);setSheetGridOpen(false);}}><BriefcaseBusiness size={22}/></button>
        </div>}
        showMapTools={settings.showMapTools}
        onToggleMapTools={() => applySettings({...settings,showMapTools:!settings.showMapTools})}
      />

      <MapTools lang={lang} currentSource={currentSource} sources={allSources} onSelectSource={setCurrentSource}
        onSelectView={() => { const b = currentMapBounds(); if (b) { setSelectedBbox(b); setSelectedPolygon(null); setSelectionMode('none'); } }}
        onOpenTopography={openTopography} contours={activeContourGeoJson} display={contourDisplay}
        onDisplayChange={setContourDisplay} onClearContours={() => setActiveContourGeoJson(null)} />

      {/* Main Interactive Map Canvas */}
      <main className="flex-1 min-h-0 min-w-0 relative overflow-hidden">
        <MapCanvas
          settings={settings}
          terrainOverlay={terrainOverlay}
          currentSource={currentSource}
          sources={allSources}
          compareSource={compareSource}
          onCompareSource={setCompareSource}
          activeOverlays={activeOverlays}
          selectionMode={selectionMode}
          selectedBbox={selectedBbox}
          selectedPolygon={selectedPolygon}
          measurementPoints={measurementPoints}
          marks={field.marksVisible===false?[]:marks}
          gpsPosition={gpsPosition}
          gpsTrack={gpsTrack}
          contourGeoJson={activeContourGeoJson}
          contourDisplay={contourDisplay}
          isOfflineMode={isOfflineMode}
          onMouseMoveCoords={handleMouseMoveCoords}
          onSetBbox={(b) => {
            setSelectedBbox(b);
            setSelectionMode('none');
            if(studioDrawing){setStudioDrawing(false);setStudioOpen(true);}else setIsSelectionOpsOpen(true);
          }}
          onSetPolygon={(pts) => {
            setSelectedPolygon(pts);
          }}
          onFinishDrawing={(mode,points)=>{
            if(digitize){
              const min=digitize==='polygon'?3:2;
              if(points.length>=min){
                const coords=points.map(([la,lo])=>[lo,la] as [number,number]);
                setMarks(m=>[...m,{id:'feat_'+Date.now(),name:digitizeName.trim()||(digitize==='polygon'?(isAr?'مضلّع':'Polygon'):(isAr?'طريق':'Route')),type:digitize,coords,category:digitize==='polygon'?(isAr?'مساحات':'Areas'):(isAr?'طرق':'Routes'),color:'#ef4444',timestamp:new Date().toISOString()} as MarkItem]);
              }
              setDigitize(null);setSelectedPolygon(null);setMeasurementPoints([]);setSelectionMode('none');return;
            }
            if(mode==='polyline')setMeasurementPoints(points);if(mode==='polygon'){setSelectedBbox(null);setSelectedPolygon(points);if(studioDrawing){setStudioDrawing(false);setStudioOpen(true);}}setSelectionMode('none');
          }}
          onSetMeasurementPoints={(pts) => {
            setMeasurementPoints(pts);
          }}
          onSelectMark={(mark) => {
            if((window as any).__SAS_VECTOR_EDITING)return;
            setIsMarksManagerOpen(true);
          }}
        />

        <FieldLayers state={field} offline={isOfflineMode} onError={setFieldError}/>
        {fieldError&&<div role="status" className="absolute bottom-12 start-12 z-30 desktop-dialog p-2 text-xs max-w-sm">{fieldError}</div>}
        {studioDrawing&&<button className="absolute top-14 end-3 z-[400] desktop-button" onClick={()=>{setSelectionMode('none');setStudioDrawing(false);setStudioOpen(true);}}>{isAr?'عودة للأدوات':'Return to tools'}</button>}
        {digitize&&<section className="absolute top-3 start-12 z-30 desktop-dialog p-3 text-sm min-w-72" aria-label={isAr?'رسم عنصر':'Draw feature'}>
          <strong>{isAr?'رسم عنصر جديد':'Draw new feature'} — {digitize==='polygon'?(isAr?'مضلّع / مساحة':'Polygon / area'):(isAr?'خط / طريق':'Line / route')}</strong>
          <input value={digitizeName} onChange={e=>setDigitizeName(e.target.value)} placeholder={isAr?'اسم العنصر (اختياري)':'Feature name (optional)'} maxLength={80}/>
          <p className="text-xs mt-1 opacity-80">{isAr?'انقر على الخريطة لإضافة نقاط، ثم «إنهاء وحفظ» أو انقر مرتين.':'Click the map to add points, then Finish & save (or double-click).'}</p>
          {digitize==='linestring'&&measurementPoints.length>=2&&<p className="text-xs mt-1">{isAr?'الطول: ':'Length: '}{distanceText(pathMeasurement(measurementPoints).distance,isAr)}</p>}
          <div className="flex gap-2 mt-2">
            <button className="desktop-button primary" onClick={()=>window.dispatchEvent(new CustomEvent('sas:drawing-command',{detail:'finish'}))}>{isAr?'إنهاء وحفظ':'Finish & save'}</button>
            <button className="desktop-button" onClick={()=>window.dispatchEvent(new CustomEvent('sas:drawing-command',{detail:'undo'}))}>{isAr?'تراجع':'Undo'}</button>
            <button className="desktop-button" onClick={()=>{setDigitize(null);setSelectedPolygon(null);setMeasurementPoints([]);setSelectionMode('none');}}>{isAr?'إلغاء':'Cancel'}</button>
          </div>
        </section>}
        {measurementPoints.length>=2&&!digitize&&<section className="absolute top-3 start-12 z-30 desktop-dialog p-3 text-sm min-w-64" aria-label={isAr?'نتيجة قياس المسافة':'Distance measurement'}>
          <strong data-testid="distance-result">{isAr?'المسافة: ':'Distance: '}{distanceText(pathMeasurement(measurementPoints).distance,isAr)}</strong>
          <p className="text-xs mt-1">{isAr?'عدد المقاطع: ':'Segments: '}{measurementPoints.length-1} · WGS84</p>
          <p className="text-xs mt-1">{selectionMode==='polyline'?(isAr?'قياس جارٍ — انقر مرتين أو اضغط إنهاء':'Measuring — double click or Finish'):(isAr?'اكتمل القياس':'Measurement complete')}</p>
          <div className="flex gap-2 mt-2">{selectionMode==='polyline'&&<><button className="desktop-button primary" onClick={()=>window.dispatchEvent(new CustomEvent('sas:drawing-command',{detail:'finish'}))}>{isAr?'إنهاء':'Finish'}</button><button className="desktop-button" onClick={()=>window.dispatchEvent(new CustomEvent('sas:drawing-command',{detail:'undo'}))}>{isAr?'تراجع':'Undo'}</button></>}<button className="desktop-button" onClick={()=>{setMeasurementPoints([]);setSelectionMode('none');}}>{isAr?'مسح':'Clear'}</button></div>
        </section>}
        {terrainOverlay && <div className="terrain-map-legend"><span>{terrainOverlay.name}</span><button onClick={()=>setTerrainOverlay(null)} aria-label={isAr?'إزالة طبقة التحليل':'Remove analysis layer'}>×</button></div>}
        {settingsError && <p role="alert" className="absolute bottom-8 start-12 z-30 bg-amber-100 text-amber-950 p-2 rounded">{settingsError}</p>}

        {/* Floating Active Tool Notification Banner */}
        {selectionMode !== 'none' && (
          <div className="absolute bottom-3 start-1/2 -translate-x-1/2 z-20 px-4 py-2 rounded-full bg-slate-900/95 border border-amber-500 text-amber-300 text-xs font-semibold shadow-2xl backdrop-blur-md flex items-center gap-3">
            <span>
              {selectionMode === 'rect' && (isAr ? 'انقر واسحب أو انقر نقطتين لتحديد المستطيل' : 'Click two corners to define rectangle')}
              {selectionMode === 'polygon' && (isAr ? 'انقر لإضافة نقاط المضلع، انقر نقراً مزدوجاً للإنهاء' : 'Click to add polygon points, double click to finish')}
              {selectionMode === 'polyline' && (isAr ? 'انقر لقياس المسار بين النقاط، انقر نقراً مزدوجاً للإنهاء' : 'Click to measure path length, double click to finish')}
            </span>
            <button
              onClick={handleClearSelection}
              className="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px]"
            >
              {isAr ? 'إلغاء' : 'Cancel'}
            </button>
          </div>
        )}
      </main>

      {/* Bottom Status Bar (Live Coordinates, Scale, Zoom, Cache, Offline Mode) */}
      {settings.showStatusBar && <StatusBar
        settings={settings}
        coords={coordsState}
        cacheStats={cacheStats}
        projectionName={currentSource.projection || 'EPSG:3857'}
        lang={lang}
        isOfflineMode={isOfflineMode}
        onToggleOfflineMode={() => handleToggleOfflineMode(!isOfflineMode)}
      />}

      <FieldWorkbench open={fieldOpen} tab={fieldTab} ar={isAr} state={field} onState={setField} marks={marks} onImport={incoming=>setMarks(m=>[...m,...incoming])} bbox={(()=>{const b=hasSelection?activeBbox:currentMapBounds()||activeBbox;return [b.min_lon,b.min_lat,b.max_lon,b.max_lat];})()} polygon={selectedPolygon} source={settings.terrainSource} offline={isOfflineMode} onClose={()=>setFieldOpen(false)} onPosition={setGpsPosition} onTrack={setGpsTrack}/>
      {professionalOpen&&<ProfessionalWorkbench ar={isAr} bbox={(()=>{const b=hasSelection?activeBbox:currentMapBounds()||activeBbox;return [b.min_lon,b.min_lat,b.max_lon,b.max_lat];})()} source={settings.terrainSource} offline={isOfflineMode} marks={marks} onMarks={setMarks} undo={markHistory.undo} redo={markHistory.redo} canUndo={markHistory.canUndo} canRedo={markHistory.canRedo} analyses={analyses} onPreview={setStudioPreview} onCatalog={id=>{setCatalogId(id);setProfessionalOpen(false);setSheetGridOpen(true);}} onClose={()=>setProfessionalOpen(false)}
       snapshot={()=>{const map=(window as any).__SAS_MAP,c=map?.getCenter();return {settings,marks,view:c?{lat:c.lat,lon:c.lng,zoom:map.getZoom()}:null,sourceId:currentSource.id,overlays:[...activeOverlays],contours:activeContourGeoJson,contourDisplay,terrainOverlay,analyses,camera3D,catalogId,field};}}
       restore={state=>{setField(state.field||emptyField);if(state.settings)applySettings(state.settings);if(state.marks)setMarks(state.marks);const source=allSources.find(s=>s.id===state.sourceId);if(source)setCurrentSource(source);if(state.overlays)setActiveOverlays(new Set(state.overlays));setActiveContourGeoJson(state.contours||null);if(state.contourDisplay)setContourDisplay(state.contourDisplay);setTerrainOverlay(state.terrainOverlay||null);setAnalyses(state.analyses||[]);setCamera3D(state.camera3D||null);setCatalogId(state.catalogId||'');if(state.view)(window as any).__SAS_MAP?.setView([state.view.lat,state.view.lon],state.view.zoom);if(state.camera3D?.bbox){const b=state.camera3D.bbox;setSelectedBbox({min_lon:b[0],min_lat:b[1],max_lon:b[2],max_lat:b[3]});setSelectedPolygon(null);}}}/>}
      {studioOpen&&<AdvancedGisWorkbench lang={lang} bbox={hasSelection?activeBbox:currentMapBounds()||activeBbox} source={currentSource} offline={isOfflineMode} polygon={selectedPolygon} marks={marks} preview={studioPreview} onPreview={setStudioPreview} onOverlay={setTerrainOverlay} onClose={()=>setStudioOpen(false)} onDraw={mode=>{setStudioDrawing(true);setStudioOpen(false);setSelectedBbox(null);setSelectedPolygon(null);setSelectionMode(mode);}} onImport={collection=>{const incoming:MarkItem[]=[];for(const f of collection.features||[]){const type=f.geometry?.type;if(['Point','LineString','Polygon'].includes(type))incoming.push({id:crypto.randomUUID(),type:type==='Point'?'point':type==='LineString'?'linestring':'polygon',coords:f.geometry.coordinates,name:f.properties?.name||'GIS feature',description:JSON.stringify(f.properties||{}),category:type==='Polygon'?'Buildings / GIS':'GIS',color:'#00a6b6'});}setMarks(m=>[...m,...incoming]);}}/>}
      {terrain3dOpen&&terrain3dRegion&&<Suspense fallback={<div className="fixed inset-0 z-[1000] bg-black/60 flex items-center justify-center text-white">{isAr?'تحميل عارض 3D…':'Loading 3D viewer…'}</div>}><Terrain3DViewer region={terrain3dRegion} source={currentSource} marks={marks} offline={isOfflineMode} lang={lang} defaultTerrainSource={settings.terrainSource} initialSession={camera3D} onClose={()=>setTerrain3dOpen(false)}/></Suspense>}
      {sheetGridOpen&&<AlgeriaSheetGrid catalogId={catalogId} ar={isAr} offline={isOfflineMode} terrainSource={settings.terrainSource} onClose={()=>setSheetGridOpen(false)} onSelect={bbox=>{setSelectedBbox(bbox);setSelectedPolygon(null);setSelectionMode('none');}} onAnalyze={bbox=>{setSheetGridOpen(false);setTopoRegion(bbox);setTerrainAnalysisOpen(true);}}/>}
      <WindowTaskbar lang={lang} />
      {/* Modals */}
      {settingsOpen && <SettingsModal settings={settings} sources={allSources} customSources={customSources} onCustomSourcesChange={list=>{updateCustomSources(list);if(currentSource.custom&&!list.some(s=>s.id===currentSource.id))setCurrentSource(DEFAULT_SOURCES[0]);}} onSave={applySettings} onClose={()=>setSettingsOpen(false)} />}
      {terrainAnalysisOpen && <TerrainWorkbench bbox={topoRegion || activeBbox} settings={settings} isOfflineMode={isOfflineMode} onClose={()=>setTerrainAnalysisOpen(false)} onApply={setTerrainOverlay} />}
      {isSelectionOpsOpen && (
        <SelectionOpsModal
          isOpen={isSelectionOpsOpen}
          onClose={() => setIsSelectionOpsOpen(false)}
          bbox={activeBbox}
          currentSource={currentSource}
          sources={allSources}
          lang={lang}
          onCacheUpdated={fetchCacheStats}
          onImport={incoming=>setMarks(m=>[...m,...incoming])}
          onApplyImportedSelection={(bbox,polygon)=>{setSelectedBbox(bbox);setSelectedPolygon(polygon||null);setSelectionMode('none');(window as any).__SAS_MAP?.fitBounds([[bbox.min_lat,bbox.min_lon],[bbox.max_lat,bbox.max_lon]],{padding:[48,48],maxZoom:18});}}
        />
      )}

      {isPythonStudioOpen && (
        <PythonStudioModal
          isOpen={isPythonStudioOpen}
          onClose={() => setIsPythonStudioOpen(false)}
          lang={lang}
        />
      )}

      {isMarksManagerOpen && (
        <MarksManagerModal
          isOpen={isMarksManagerOpen}
          onClose={() => setIsMarksManagerOpen(false)}
          marks={marks}
          onAddMark={(m) => setMarks((prev) => [...prev, m])}
          onDeleteMark={(id) => setMarks((prev) => prev.filter((m) => m.id !== id))}
          onImportMarks={(newMarks) => setMarks((prev) => [...prev, ...newMarks])}
          onToggleMark={(id) => setMarks((prev) => prev.map((m) => m.id === id ? { ...m, hidden: !m.hidden } : m))}
          onSetAllHidden={(hidden) => setMarks((prev) => prev.map((m) => ({ ...m, hidden })))}
          lang={lang}
        />
      )}

      {isElevationOpen && (
        <ElevationProfileModal
          isOpen={isElevationOpen}
          onClose={() => setIsElevationOpen(false)}
          pathCoords={measurementPoints.length >= 2 ? measurementPoints : DEFAULT_ELEVATION_PATH}
          isOfflineMode={isOfflineMode}
          lang={lang}
        />
      )}

      {isGpsSimulatorOpen && (
        <GpsSimulatorModal
          isOpen={isGpsSimulatorOpen}
          onClose={() => setIsGpsSimulatorOpen(false)}
          gpsPosition={gpsPosition}
          onUpdatePosition={handleUpdateGpsPosition}
          lang={lang}
        />
      )}

      {isGoToOpen && (
        <GoToModal
          preferNordSahara={settings.coordinateSystem==='utm_nord_sahara'}
          defaultNordSaharaZone={settings.nordSaharaZone||Math.max(29,Math.min(32,Math.floor((coordsState.lon+180)/6)+1))}
          isOpen={isGoToOpen}
          onClose={() => setIsGoToOpen(false)}
          onNavigate={(lat, lon, z) => {
            const map = (window as any).__SAS_MAP;
            if (map) {
              map.setView([lat, lon], z || 15);
            }
          }}
          lang={lang}
        />
      )}

      {isCacheManagerOpen && (
        <CacheManagerModal
          isOpen={isCacheManagerOpen}
          onClose={() => setIsCacheManagerOpen(false)}
          lang={lang}
          isOfflineMode={isOfflineMode}
          onToggleOfflineMode={handleToggleOfflineMode}
          currentSource={currentSource}
          onCacheUpdated={fetchCacheStats}
        />
      )}

      {isTopoStudioOpen && (
        <TopographyStudioModal
          isOpen={isTopoStudioOpen}
          onClose={() => setIsTopoStudioOpen(false)}
          bbox={topoRegion || activeBbox}
          settings={settings}
          isOfflineMode={isOfflineMode}
          onApplyContoursToMap={(geojson) => { setActiveContourGeoJson(geojson); setContourDisplay(prev => ({ ...prev, visible: true })); }}
          lang={lang}
        />
      )}

      {isSpatialAnalysisOpen && (
        <SpatialAnalysisModal
          isOpen={isSpatialAnalysisOpen}
          onClose={() => setIsSpatialAnalysisOpen(false)}
          centerCoords={{ lat: coordsState.lat, lon: coordsState.lon }}
          marks={marks}
          onAddBufferToMap={(pts, name) => {
            const newMark: MarkItem = {
              id: 'buf_' + Date.now(),
              name: name,
              type: 'polygon',
              coords: [pts.map((p) => [p[1], p[0]])],
              description: 'Geodesic Buffer Zone',
              color: '#a855f7',
              category: 'Buffers (نطاقات حرم)'
            };
            setMarks((prev) => [...prev, newMark]);
          }}
          lang={lang}
        />
      )}
    </div>
  );
}
