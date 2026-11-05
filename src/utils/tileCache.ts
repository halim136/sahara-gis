import { storeAppValue } from './portableState';
/**
 * Tile Cache & Offline Mode Manager
 * Uses the shared disk cache for map tiles, offline mode enforcement,
 * and zero-network placeholder generation.
 */

import L from 'leaflet';
import { MapSource } from '../types';
import { lonLatToTile } from './geoUtils';

export const SAS_TILE_CACHE_NAME = 'sas-planet-tile-cache-v1';
export const OFFLINE_MODE_STORAGE_KEY = 'sas_offline_mode';

/**
 * Check if Offline Mode is currently enabled in localStorage
 */
export function getStoredOfflineMode(): boolean {
  try {
    return localStorage.getItem(OFFLINE_MODE_STORAGE_KEY) === 'true';
  } catch (_) {
    return false;
  }
}

/**
 * Persist Offline Mode preference
 */
export function setStoredOfflineMode(enabled: boolean): void {
  try {
    storeAppValue(OFFLINE_MODE_STORAGE_KEY, String(enabled));
    window.dispatchEvent(
      new CustomEvent('sas:offline-mode-changed', { detail: { enabled } })
    );
  } catch (_) {}
}

/**
 * Get statistics of tiles cached in browser CacheStorage
 */
export async function getBrowserCacheStats(): Promise<{
  count: number;
  estimatedSizeMb: number;
}> {
  if (typeof window === 'undefined' || !('caches' in window)) {
    return { count: 0, estimatedSizeMb: 0 };
  }

  try {
    const cache = await caches.open(SAS_TILE_CACHE_NAME);
    const keys = await cache.keys();
    const count = keys.length;
    // Average map tile (PNG/JPEG) is ~18KB
    const estimatedSizeMb = Number(((count * 18.5) / 1024).toFixed(2));
    return { count, estimatedSizeMb };
  } catch (_) {
    return { count: 0, estimatedSizeMb: 0 };
  }
}

/**
 * Clear all browser-cached map tiles
 */
export async function clearBrowserTileCache(): Promise<boolean> {
  if (typeof window === 'undefined' || !('caches' in window)) {
    return false;
  }

  try {
    const deleted = await caches.delete(SAS_TILE_CACHE_NAME);
    window.dispatchEvent(new CustomEvent('sas:cache-cleared'));
    return deleted;
  } catch (_) {
    return false;
  }
}

/**
 * Generate a visual offline placeholder canvas when a tile is not available in local cache
 * and Offline Mode is active. Strictly prevents any external network request!
 */
export function createOfflinePlaceholderCanvas(coords: {
  x: number;
  y: number;
  z: number;
}): HTMLCanvasElement {
  const canvas = document.createElement('canvas');
  canvas.width = 256;
  canvas.height = 256;
  const ctx = canvas.getContext('2d');

  if (!ctx) return canvas;

  // Background - SAS Planet Dark Grid Theme
  ctx.fillStyle = '#090d16';
  ctx.fillRect(0, 0, 256, 256);

  // Grid border
  ctx.strokeStyle = '#1e293b';
  ctx.lineWidth = 1;
  ctx.strokeRect(0.5, 0.5, 255, 255);

  // Subtle diagonal cross
  ctx.strokeStyle = 'rgba(30, 41, 59, 0.45)';
  ctx.lineWidth = 1;
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.lineTo(256, 256);
  ctx.moveTo(256, 0);
  ctx.lineTo(0, 256);
  ctx.stroke();
  ctx.setLineDash([]);

  // Center Offline Warning Card
  ctx.fillStyle = 'rgba(15, 23, 42, 0.92)';
  ctx.fillRect(28, 86, 200, 84);

  // Border of card
  ctx.strokeStyle = '#d97706'; // Amber-600
  ctx.lineWidth = 1.5;
  ctx.strokeRect(28, 86, 200, 84);

  // Offline Badge / Icon
  ctx.fillStyle = '#f59e0b'; // Amber-500
  ctx.font = 'bold 12px "Cairo", sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText('⚡ وضع أوفلاين (غير متصل)', 128, 112);

  ctx.fillStyle = '#cbd5e1'; // Slate-300
  ctx.font = '10px "Cairo", sans-serif';
  ctx.fillText('البلاطة غير مخزنة محلياً', 128, 132);

  ctx.fillStyle = '#64748b'; // Slate-500
  ctx.font = '10px monospace';
  ctx.fillText(`Z:${coords.z} X:${coords.x} Y:${coords.y}`, 128, 154);

  return canvas;
}

/** Every displayed/downloaded tile is persisted by the local server in cache_gmt. */
export function diskTileUrl(source:string,coords:{x:number;y:number;z:number},offline=false):string {
  return '/api/maps/tile?'+new URLSearchParams({source,z:String(coords.z),x:String(coords.x),y:String(coords.y),offline:offline?'1':'0'});
}
async function persistLegacyTile(source:string,coords:{x:number;y:number;z:number},blob:Blob){
  try{
    const bytes=new Uint8Array(await blob.arrayBuffer());if(!bytes.length||bytes.length>8*1024*1024)return;
    let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
    await fetch('/api/cache/tile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source,...coords,content:btoa(binary)})});
  }catch{}
}
export async function getMapTileBlob(source:string,coords:{x:number;y:number;z:number},legacyUrl:string,offline=false,signal?:AbortSignal):Promise<Blob|null>{
  try{
    const response=await fetch(diskTileUrl(source,coords,offline),{signal,cache:'no-store'});
    if(response.ok)return await response.blob();
  }catch(error){if(signal?.aborted)throw error;}
  // Preserve maps saved by previous versions, copying each recovered tile onto disk.
  if('caches' in window)try{
    const cache=await caches.open(SAS_TILE_CACHE_NAME),response=await cache.match(legacyUrl);
    if(response){const blob=await response.blob();if(blob.size){void persistLegacyTile(source,coords,blob);return blob;}}
  }catch{}
  return null;
}
export async function cacheCurrentViewportTiles(map:L.Map,source:MapSource,onProgress?:(done:number,total:number)=>void):Promise<{total:number;saved:number;failed:number}>{
  if(!map||!source.url_template)return {total:0,saved:0,failed:0};
  const bounds=map.getBounds(),z=map.getZoom(),size=2**z;
  const [west,north]=lonLatToTile(bounds.getWest(),Math.min(85.05112878,bounds.getNorth()),z);
  const [east,south]=lonLatToTile(bounds.getEast(),Math.max(-85.05112878,bounds.getSouth()),z);
  const minX=Math.min(west,east),maxX=Math.min(minX+size-1,Math.max(west,east));
  const minY=Math.max(0,Math.min(north,south)),maxY=Math.min(size-1,Math.max(north,south));
  const tiles:{x:number;y:number;z:number}[]=[];
  for(let x=minX;x<=maxX;x++)for(let y=minY;y<=maxY;y++)tiles.push({x:((x%size)+size)%size,y,z});
  let saved=0,failed=0;
  for(let i=0;i<tiles.length;i+=6)await Promise.all(tiles.slice(i,i+6).map(async coords=>{
    try{const res=await fetch(diskTileUrl(source.id,coords,getStoredOfflineMode()),{cache:'no-store'});if(res.ok){await res.arrayBuffer();saved++;}else failed++;}catch{failed++;}
    onProgress?.(saved+failed,tiles.length);
  }));
  return {total:tiles.length,saved,failed};
}
