import {projectWgsUtm,projectNordSahara,projectedText} from './coordinateReference';
import { CoordinatesState } from '../types';

export function lonLatToTile(lon: number, lat: number, zoom: number): [number, number] {
  const clampedLat = Math.max(Math.min(lat, 85.05112878), -85.05112878);
  const n = Math.pow(2, zoom);
  const x = Math.floor(((lon + 180.0) / 360.0) * n);
  const latRad = (clampedLat * Math.PI) / 180.0;
  const y = Math.floor(((1.0 - Math.asinh(Math.tan(latRad)) / Math.PI) / 2.0) * n);
  const maxIdx = (1 << zoom) - 1;
  return [Math.max(0, Math.min(x, maxIdx)), Math.max(0, Math.min(y, maxIdx))];
}

export function tileToLonLat(x: number, y: number, zoom: number): [number, number] {
  const n = Math.pow(2, zoom);
  const lon = (x / n) * 360.0 - 180.0;
  const latRad = Math.atan(Math.sinh(Math.PI * (1.0 - (2.0 * y) / n)));
  const lat = (latRad * 180.0) / Math.PI;
  return [lon, lat];
}

export function formatDMS(deg: number, isLat: boolean = true): string {
  const hemi = isLat ? (deg >= 0 ? 'N' : 'S') : (deg >= 0 ? 'E' : 'W');
  const dAbs = Math.abs(deg);
  const d = Math.floor(dAbs);
  const m = Math.floor((dAbs - d) * 60);
  const s = ((dAbs - d - m / 60) * 3600).toFixed(2);
  return `${d}°${m.toString().padStart(2, '0')}'${s.padStart(5, '0')}"${hemi}`;
}

export function formatUTM(lat:number,lon:number):string {
  const value=projectWgsUtm(lat,lon);return value?projectedText(value):'—';
}

export function formatUtmNordSahara(lat:number,lon:number,zone=0):string {
  const value=projectNordSahara(lat,lon,zone);return value?projectedText(value,'UTM NS'):'—';
}

export function getFullCoordinateState(lat: number, lon: number, zoom: number): CoordinatesState {
  const [tileX, tileY] = lonLatToTile(lon, lat, zoom);
  const mercatorX = lon * (Math.PI * 6378137.0 / 180.0);
  const clampedLat = Math.max(Math.min(lat, 85.05112878), -85.05112878);
  const mercatorY = Math.log(Math.tan((90.0 + clampedLat) * Math.PI / 360.0)) * 6378137.0;

  return {
    lat: Number(lat.toFixed(6)),
    lon: Number(lon.toFixed(6)),
    zoom,
    tileX,
    tileY,
    dmsLat: formatDMS(lat, true),
    dmsLon: formatDMS(lon, false),
    utm: formatUTM(lat, lon),
    utmNordSahara: formatUtmNordSahara(lat, lon),
    mercatorX: Math.round(mercatorX),
    mercatorY: Math.round(mercatorY)
  };
}

export function calculateTilesCountInBbox(
  minLon: number,
  minLat: number,
  maxLon: number,
  maxLat: number,
  zooms: number[]
): { totalTiles: number; zoomBreakdown: { zoom: number; tiles: number; xCount: number; yCount: number }[] } {
  let totalTiles = 0;
  const zoomBreakdown = [];

  for (const z of zooms) {
    const [xMin, yMax] = lonLatToTile(minLon, minLat, z);
    const [xMax, yMin] = lonLatToTile(maxLon, maxLat, z);

    const xStart = Math.min(xMin, xMax);
    const xEnd = Math.max(xMin, xMax);
    const yStart = Math.min(yMin, yMax);
    const yEnd = Math.max(yMin, yMax);

    const xCount = xEnd - xStart + 1;
    const yCount = yEnd - yStart + 1;
    const count = xCount * yCount;

    totalTiles += count;
    zoomBreakdown.push({ zoom: z, tiles: count, xCount, yCount });
  }

  return { totalTiles, zoomBreakdown };
}
