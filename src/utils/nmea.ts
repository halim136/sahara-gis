export type NmeaFix={kind:'GGA'|'RMC';valid:boolean;lat?:number;lon?:number;quality?:number;satellites?:number;hdop?:number;altitudeM?:number;geoidM?:number;speedKmh?:number;bearing?:number;time?:string;utcTime?:string};
const finite=(s:string|undefined)=>typeof s==='string'&&s.trim()!==''&&Number.isFinite(Number(s))?Number(s):undefined;
function degrees(raw:string,hemisphere:string,lat:boolean){const n=Number(raw),d=Math.floor(n/100),m=n-d*100;if(!raw||!Number.isFinite(n)||m>=60||m<0||d>(lat?90:180)||!new RegExp(lat?'^[NS]$':'^[EW]$').test(hemisphere))return undefined;const v=(d+m/60)*(/[SW]/.test(hemisphere)?-1:1);return Math.abs(v)<=(lat?85:180)?v:undefined;}
export function nmeaChecksum(body:string){let n=0;for(const c of body)n^=c.charCodeAt(0);return n.toString(16).toUpperCase().padStart(2,'0');}
export function parseNmea(line:string):NmeaFix|null{
 const match=line.trim().match(/^\$([^*]+)\*([0-9A-Fa-f]{2})$/);if(!match||nmeaChecksum(match[1])!==match[2].toUpperCase())return null;
 const f=match[1].split(','),kind=f[0].slice(-3);if(!['GGA','RMC'].includes(kind))return null;
 const okTime=/^\d{6}(?:\.\d+)?$/.test(f[1])&&Number(f[1].slice(0,2))<24&&Number(f[1].slice(2,4))<60&&Number(f[1].slice(4))<60;
 if(!okTime)return null;
 if(kind==='GGA'){
  const quality=finite(f[6]);if(quality===undefined||!Number.isInteger(quality)||quality<0||quality>8)return null;
  if(quality===0)return {kind,valid:false,quality,utcTime:f[1]};
  const lat=degrees(f[2],f[3],true),lon=degrees(f[4],f[5],false);if(lat===undefined||lon===undefined)return null;
  return {kind,valid:true,lat,lon,quality,satellites:finite(f[7]),hdop:finite(f[8]),altitudeM:f[10]==='M'?finite(f[9]):undefined,geoidM:f[12]==='M'?finite(f[11]):undefined,utcTime:f[1]};
 }
 if(f[2]!=='A')return {kind:'RMC',valid:false,utcTime:f[1]};
 const lat=degrees(f[3],f[4],true),lon=degrees(f[5],f[6],false);if(lat===undefined||lon===undefined)return null;
 let time:string|undefined;
 if(/^\d{6}$/.test(f[9])){const yy=Number(f[9].slice(4)),year=yy>=80?1900+yy:2000+yy,month=Number(f[9].slice(2,4)),day=Number(f[9].slice(0,2)),date=new Date(Date.UTC(year,month-1,day,Number(f[1].slice(0,2)),Number(f[1].slice(2,4)),Number(f[1].slice(4,6)),Math.round((Number('0.'+(f[1].split('.')[1]||'0')))*1000)));if(date.getUTCFullYear()===year&&date.getUTCMonth()===month-1&&date.getUTCDate()===day)time=date.toISOString();}
 return {kind:'RMC',valid:true,lat,lon,time,utcTime:f[1],speedKmh:finite(f[7])===undefined?undefined:Number(f[7])*1.852,bearing:finite(f[8])};
}
