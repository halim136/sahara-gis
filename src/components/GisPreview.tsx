import {useEffect} from 'react';
import L from 'leaflet';
export function GisPreview({value,onChange}:{value:any;onChange:(v:any)=>void}){
 useEffect(()=>{const map=(window as any).__SAS_MAP;if(!map||!value)return;const group=L.featureGroup().addTo(map);
 const layer=L.geoJSON(value,{style:(f:any)=>({color:f?.properties?.cached===true?'#13a35c':f?.properties?.cached===false?'#e34c4c':'#00bddd',weight:2,fillOpacity:.15})}).addTo(group);
 const features=value.features||[];
 if(features.length===1&&features[0].geometry?.type==='Polygon'&&features[0].properties?.review_required){const ring=features[0].geometry.coordinates[0];ring.slice(0,-1).forEach((point:number[],i:number)=>{const marker=L.marker([point[1],point[0]],{draggable:true,icon:L.divIcon({className:'building-vertex',iconSize:[12,12],iconAnchor:[6,6]})}).addTo(group);marker.on('dragend',()=>{const clone=structuredClone(value);const pos=marker.getLatLng();clone.features[0].geometry.coordinates[0][i]=[pos.lng,pos.lat];if(i===0)clone.features[0].geometry.coordinates[0][ring.length-1]=[pos.lng,pos.lat];onChange(clone);});});}
 return()=>{group.remove();};
 },[value,onChange]);return null;
}
