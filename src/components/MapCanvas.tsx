import {appendDistinctPoint,pathMeasurement,distanceText} from '../utils/measurement';
import { storeAppValue } from '../utils/portableState';
import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import { MapSource, SelectionMode, MarkItem, BoundingBox } from '../types';
import type { AppSettings } from '../utils/settings';
import type { TerrainOverlay } from './TerrainWorkbench';
import type { ContourDisplay } from './MapTools';
import { lonLatToTile } from '../utils/geoUtils';
import {
  createOfflinePlaceholderCanvas,
  getMapTileBlob
} from '../utils/tileCache';

interface MapCanvasProps {
  settings: AppSettings;
  terrainOverlay: TerrainOverlay | null;
  currentSource: MapSource;
  activeOverlays: Set<string>;
  selectionMode: SelectionMode;
  selectedBbox: BoundingBox | null;
  selectedPolygon: [number, number][] | null; // [lat, lon]
  measurementPoints: [number, number][]; // [lat, lon]
  marks: MarkItem[];
  gpsPosition: { lat: number; lon: number; bearing: number } | null;
  gpsTrack: [number, number][];
  contourGeoJson?: any;
  contourDisplay: ContourDisplay;
  isOfflineMode?: boolean;
  onMouseMoveCoords: (lat: number, lon: number, zoom: number) => void;
  onSetBbox: (bbox: BoundingBox) => void;
  onSetPolygon: (pts: [number, number][]) => void;
  onSetMeasurementPoints: (pts: [number, number][]) => void;
  onFinishDrawing: (mode:SelectionMode,points:[number,number][])=>void;
  onSelectMark?: (mark: MarkItem) => void;
  showLabels?: boolean;
  sources?: MapSource[];
  compareSource?: MapSource | null;
  onCompareSource?: (s: MapSource | null) => void;
}

export const MapCanvas: React.FC<MapCanvasProps> = ({
  settings,
  terrainOverlay,
  currentSource,
  activeOverlays,
  selectionMode,
  selectedBbox,
  selectedPolygon,
  measurementPoints,
  marks,
  gpsPosition,
  gpsTrack,
  contourGeoJson,
  contourDisplay,
  isOfflineMode = false,
  onMouseMoveCoords,
  onSetBbox,
  onSetPolygon,
  onSetMeasurementPoints,
  onFinishDrawing,
  onSelectMark,
  showLabels = false,
  sources = [],
  compareSource = null,
  onCompareSource
}) => {
  const [liveZoom, setLiveZoom] = useState(4);
  const [swipeRatio, setSwipeRatio] = useState(0.5);
  const swipeRatioRef = useRef(swipeRatio);
  swipeRatioRef.current = swipeRatio;
  const terrainRasterRef = useRef<L.ImageOverlay | null>(null);
  const compareLayerRef = useRef<L.TileLayer | null>(null);
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);

  // Layers refs
  const baseTileLayerRef = useRef<L.TileLayer | null>(null);
  const overlayLayersRef = useRef<Map<string, L.TileLayer>>(new Map());
  const gridLayerRef = useRef<L.GridLayer | null>(null);
  const selectionLayerGroupRef = useRef<L.LayerGroup | null>(null);
  const marksLayerGroupRef = useRef<L.LayerGroup | null>(null);
  const gpsLayerGroupRef = useRef<L.LayerGroup | null>(null);
  const contourLayerGroupRef = useRef<L.LayerGroup | null>(null);

  const callbacksRef=useRef({onFinishDrawing,onSetMeasurementPoints,onSetPolygon,onSetBbox});
  callbacksRef.current={onFinishDrawing,onSetMeasurementPoints,onSetPolygon,onSetBbox};
  const finishDrawingRef=useRef<()=>void>(()=>{});

  // Drawing state
  const isDrawingRectRef = useRef<boolean>(false);
  const rectStartPointRef = useRef<L.LatLng | null>(null);
  const polyPointsRef = useRef<[number, number][]>([]);

  // 1. Initialize Map
  useEffect(() => {
    if (!mapContainerRef.current || mapInstanceRef.current) return;

    let initial: {lat:number;lon:number;zoom:number} = {lat:25,lon:14,zoom:4};
    if (settings.rememberView) {
      try { const s=JSON.parse(localStorage.getItem('sas:last-view:v1') || 'null');
        if(s && Number.isFinite(s.lat) && Math.abs(s.lat)<=85 && Number.isFinite(s.lon) && Math.abs(s.lon)<=180 && Number.isInteger(s.zoom) && s.zoom>=1 && s.zoom<=21) initial=s;
      } catch {}
    }
    const map = L.map(mapContainerRef.current, {
      center: [initial.lat, initial.lon],
      zoom: initial.zoom,
      scrollWheelZoom: settings.wheelZoom,
      zoomAnimation: true,
      fadeAnimation: true,
      markerZoomAnimation: true,
      minZoom: 1,
      maxZoom: 21,
      zoomControl: false,
      attributionControl: false
    });

    // Dedicated panes keep a fixed stacking order: base map at the bottom, the
    // swipe-compare layer just above it, then all overlays/grids ABOVE the base
    // so switching the base source can never bury the active overlays.
    map.createPane('sas-base').style.zIndex = '200';
    map.createPane('sas-compare').style.zIndex = '210';
    map.createPane('sas-overlays').style.zIndex = '350';

    // Add scale control
    L.control.scale({ imperial: false, position: 'bottomleft' }).addTo(map);

    // Create selection & marks layer groups
    selectionLayerGroupRef.current = L.layerGroup().addTo(map);
    marksLayerGroupRef.current = L.layerGroup().addTo(map);
    gpsLayerGroupRef.current = L.layerGroup().addTo(map);
    contourLayerGroupRef.current = L.layerGroup().addTo(map);

    // Mouse movement listener
    map.on('mousemove', (e: L.LeafletMouseEvent) => {
      onMouseMoveCoords(e.latlng.lat, e.latlng.lng, map.getZoom());

      // If dragging rectangle
      if (isDrawingRectRef.current && rectStartPointRef.current && selectionLayerGroupRef.current) {
        const bounds = L.latLngBounds(rectStartPointRef.current, e.latlng);
        selectionLayerGroupRef.current.clearLayers();
        L.rectangle(bounds, {
          color: '#f59e0b',
          weight: 2,
          fillColor: '#f59e0b',
          fillOpacity: 0.2,
          dashArray: '5, 5'
        }).addTo(selectionLayerGroupRef.current);
      }
    });

    setLiveZoom(map.getZoom());
    map.on('zoomend', () => {
      setLiveZoom(map.getZoom());
      const center = map.getCenter();
      onMouseMoveCoords(center.lat, center.lng, map.getZoom());
    });

    // Click handler for drawing
    map.on('click', (e: L.LeafletMouseEvent) => {
      const curMode = (window as any).__SAS_SELECTION_MODE;
      if(e.originalEvent.detail>1)return;

      if (curMode === 'rect') {
        if (!rectStartPointRef.current) {
          rectStartPointRef.current = e.latlng;
          isDrawingRectRef.current = true;
        } else {
          // Finish rect
          const bounds = L.latLngBounds(rectStartPointRef.current, e.latlng);
          callbacksRef.current.onSetBbox({
            min_lon: Math.min(rectStartPointRef.current.lng, e.latlng.lng),
            min_lat: Math.min(rectStartPointRef.current.lat, e.latlng.lat),
            max_lon: Math.max(rectStartPointRef.current.lng, e.latlng.lng),
            max_lat: Math.max(rectStartPointRef.current.lat, e.latlng.lat)
          });
          rectStartPointRef.current = null;
          isDrawingRectRef.current = false;
        }
      } else if (curMode === 'polygon') {
        const newPts = appendDistinctPoint(polyPointsRef.current,[e.latlng.lat,e.latlng.lng]);
        polyPointsRef.current = newPts;
        callbacksRef.current.onSetPolygon(newPts);
      } else if (curMode === 'polyline') {
        const newPts = appendDistinctPoint(polyPointsRef.current,[e.latlng.lat,e.latlng.lng]);
        polyPointsRef.current = newPts;
        callbacksRef.current.onSetMeasurementPoints(newPts);
      }
    });

    const finish=()=>{
      const mode=(window as any).__SAS_SELECTION_MODE as SelectionMode;
      const points=polyPointsRef.current;
      if((mode==='polyline'&&points.length>=2)||(mode==='polygon'&&points.length>=3)){
        callbacksRef.current.onFinishDrawing(mode,[...points]);
        polyPointsRef.current=[];
      }
    };
    finishDrawingRef.current=finish;
    map.on('dblclick',(event:L.LeafletMouseEvent)=>{
      if(['polyline','polygon'].includes((window as any).__SAS_SELECTION_MODE)){
        L.DomEvent.stop(event.originalEvent);finish();
      }
    });
    const drawingCommand=(event:Event)=>{
      const command=(event as CustomEvent).detail;
      if(command==='finish')finish();
      if(command==='undo'){
        polyPointsRef.current=polyPointsRef.current.slice(0,-1);
        const mode=(window as any).__SAS_SELECTION_MODE;
        if(mode==='polyline')callbacksRef.current.onSetMeasurementPoints([...polyPointsRef.current]);
        if(mode==='polygon')callbacksRef.current.onSetPolygon([...polyPointsRef.current]);
      }
    };
    window.addEventListener('sas:drawing-command',drawingCommand);
    const key=(event:KeyboardEvent)=>{
      if((event.target as HTMLElement)?.closest('input,textarea,select,[contenteditable="true"]'))return;
      if(event.key==='Enter')finish();
      if(event.key==='Backspace'&&['polyline','polygon'].includes((window as any).__SAS_SELECTION_MODE)){
        event.preventDefault();drawingCommand(new CustomEvent('sas:drawing-command',{detail:'undo'}));
      }
    };
    window.addEventListener('keydown',key);

    mapInstanceRef.current = map;
    (window as any).__SAS_MAP = map;
    window.dispatchEvent(new Event('sas:map-ready'));
    onMouseMoveCoords(initial.lat,initial.lon,initial.zoom);
    const resize=new ResizeObserver(()=>map.invalidateSize({animate:false}));
    resize.observe(mapContainerRef.current);

    return () => {
      window.removeEventListener('sas:drawing-command',drawingCommand);window.removeEventListener('keydown',key);
      resize.disconnect();
      map.remove();
      mapInstanceRef.current = null;
      delete (window as any).__SAS_MAP;
    };
  }, []);

  useEffect(()=>{
    const map=mapInstanceRef.current;if(!map)return;
    settings.wheelZoom?map.scrollWheelZoom.enable():map.scrollWheelZoom.disable();
    map.getContainer().classList.toggle('sas-reduced-motion',!settings.animations);
    const remember=()=>{if(settings.rememberView){const c=map.getCenter().wrap();try{storeAppValue('sas:last-view:v1',JSON.stringify({lat:c.lat,lon:c.lng,zoom:map.getZoom()}));}catch{}}};
    map.on('moveend',remember);return()=>{map.off('moveend',remember);};
  },[settings.wheelZoom,settings.animations,settings.rememberView]);

  useEffect(()=>{
    const map=mapInstanceRef.current;if(!map)return;
    terrainRasterRef.current?.remove();terrainRasterRef.current=null;
    if(terrainOverlay){const [w,s,e,n]=terrainOverlay.bbox;terrainRasterRef.current=L.imageOverlay(terrainOverlay.url,[[s,w],[n,e]],{opacity:.85,zIndex:250,interactive:false}).addTo(map);}
  },[terrainOverlay]);

  // Drawing tools own double-click; switching tools always starts a fresh draft.
  useEffect(()=>{
    (window as any).__SAS_SELECTION_MODE=selectionMode;
    const map=mapInstanceRef.current;
    map?.getContainer().classList.toggle('sas-draw-cursor',selectionMode!=='none');
    if(selectionMode!=='none')map?.closePopup();
    if(['polyline','polygon'].includes(selectionMode))map?.doubleClickZoom.disable();else map?.doubleClickZoom.enable();
    polyPointsRef.current=[];rectStartPointRef.current=null;isDrawingRectRef.current=false;
    if(selectionMode==='polyline')callbacksRef.current.onSetMeasurementPoints([]);
    if(selectionMode==='polygon')callbacksRef.current.onSetPolygon([]);
  },[selectionMode]);

  // Both online and offline map display read the shared disk cache.
  const createOfflineAwareTileLayer = (
    sourceId: string,
    urlTemplate: string,
    options: L.TileLayerOptions & { isOfflineMode: boolean; isOverlay?: boolean }
  ) => {
    const DiskTileLayer = L.TileLayer.extend({
      createTile: function(this:L.TileLayer,coords:L.Coords,done:(error:any,tile:HTMLElement)=>void):HTMLElement {
        const container=document.createElement('img'),controller=new AbortController();
        container.className=options.isOverlay?'sas-map-overlay-tile':'sas-map-base-tile';
        container.alt='';container.setAttribute('role','presentation');
        let objectUrl:string|undefined,completed=false;
        const releaseUrl=()=>{if(objectUrl){URL.revokeObjectURL(objectUrl);objectUrl=undefined;}};
        const release=()=>{controller.abort();container.onload=null;container.onerror=null;releaseUrl();};
        (container as any).__releaseTile=release;
        const finish=()=>{if(!completed&&!controller.signal.aborted){completed=true;done(null,container);}};
        const missing=()=>{
          if(controller.signal.aborted)return;
          container.onload=null;container.onerror=null;releaseUrl();
          // Leaflet expects a tile image; a wrapper div caused seams at fractional DPI.
          if(!options.isOverlay)container.src=createOfflinePlaceholderCanvas(coords).toDataURL('image/png');
          else container.style.visibility='hidden';
          finish();
        };
        container.onload=()=>{releaseUrl();finish();};container.onerror=missing;
        void getMapTileBlob(sourceId,coords,this.getTileUrl(coords),options.isOfflineMode,controller.signal).then(blob=>{
          if(controller.signal.aborted)return;
          if(!blob){missing();return;}
          objectUrl=URL.createObjectURL(blob);container.src=objectUrl;
        }).catch(missing);
        return container;
      }
    });
    const layer=new (DiskTileLayer as any)(urlTemplate,options) as L.TileLayer;
    layer.on('tileunload',(event:L.TileEvent)=>{(event.tile as any).__releaseTile?.();});
    return layer;
  };

  // 2. Base Tile Layer Updating
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    if (baseTileLayerRef.current) {
      map.removeLayer(baseTileLayerRef.current);
    }

    const subdomains = currentSource.subdomains && currentSource.subdomains.length > 0
      ? currentSource.subdomains
      : ['a', 'b', 'c'];

    // User-added custom sources render directly (not via the disk tile cache).
    let newLayer: L.TileLayer;
    if (currentSource.custom) {
      const common = { pane: 'sas-base', maxZoom: currentSource.max_zoom || 19, attribution: currentSource.attribution || '', className: 'sas-map-base-tile' };
      if (currentSource.kind === 'wms') {
        const base = currentSource.url_template.split('?')[0];
        newLayer = L.tileLayer.wms(base, { layers: currentSource.wmsLayers || '', format: 'image/png', transparent: false, version: '1.3.0', ...common } as any);
      } else {
        newLayer = L.tileLayer(currentSource.url_template, { subdomains, tms: currentSource.kind === 'tms', ...common } as any);
      }
    } else {
      newLayer = createOfflineAwareTileLayer(currentSource.id, currentSource.url_template, {
        subdomains,
        pane: 'sas-base',
        maxZoom: currentSource.max_zoom || 21,
        attribution: currentSource.attribution || '',
        isOfflineMode
      });
    }

    newLayer.addTo(map);
    baseTileLayerRef.current = newLayer;
  }, [currentSource, isOfflineMode]);

  // Clip the compare pane to the right of the divider. Leaflet panes are 0×0,
  // so a percentage clip-path collapses to nothing; use pixel `clip` in the
  // pane's own (layer-point) coordinate space, which accounts for the map pan.
  const applyCompareClip = (map: L.Map, ratio: number) => {
    const pane = map.getPane('sas-compare');
    if (!pane) return;
    const size = map.getSize();
    const tl = map.containerPointToLayerPoint(L.point(0, 0));
    const br = map.containerPointToLayerPoint(L.point(size.x, size.y));
    const divX = map.containerPointToLayerPoint(L.point(ratio * size.x, 0)).x;
    pane.style.clipPath = 'none';
    pane.style.clip = `rect(${tl.y}px, ${br.x}px, ${br.y}px, ${divX}px)`;
  };

  // Swipe comparison: a second source shown over the right of a draggable divider.
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;
    const pane = map.getPane('sas-compare');
    if (compareLayerRef.current) { map.removeLayer(compareLayerRef.current); compareLayerRef.current = null; }
    if (pane) { pane.style.clip = ''; pane.style.clipPath = 'none'; }
    if (!compareSource) return;
    const sub = compareSource.subdomains && compareSource.subdomains.length > 0 ? compareSource.subdomains : ['a', 'b', 'c'];
    const common: any = { pane: 'sas-compare', maxZoom: compareSource.max_zoom || 21, attribution: '' };
    let layer: L.TileLayer;
    if (compareSource.custom) {
      if (compareSource.kind === 'wms') layer = L.tileLayer.wms(compareSource.url_template.split('?')[0], { layers: compareSource.wmsLayers || '', format: 'image/png', transparent: false, version: '1.3.0', ...common });
      else layer = L.tileLayer(compareSource.url_template, { subdomains: sub, tms: compareSource.kind === 'tms', ...common });
    } else {
      layer = createOfflineAwareTileLayer(compareSource.id, compareSource.url_template, { subdomains: sub, isOfflineMode, ...common });
    }
    layer.addTo(map);
    compareLayerRef.current = layer;
    const reclip = () => applyCompareClip(map, swipeRatioRef.current);
    reclip();
    map.on('move zoom moveend zoomend viewreset resize', reclip);
    return () => {
      map.off('move zoom moveend zoomend viewreset resize', reclip);
      if (compareLayerRef.current) { map.removeLayer(compareLayerRef.current); compareLayerRef.current = null; }
      if (pane) { pane.style.clip = ''; pane.style.clipPath = 'none'; }
    };
  }, [compareSource, isOfflineMode]);

  // Re-clip live while the divider handle is dragged.
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (map && compareSource) applyCompareClip(map, swipeRatio);
  }, [swipeRatio, compareSource]);

  // 3. Overlays Updating
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    // Reset overlay layers when switching offline/online to apply strict cache policy
    overlayLayersRef.current.forEach((layer) => {
      map.removeLayer(layer);
    });
    overlayLayersRef.current.clear();

    // Google Hybrid Labels & Roads Overlay
    const hybridId = 'google_hybrid_overlay';
    if (activeOverlays.has(hybridId)) {
      const l = createOfflineAwareTileLayer(hybridId, 'https://mt{s}.google.com/vt/lyrs=h&x={x}&y={y}&z={z}', {
        subdomains: ['0', '1', '2', '3'],
        pane: 'sas-overlays',
        maxZoom: 22,
        opacity: 0.95,
        isOfflineMode,
        isOverlay: true
      }).addTo(map);
      overlayLayersRef.current.set(hybridId, l);
    }

    // OpenSeaMap Marine Overlay
    const seaId = 'openseamap';
    if (activeOverlays.has(seaId)) {
      const l = createOfflineAwareTileLayer(seaId, 'https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png', {
        pane: 'sas-overlays',
        maxZoom: 18,
        opacity: 0.9,
        isOfflineMode,
        isOverlay: true
      }).addTo(map);
      overlayLayersRef.current.set(seaId, l);
    }

    // Custom Tile Grid Overlay
    const hasTileGrid = activeOverlays.has('grid_tiles');
    const hasDegreeGrid = activeOverlays.has('grid_degree');

    if (gridLayerRef.current) {
      map.removeLayer(gridLayerRef.current);
      gridLayerRef.current = null;
    }

    if (hasTileGrid || hasDegreeGrid) {
      const CustomGrid = L.GridLayer.extend({
        createTile: function (coords: L.Coords) {
          const tile = document.createElement('div');
          tile.style.outline = '1px dashed rgba(59, 130, 246, 0.45)';
          tile.style.backgroundColor = 'transparent';
          tile.style.width = '256px';
          tile.style.height = '256px';
          tile.style.position = 'relative';

          if (hasTileGrid) {
            const label = document.createElement('div');
            label.style.position = 'absolute';
            label.style.top = '4px';
            label.style.left = '4px';
            label.style.padding = '2px 4px';
            label.style.background = 'rgba(15, 23, 42, 0.85)';
            label.style.border = '1px solid rgba(59, 130, 246, 0.6)';
            label.style.color = '#38bdf8';
            label.style.fontSize = '10px';
            label.style.fontFamily = 'monospace';
            label.style.borderRadius = '3px';
            label.style.pointerEvents = 'none';
            label.textContent = `Z:${coords.z} X:${coords.x} Y:${coords.y}`;
            tile.appendChild(label);
          }

          if (hasDegreeGrid) {
            // Draw coordinate line labels
            const gridLabel = document.createElement('div');
            gridLabel.style.position = 'absolute';
            gridLabel.style.bottom = '4px';
            gridLabel.style.right = '4px';
            gridLabel.style.padding = '1px 3px';
            gridLabel.style.background = 'rgba(0, 0, 0, 0.65)';
            gridLabel.style.color = '#fbbf24';
            gridLabel.style.fontSize = '9px';
            gridLabel.style.fontFamily = 'monospace';
            gridLabel.style.borderRadius = '2px';
            gridLabel.style.pointerEvents = 'none';
            gridLabel.textContent = `WGS84`;
            tile.appendChild(gridLabel);
          }

          return tile;
        }
      });
      const gLayer = new (CustomGrid as any)({ pane: 'sas-overlays' });
      gLayer.addTo(map);
      gridLayerRef.current = gLayer;
    }
  }, [activeOverlays, isOfflineMode]);

  // 4. Render Selections & Measurements
  useEffect(() => {
    const group = selectionLayerGroupRef.current;
    if (!group) return;

    group.clearLayers();

    // Render Bounding Box
    if (selectedBbox) {
      const bounds = L.latLngBounds(
        [selectedBbox.min_lat, selectedBbox.min_lon],
        [selectedBbox.max_lat, selectedBbox.max_lon]
      );
      L.rectangle(bounds, {
        color: '#f59e0b',
        weight: 2.5,
        fillColor: '#f59e0b',
        fillOpacity: 0.15,
        dashArray: '6, 4'
      }).addTo(group);

      // Add Corner Badges
      L.marker([selectedBbox.max_lat, selectedBbox.min_lon], {
        icon: L.divIcon({
          className: 'custom-corner-icon',
          html: '<div style="background:#f59e0b;color:#000;padding:1px 4px;font-size:9px;font-weight:bold;border-radius:2px;">NW Corner</div>'
        })
      }).addTo(group);
    }

    // Render Selected Polygon
    if (selectedPolygon && selectedPolygon.length > 1) {
      L.polygon(selectedPolygon, {
        color: '#06b6d4',
        weight: 2.5,
        fillColor: '#06b6d4',
        fillOpacity: 0.2
      }).addTo(group);

      // Vertices markers
      selectedPolygon.forEach((pt, idx) => {
        L.circleMarker(pt, {
          radius: 4,
          color: '#0891b2',
          fillColor: '#fff',
          fillOpacity: 1,
          weight: 2
        }).addTo(group);
      });
    }

    // Render Measurement Path
    if (measurementPoints && measurementPoints.length > 0) {
      L.polyline(measurementPoints, {
        color: '#10b981',
        weight: 3,
        dashArray: '4, 4', interactive:false
      }).addTo(group);

      const measured=pathMeasurement(measurementPoints);
      measurementPoints.forEach((pt, idx) => {
        L.circleMarker(pt, {
          radius: 5, interactive:false,
          color: '#059669',
          fillColor: '#34d399',
          fillOpacity: 1,
          weight: 2
        }).addTo(group);
      });
    }
  }, [selectedBbox, selectedPolygon, measurementPoints]);

  // 5. Render Marks
  useEffect(() => {
    const group = marksLayerGroupRef.current;
    if (!group) return;

    group.clearLayers();

    marks.forEach((mark) => {
      if (mark.hidden) return;
      const color = /^#[0-9a-f]{3,8}$/i.test(mark.color||'')?mark.color!:'#ef4444';
      const escape=(value:unknown)=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
      const markName=escape(mark.name),description=escape(mark.description);

      if (mark.type === 'point' && Array.isArray(mark.coords) && mark.coords.length >= 2) {
        const [lon, lat] = mark.coords;
        const iconHtml = `
          <div style="background:${color};border:2px solid #fff;border-radius:50%;width:18px;height:18px;box-shadow:0 0 6px rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;cursor:pointer;">
            <div style="background:#fff;border-radius:50%;width:6px;height:6px;"></div>
          </div>
        `;
        const icon = L.divIcon({
          className: 'sas-pin',
          html: iconHtml,
          iconSize: [18, 18],
          iconAnchor: [9, 9]
        });

        const m = L.marker([lat, lon], { icon, interactive:selectionMode==='none' }).addTo(group);
        if (showLabels && mark.name) m.bindTooltip(markName, { permanent: true, direction: 'top', className: 'sas-feature-label', offset: [0, -8] });
        m.bindPopup(`
          <div style="font-family:Cairo,sans-serif;font-size:12px;color:#0f172a;">
            <strong style="color:${color};font-size:13px;">${markName}</strong>
            ${mark.description ? `<p style="margin:4px 0 0 0;">${description}</p>` : ''}
            <div style="margin-top:6px;font-size:10px;color:#64748b;font-family:monospace;">
              ${lat.toFixed(5)}°, ${lon.toFixed(5)}°
            </div>
          </div>
        `);
        m.on('click', () => onSelectMark?.(mark));
      } else if (mark.type === 'linestring' && Array.isArray(mark.coords)) {
        const pts = mark.coords.map((c: [number, number]) => [c[1], c[0]] as [number, number]);
        const segmented=mark.trackSegments?.flat();const coherent=segmented?.length===mark.coords.length&&segmented.every((p,i)=>p.lon===mark.coords[i][0]&&p.lat===mark.coords[i][1]);
        const poly = L.polyline(coherent?mark.trackSegments!.map(seg=>seg.map(p=>[p.lat,p.lon] as [number,number])):pts, { color, weight: mark.weight || 3.5, opacity: 0.85, interactive:selectionMode==='none' }).addTo(group);
        poly.bindPopup(`<strong>${markName}</strong><br/>${description}`);
        if (showLabels && mark.name) poly.bindTooltip(markName, { permanent: true, direction: 'center', className: 'sas-feature-label' });
      } else if (mark.type === 'polygon' && Array.isArray(mark.coords)) {
        const outer = Array.isArray(mark.coords[0][0]) ? mark.coords[0] : mark.coords;
        const pts = outer.map((c: [number, number]) => [c[1], c[0]] as [number, number]);
        const poly = L.polygon(pts, { color, weight: mark.weight || 2.5, fillColor: color, fillOpacity: 0.25, interactive:selectionMode==='none' }).addTo(group);
        poly.bindPopup(`<strong>${markName}</strong><br/>${description}`);
        if (showLabels && mark.name) poly.bindTooltip(markName, { permanent: true, direction: 'center', className: 'sas-feature-label' });
      }
    });
  }, [marks,selectionMode,showLabels]);

  // 6. Render GPS Simulation
  useEffect(() => {
    const group = gpsLayerGroupRef.current;
    if (!group) return;

    group.clearLayers();

    if (gpsTrack && gpsTrack.length > 1) {
      L.polyline(gpsTrack, {
        color: '#06b6d4',
        weight: 3,
        opacity: 0.8
      }).addTo(group);
    }

    if (gpsPosition) {
      const arrowHtml = `
        <div style="transform: rotate(${gpsPosition.bearing}deg); display:flex; align-items:center; justify-content:center;">
          <div style="width: 0; height: 0; border-left: 8px solid transparent; border-right: 8px solid transparent; border-bottom: 20px solid #06b6d4; filter: drop-shadow(0 0 3px rgba(0,0,0,0.8));"></div>
        </div>
      `;
      const icon = L.divIcon({
        className: 'gps-cursor',
        html: arrowHtml,
        iconSize: [24, 24],
        iconAnchor: [12, 12]
      });

      L.marker([gpsPosition.lat, gpsPosition.lon], { icon }).addTo(group);
    }
  }, [gpsPosition, gpsTrack]);

  // 7. Render Contours
  useEffect(() => {
    const group = contourLayerGroupRef.current;
    if (!group) return;

    group.clearLayers();

    if (contourDisplay.visible && contourGeoJson && contourGeoJson.features) {
      L.geoJSON(contourGeoJson, {
        filter: (feature: any) => !contourDisplay.majorOnly || Boolean(feature?.properties?.is_index),
        style: (feature: any) => ({
          color: feature?.properties?.color || '#b45309',
          weight: feature?.properties?.stroke_width || 1.5,
          opacity: contourDisplay.opacity
        }),
        onEachFeature: (feature: any, layer: L.Layer) => {
          if (typeof feature?.properties?.elevation === 'number') {
            layer.bindTooltip(`${feature.properties.elevation}m`, {
              sticky: true,
              className: 'contour-tooltip'
            });
          }
        }
      }).addTo(group);
    }
  }, [contourGeoJson, contourDisplay]);

  return (
    <div className="relative w-full h-full overflow-hidden flex sas-map-frame" dir="ltr">
      {settings.showZoomRail&&<aside className="desktop-zoom-rail" aria-label={settings.language==='ar'?'مستوى التكبير':'Zoom level'}>
        <button onClick={()=>mapInstanceRef.current?.zoomIn()} aria-label={settings.language==='ar'?'تكبير':'Zoom in'}>+</button>
        <input aria-label={settings.language==='ar'?'التكبير':'Zoom'} type="range" min="1" max="21" step="1" value={liveZoom} onChange={e=>mapInstanceRef.current?.setZoom(Number(e.target.value),{animate:settings.animations})}/>
        <button onClick={()=>mapInstanceRef.current?.zoomOut()} aria-label={settings.language==='ar'?'تصغير':'Zoom out'}>−</button><strong>z{liveZoom}</strong>
      </aside>}
      <div className="relative flex-1 min-w-0 h-full">
        <div ref={mapContainerRef} className="w-full h-full z-10" />
        {compareSource && (
          <>
            <div className="absolute top-0 bottom-0 z-[400] w-0.5 bg-white/90 shadow pointer-events-none" style={{ left: `${swipeRatio * 100}%` }} />
            <div
              role="separator"
              aria-label={settings.language === 'ar' ? 'مقبض المقارنة' : 'Swipe handle'}
              onPointerDown={e => (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)}
              onPointerMove={e => { if (e.buttons !== 1) return; const rect = mapContainerRef.current?.getBoundingClientRect(); if (!rect) return; setSwipeRatio(Math.min(0.98, Math.max(0.02, (e.clientX - rect.left) / rect.width))); }}
              className="absolute top-1/2 -translate-y-1/2 -ml-3.5 z-[500] w-7 h-11 rounded bg-white shadow-lg cursor-ew-resize flex items-center justify-center text-slate-700 text-sm select-none"
              style={{ left: `${swipeRatio * 100}%` }}
            >⇔</div>
          </>
        )}
      </div>
    </div>
  );
};
