import fs from 'node:fs';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {MapDiskCache,sources,TileSpec} from './mapCache';
type Range={z:number;x0:number;x1:number;y0:number;y1:number;count:number};
export function tileRanges(bbox:number[],zooms:number[],source:string):Range[]{
 if(!sources[source]?.url_template||!Array.isArray(bbox)||bbox.length!==4||!bbox.every(Number.isFinite)||!(bbox[0]>=-180&&bbox[0]<bbox[2]&&bbox[2]<=180&&bbox[1]>=-85&&bbox[1]<bbox[3]&&bbox[3]<=85))throw Error('Invalid source or region.');
 if(!Array.isArray(zooms)||zooms.length<1||zooms.length>24||zooms.some(z=>!Number.isInteger(z)||z<0||z>sources[source].max_zoom))throw Error('Invalid zoom levels.');
 const coord=(lon:number,lat:number,z:number)=>{const n=2**z;return [Math.max(0,Math.min(n-1,Math.floor((lon+180)/360*n))),Math.max(0,Math.min(n-1,Math.floor((1-Math.asinh(Math.tan(lat*Math.PI/180))/Math.PI)/2*n)))];};
 const ranges=[...new Set(zooms)].sort((a,b)=>a-b).map(z=>{const [x0,y1]=coord(bbox[0],bbox[1],z),[x1,y0]=coord(bbox[2],bbox[3],z);return {z,x0,x1,y0,y1,count:(x1-x0+1)*(y1-y0+1)};});
 if(ranges.reduce((n,r)=>n+r.count,0)>100000)throw Error('Select at most 100,000 tiles per job.');return ranges;
}
function specAt(job:Job,index:number):TileSpec{for(const r of job.ranges){if(index<r.count)return {source:job.source_id,z:r.z,x:r.x0+index%(r.x1-r.x0+1),y:r.y0+Math.floor(index/(r.x1-r.x0+1))};index-=r.count;}throw Error('Invalid job cursor');}
interface Job{storage_type:string;speed_kb_s:number;elapsed_s:number;bytes_downloaded:number;job_id:string;source_id:string;bbox:number[];zooms:number[];ranges:Range[];status:string;cursor:number;total_tiles:number;downloaded:number;cached:number;failed:number;progress_percent:number;error?:string;created:string;retry:number[];repair?:boolean;}
export class CacheJobs{
 private jobs=new Map<string,Job>();private running=new Set<string>();private stateFile:string;
 constructor(private cache:MapDiskCache,stateDir:string,private verify?:(bytes:Buffer)=>Promise<void>){fs.mkdirSync(stateDir,{recursive:true});this.stateFile=path.join(stateDir,'cache-jobs.json');try{const state=JSON.parse(fs.readFileSync(this.stateFile,'utf8'));for(const j of state){tileRanges(j.bbox,j.zooms,j.source_id);if(j.status==='running')j.status='paused';this.jobs.set(j.job_id,j);}}catch{} }
 private persist(){const tmp=this.stateFile+'.tmp';fs.writeFileSync(tmp,JSON.stringify([...this.jobs.values()]));fs.renameSync(tmp,this.stateFile);}
 list(){return [...this.jobs.values()].map(j=>({...j,ranges:undefined,retry:undefined}));}
 add(body:any){if(this.jobs.size>=200)throw Error('Keep at most 200 jobs; remove completed jobs first.');const ranges=tileRanges(body.bbox,body.zooms,body.source_id);const j:Job={storage_type:'gm1',speed_kb_s:0,elapsed_s:0,bytes_downloaded:0,job_id:randomUUID(),source_id:body.source_id,bbox:body.bbox,zooms:body.zooms,ranges,status:'paused',cursor:0,total_tiles:ranges.reduce((s,r)=>s+r.count,0),downloaded:0,cached:0,failed:0,progress_percent:0,created:new Date().toISOString(),retry:[],repair:body.repair===true};if(j.repair){const bad=new Set((Array.isArray(body.damaged)?body.damaged:[]).map((s:any)=>[s.z,s.x,s.y].join('/')));(j as any).damaged=[];for(let i=0;i<j.total_tiles;i++){const s=specAt(j,i);if(bad.has([s.z,s.x,s.y].join('/')))(j as any).damaged.push(i);}}this.jobs.set(j.job_id,j);this.persist();if(!body.paused)this.control(j.job_id,'resume');return j;}
 control(id:string,action:string){const j=this.jobs.get(id);if(!j)throw Error('Job not found.');if(action==='pause'){j.status='paused';}else if(action==='cancel'){j.status='cancelled';}else if(action==='remove'){if(this.running.has(id))throw Error('Pause and wait before removing.');this.jobs.delete(id);}else if(action==='resume'){if(j.status==='completed'&&!j.retry.length)return j;j.status='running';void this.run(j);}else throw Error('Unknown queue action.');this.persist();return j;}
 private async run(j:Job){if(this.running.has(j.job_id))return;this.running.add(j.job_id);
  try{while(j.status==='running'&&(j.cursor<j.total_tiles||j.retry.length)){
   const retrying=j.cursor>=j.total_tiles;const indices=retrying?j.retry.splice(0,4):Array.from({length:Math.min(4,j.total_tiles-j.cursor)},(_,i)=>j.cursor+i);
   const failed:number[]=[];let hits=0,downloads=0;
   await Promise.all(indices.map(async index=>{const spec=specAt(j,index);try{let existing=await this.cache.read(spec);if(existing&&j.repair){ // Pillow scan identifies damage; force only those tiles through a verified refresh.
      const bad=(j as any).damaged?.includes(index);if(bad)existing=null;
     }
     if(existing)hits++;else{if(j.repair&&(j as any).damaged?.includes(index))await this.cache.refresh(spec,this.verify);else await this.cache.get(spec);downloads++;}
     
    }catch(e:any){failed.push(index);j.error=e.message;}}));
   j.cached+=hits;j.downloaded+=downloads;if(retrying)j.failed=Math.max(0,j.failed-(indices.length-failed.length));else{j.failed+=failed.length;j.cursor+=indices.length;}j.retry.push(...failed);j.progress_percent=Math.round(j.cursor/j.total_tiles*10000)/100;this.persist();
   if(retrying&&failed.length){j.status='paused';j.error='Some tiles failed. Resume to retry missing tiles.';break;}
  }if(j.status==='running')j.status='completed';
  }catch(e:any){j.status='error';j.error=e.message;}finally{this.running.delete(j.job_id);this.persist();}}
 async coverage(body:any){const ranges=tileRanges(body.bbox,body.zooms,body.source_id);if(ranges.reduce((s,r)=>s+r.count,0)>10000)throw Error('Coverage inspection is limited to 10,000 tiles.');const result=[];const features:any[]=[];for(const r of ranges){let present=0;for(let i=0;i<r.count;i++){const x=r.x0+i%(r.x1-r.x0+1),y=r.y0+Math.floor(i/(r.x1-r.x0+1));const hit=await this.cache.read({source:body.source_id,z:r.z,x,y});if(hit)present++;if(features.length<2000){const lon=(x:number)=>x/2**r.z*360-180,lat=(y:number)=>Math.atan(Math.sinh(Math.PI*(1-2*y/2**r.z)))*180/Math.PI;features.push({type:'Feature',properties:{cached:!!hit,z:r.z},geometry:{type:'Polygon',coordinates:[[[lon(x),lat(y)],[lon(x+1),lat(y)],[lon(x+1),lat(y+1)],[lon(x),lat(y+1)],[lon(x),lat(y)]]]}});}}result.push({zoom:r.z,cached:present,total:r.count,percent:Math.round(present/r.count*10000)/100});}return {levels:result,geojson:{type:'FeatureCollection',features},drawn_tile_limit:2000};}
}
