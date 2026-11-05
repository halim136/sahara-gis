import { MapSource } from '../types';

// User-defined map sources (XYZ / TMS / WMS) stored per browser.
// These render as direct Leaflet layers, not through the disk tile cache.
const KEY = 'sas_custom_sources';

export function loadCustomSources(): MapSource[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const list = JSON.parse(raw);
    if (!Array.isArray(list)) return [];
    return list.filter((s) => s && typeof s.id === 'string' && typeof s.url_template === 'string')
      .map((s) => ({ ...s, custom: true } as MapSource));
  } catch {
    return [];
  }
}

export function saveCustomSources(list: MapSource[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    /* storage unavailable (private mode) — keep in memory only */
  }
}

export interface CustomSourceInput {
  name: string;
  kind: 'xyz' | 'tms' | 'wms';
  url: string;
  category?: MapSource['category'];
  maxZoom?: number;
  wmsLayers?: string;
  attribution?: string;
}

/** Validate and normalise a user source definition into a MapSource. */
export function buildCustomSource(input: CustomSourceInput): MapSource {
  const name = (input.name || '').trim();
  if (!name) throw new Error('Name is required.');
  const url = (input.url || '').trim();
  if (!/^https?:\/\//i.test(url)) throw new Error('URL must start with http:// or https://');
  const kind = input.kind;
  if (kind === 'xyz' || kind === 'tms') {
    if (!(url.includes('{x}') && url.includes('{y}') && url.includes('{z}')))
      throw new Error('XYZ/TMS URL must contain {x}, {y} and {z}.');
  } else if (kind === 'wms') {
    if (!(input.wmsLayers && input.wmsLayers.trim())) throw new Error('WMS needs a layer name.');
  } else {
    throw new Error('Unknown source type.');
  }
  const maxZoom = Math.min(23, Math.max(1, Math.round(Number(input.maxZoom) || 19)));
  return {
    id: 'custom_' + Math.random().toString(36).slice(2, 10),
    name,
    category: input.category || 'Satellite',
    url_template: url,
    max_zoom: maxZoom,
    format: 'png',
    attribution: (input.attribution || '').trim(),
    projection: 'EPSG:3857',
    custom: true,
    kind,
    wmsLayers: kind === 'wms' ? (input.wmsLayers || '').trim() : undefined,
  };
}
