import {useEffect,useState} from 'react';
import L from 'leaflet';
import {studioRequest} from './AdvancedGisWorkbench';
export type FieldLayer={id:string;name:string;kind:'image'|'wms'|'wmts'|'geojson'|'photo';visible:boolean;opacity:number;url?:string;original?:string;bbox?:number[];geojson?:any;lon?:number;lat?:number;direction?:number;captured?:string;serviceLayers?:string;matrixSet?:string;matrixPrefix?:string;style?:string;format?:string;metadata?:any;attribution?:string};
export type FieldState={layers:FieldLayer[];grid:{enabled:boolean;crs:string;step_m:number};marksVisible?:boolean};
export const emptyField:FieldState={layers:[],grid:{enabled:false,crs:'utm_ns_auto',step_m:1000},marksVisible:true};
function webUrl(value:string|undefined){if(!value)throw Error('Layer URL missing');if(value.startsWith('/exports/'))return value;const u=new URL(value);if(!['https:','http:'].includes(u.protocol)||u.username||u.password)throw Error('Use HTTP(S) URLs without credentials');return u.href;}
export function FieldLayers({state,offline,onError}:{state:FieldState;offline:boolean;onError:(e:string)=>void}){
 const [grid,setGrid]=useState<any>(null);
 useEffect(()=>{const map=(window as any).__SAS_MAP;if(!map||!state.grid.enabled){setGrid(null);return;}let timer:ReturnType<typeof setTimeout>,active=true,sequence=0;const refresh=()=>{clearTimeout(timer);timer=setTimeout(async()=>{const serial=++sequence,b=map.getBounds();try{const d=await studioRequest('field_grid',{bbox:[b.getWest(),b.getSouth(),b.getEast(),b.getNorth()],...state.grid});if(active&&serial===sequence){setGrid(d.geojson);onError('');}}catch(e:any){if(active&&serial===sequence){setGrid(null);onError(e.message);}}},300);};map.on('moveend',refresh);refresh();return()=>{active=false;clearTimeout(timer);map.off('moveend',refresh);};},[state.grid.enabled,state.grid.crs,state.grid.step_m]);
 useEffect(()=>{const map=(window as any).__SAS_MAP;if(!map)return;const mounted:L.Layer[]=[];const panes:string[]=[];
  state.layers.forEach((item,index)=>{if(!item.visible||offline&&['wms','wmts'].includes(item.kind))return;try{
   const pane='field-'+index;let node=map.getPane(pane);if(!node)node=map.createPane(pane);node.style.zIndex=String(320+index);node.style.opacity=String(item.opacity);panes.push(pane);let layer:L.Layer;
   if(item.kind==='image'){if(!item.bbox)throw Error('Raster bounds missing');const [w,s,e,n]=item.bbox;layer=L.imageOverlay(webUrl(item.url),[[s,w],[n,e]],{pane,interactive:false});}
   else if(item.kind==='wms')layer=L.tileLayer.wms(webUrl(item.url),{pane,layers:item.serviceLayers||'',format:item.format||'image/png',transparent:true,version:'1.1.1',crs:L.CRS.EPSG3857,maxZoom:22,attribution:item.attribution});
   else if(item.kind==='wmts'){
    const u=new URL(webUrl(item.url));for(const [k,v] of Object.entries({SERVICE:'WMTS',REQUEST:'GetTile',VERSION:'1.0.0',LAYER:item.serviceLayers||'',STYLE:item.style||'default',FORMAT:item.format||'image/png',TILEMATRIXSET:item.matrixSet||'GoogleMapsCompatible'}))u.searchParams.set(k,v);
    const sep=u.href.includes('?')?'&':'?';layer=L.tileLayer(u.href+sep+'TILEMATRIX='+encodeURIComponent(item.matrixPrefix||'')+'{z}&TILEROW={y}&TILECOL={x}',{pane,maxZoom:22,attribution:item.attribution});
   }else if(item.kind==='photo'){
    if(item.lon===undefined||item.lat===undefined)return;layer=L.marker([item.lat,item.lon],{pane,icon:L.divIcon({className:'field-photo-marker',html:'📷',iconSize:[28,28]})});const box=document.createElement('div'),title=document.createElement('strong'),image=document.createElement('img'),caption=document.createElement('p');title.textContent=item.name;image.src=webUrl(item.url);image.width=220;caption.textContent=[item.captured,item.direction===undefined?'':item.direction+'°'].filter(Boolean).join(' · ');box.append(title,image,caption);(layer as L.Marker).bindPopup(box);
   }else layer=L.geoJSON(item.geojson,{pane,style:f=>({color:typeof f?.properties?.slope_percent==='number'?(Math.abs(f.properties.slope_percent)>15?'#d54539':Math.abs(f.properties.slope_percent)>6?'#d59b21':'#168d73'):'#2268c8',weight:3}),pointToLayer:(_,ll)=>L.circleMarker(ll,{pane,radius:5})});
   layer.addTo(map);mounted.push(layer);
  }catch(e:any){onError(item.name+': '+e.message);}});
  return()=>{mounted.forEach(layer=>map.removeLayer(layer));panes.forEach(name=>{const node=map.getPane(name);if(node)node.style.opacity='1';});};
 },[state.layers,offline]);
 useEffect(()=>{const map=(window as any).__SAS_MAP;if(!map||!grid)return;const group=L.geoJSON(grid,{style:{color:'#873db0',weight:1,opacity:.75},onEachFeature:(f,layer)=>{const el=document.createElement('span');el.textContent=f.properties.label;layer.bindTooltip(el,{permanent:true,direction:'center',className:'sheet-label'});}}).addTo(map);return()=>{group.eachLayer(l=>l.unbindTooltip());group.remove();};},[grid]);
 return null;
}
