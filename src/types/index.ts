export interface MapSource {
  id: string;
  name: string;
  category: 'Satellite' | 'Hybrid' | 'Map' | 'Topographic' | 'Terrain' | 'Overlay' | 'Grid';
  url_template: string;
  subdomains?: string[];
  max_zoom: number;
  projection?: string;
  format?: string;
  attribution?: string;
  is_overlay?: boolean;
  custom?: boolean;
  kind?: 'xyz' | 'tms' | 'wms';
  wmsLayers?: string;
  is_grid?: boolean;
}

export interface CoordinatesState {
  lat: number;
  lon: number;
  zoom: number;
  tileX: number;
  tileY: number;
  dmsLat: string;
  dmsLon: string;
  utm: string;
  utmNordSahara?: string;
  mercatorX: number;
  mercatorY: number;
}

export type SelectionMode = 'none' | 'rect' | 'polygon' | 'polyline' | 'radius';

export interface BoundingBox {
  min_lon: number;
  min_lat: number;
  max_lon: number;
  max_lat: number;
}

export interface MarkItem {
  id: string;
  name: string;
  type: 'point' | 'linestring' | 'polygon';
  coords: any; // [lon, lat] or [[lon, lat], ...]
  description?: string;
  color?: string;
  category?: string;
  timestamp?: string;
  gpxKind?: 'wpt'|'trk'|'rte';
  trackSegments?: {lon:number;lat:number;ele?:number;time?:string;hdop?:number}[][];
  properties?: Record<string, any>;
  hidden?: boolean;
  weight?: number;
}

export interface MeasurementData {
  points: [number, number][]; // [lat, lon]
  lengthMeters: number;
  lengthKm: number;
  areaSqMeters: number;
  areaHectares: number;
  areaSqKm: number;
  segments: { from: [number, number]; to: [number, number]; distM: number; bearing: number }[];
}

export interface ElevationSample {
  index: number;
  distance_m: number;
  distance_km: number;
  lat: number;
  lon: number;
  elevation_m: number;
}

export interface DownloadJobState {
  job_id: string;
  source_id: string;
  bbox: [number, number, number, number];
  zooms: number[];
  storage_type: string;
  total_tiles: number;
  downloaded: number;
  cached: number;
  failed: number;
  bytes_downloaded: number;
  progress_percent: number;
  speed_kb_s: number;
  elapsed_s: number;
  status: 'idle' | 'running' | 'paused' | 'completed' | 'cancelled' | 'error';
  error?: string;
}
