import React from 'react';
import {CoordinatesState} from '../types';
import type {AppSettings} from '../utils/settings';
import {projectWgsUtm,projectNordSahara,projectedText} from '../utils/coordinateReference';
import {Database,Globe,Wifi,WifiOff} from 'lucide-react';
interface Props {coords:CoordinatesState;settings:AppSettings;cacheStats:{total_tiles:number;total_size_mb:number};projectionName:string;lang:'ar'|'en';isOfflineMode?:boolean;onToggleOfflineMode?:()=>void;}
export const StatusBar:React.FC<Props>=({coords,settings,cacheStats,projectionName,lang,isOfflineMode=false,onToggleOfflineMode})=>{
 const ar=lang==='ar';const mpp=156543.03392*Math.cos(coords.lat*Math.PI/180)/2**coords.zoom;
 const ns=settings.coordinateSystem==='utm_nord_sahara';
 const projected=ns?projectNordSahara(coords.lat,coords.lon,settings.nordSaharaZone):settings.coordinateSystem==='utm_wgs84'?projectWgsUtm(coords.lat,coords.lon):null;
 const geographic=settings.coordinateSystem==='decimal'?coords.lat.toFixed(6)+'°, '+coords.lon.toFixed(6)+'°':coords.dmsLat+' · '+coords.dmsLon;
 const text=ns||settings.coordinateSystem==='utm_wgs84'?(projected?projectedText(projected,ns?'UTM Nord Sahara 1959':'UTM WGS84'):(ar?'الموقع خارج نطاق النظام المختار':'Location outside the selected coordinate system area')):geographic;
 return <footer className="desktop-status" data-testid="status-bar" style={{height:28,minHeight:28,maxHeight:28,flex:'0 0 28px'}}><span>z{coords.zoom}</span><span data-testid="coordinate-display" dir="ltr" title={ns?'Nord Sahara 1959 — EPSG:1253 (44 m)':'WGS84'}>{text}{projected?' · EPSG:'+projected.epsg:''}</span><span>{mpp.toFixed(2)} m/pixel</span><span>1:{Math.round(mpp*3779.5).toLocaleString()}</span><span>X:{coords.tileX} Y:{coords.tileY}</span><button onClick={onToggleOfflineMode} title={ar?'تبديل وضع عدم الاتصال':'Toggle offline mode'}>{isOfflineMode?<WifiOff size={12}/>:<Wifi size={12}/>} {isOfflineMode?(ar?'دون اتصال':'Offline'):(ar?'متصل':'Online')}</button><span><Database size={12}/>{cacheStats.total_tiles.toLocaleString()} ({cacheStats.total_size_mb} MB)</span><span className="status-source" title={ar?'إسقاط خريطة الأساس':'Base map projection'}><Globe size={12}/>{ar?'الخريطة: ':'Map: '}{projectionName}</span></footer>;
};
