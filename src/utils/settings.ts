import { storeAppValue } from './portableState';
export interface AppSettings {
  coordinateSystem: 'dms' | 'decimal' | 'utm_wgs84' | 'utm_nord_sahara';
  nordSaharaZone: 0 | 29 | 30 | 31 | 32;
  theme: 'classic' | 'dark';
  language: 'ar' | 'en';
  defaultSource: string;
  wheelZoom: boolean;
  animations: boolean;
  showZoomRail: boolean;
  showMapTools: boolean;
  showStatusBar: boolean;
  rememberView: boolean;
  contourInterval: number;
  terrainResolution: number;
  terrainSource: 'terrain' | 'srtm';
  azimuth: number;
  altitude: number;
  zFactor: number;
}
export const DEFAULT_SETTINGS: AppSettings = {
  coordinateSystem:'dms', nordSaharaZone:0,
  theme: 'classic', language: 'ar', defaultSource: 'google_sat', wheelZoom: true, animations: false,
  showZoomRail: true, showMapTools: false, showStatusBar: true, rememberView: true,
  contourInterval: 25, terrainResolution: 256, terrainSource: 'terrain', azimuth:315, altitude:45, zFactor:1
};
export function normalizeSettings(raw: unknown): AppSettings {
  const r = raw && typeof raw === 'object' ? raw as Record<string,unknown> : {};
  const d = {...DEFAULT_SETTINGS};
  for (const k of ['wheelZoom','animations','showZoomRail','showMapTools','showStatusBar','rememberView'] as const) if (typeof r[k] === 'boolean') d[k] = r[k];
  if (['dms','decimal','utm_wgs84','utm_nord_sahara'].includes(String(r.coordinateSystem))) d.coordinateSystem = r.coordinateSystem as AppSettings['coordinateSystem'];
  if ([0,29,30,31,32].includes(Number(r.nordSaharaZone)) && typeof r.nordSaharaZone==='number') d.nordSaharaZone = r.nordSaharaZone as AppSettings['nordSaharaZone'];
  if (r.theme === 'dark' || r.theme === 'classic') d.theme = r.theme;
  if (r.language === 'ar' || r.language === 'en') d.language = r.language;
  if (['google_sat','google_hybrid','esri_satellite','osm','opentopomap','carto_dark','yandex_sat'].includes(String(r.defaultSource))) d.defaultSource = String(r.defaultSource);
  if (r.terrainSource === 'terrain' || r.terrainSource === 'srtm') d.terrainSource = r.terrainSource;
  if ([5,10,20,25,50,100,250].includes(Number(r.contourInterval))) d.contourInterval = Number(r.contourInterval);
  if ([128,256,512].includes(Number(r.terrainResolution))) d.terrainResolution = Number(r.terrainResolution);
  for (const [key,min,max] of [['azimuth',0,360],['altitude',1,90],['zFactor',0.1,10]] as const) {
    if (typeof r[key] === 'number' && Number.isFinite(r[key]) && Number(r[key]) >= min && Number(r[key]) <= max) d[key] = Number(r[key]);
  }
  return d;
}
export function loadSettings(): AppSettings { try { return normalizeSettings(JSON.parse(localStorage.getItem('sas:settings:v1') || '{}')); } catch { return {...DEFAULT_SETTINGS}; } }
export function saveSettings(settings: AppSettings) { storeAppValue('sas:settings:v1',JSON.stringify(normalizeSettings(settings))); }
