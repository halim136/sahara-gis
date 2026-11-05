import GeographicLib from 'geographiclib-geodesic';
const {Geodesic}=GeographicLib;
export type LatLon=[number,number];
export function pathMeasurement(points:LatLon[]){
 let distance=0;const segments:number[]=[];
 for(let i=1;i<points.length;i++){
  const result=Geodesic.WGS84.Inverse(...points[i-1],...points[i]);
  const length=result.s12??0;segments.push(length);distance+=length;
 }
 return {distance,segments};
}
export function distanceText(meters:number,ar=false){
 return meters>=1000?(meters/1000).toFixed(3)+(ar?' كم':' km'):meters.toFixed(2)+(ar?' م':' m');
}
export function appendDistinctPoint(points:LatLon[],point:LatLon):LatLon[]{
 if(points.length&&pathMeasurement([points[points.length-1],point]).distance<.02)return points;
 return [...points,point];
}
