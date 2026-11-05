import {BoundingBox} from '../types';
export type Bbox3D=[number,number,number,number];
export type TexturePlan={zoom:number;x0:number;x1:number;y0:number;y1:number;left:number;top:number;right:number;bottom:number;count:number;width:number;height:number};
export function worldPixel(lon:number,lat:number,z:number){const size=256*2**z;return [(lon+180)/360*size,(1-Math.asinh(Math.tan(lat*Math.PI/180))/Math.PI)/2*size];}
export function texturePlan(bbox:Bbox3D,maxZoom:number,requested?:number):TexturePlan{
 const [l,t]=worldPixel(bbox[0],bbox[3],0),[r,b]=worldPixel(bbox[2],bbox[1],0);
 let zoom=requested??Math.floor(Math.log2(4096/Math.max(r-l,b-t)));
 zoom=Math.max(0,Math.min(maxZoom,22,zoom));
 for(;;zoom--){const [left,top]=worldPixel(bbox[0],bbox[3],zoom),[right,bottom]=worldPixel(bbox[2],bbox[1],zoom);const n=2**zoom,x0=Math.max(0,Math.floor(left/256)),y0=Math.max(0,Math.floor(top/256)),x1=Math.min(n-1,Math.ceil(right/256)-1),y1=Math.min(n-1,Math.ceil(bottom/256)-1),count=(x1-x0+1)*(y1-y0+1);
  if(count<=1024||zoom===0)return {zoom,x0,x1,y0,y1,left,top,right,bottom,count,width:right-left,height:bottom-top};
 }
}
export function localSceneRegion(region:BoundingBox):{bbox:Bbox3D;cropped:boolean}{
 const lon=(region.min_lon+region.max_lon)/2,lat=(region.min_lat+region.max_lat)/2;
 const width=(region.max_lon-region.min_lon)*111320*Math.cos(lat*Math.PI/180),height=(region.max_lat-region.min_lat)*111320;
 if(width<=45000&&height<=45000)return {bbox:[region.min_lon,region.min_lat,region.max_lon,region.max_lat],cropped:false};
 const dy=.02245,dx=dy/Math.max(.09,Math.cos(lat*Math.PI/180));
 return {bbox:[Math.max(-180,lon-dx),Math.max(-85,lat-dy),Math.min(180,lon+dx),Math.min(85,lat+dy)],cropped:true};
}
