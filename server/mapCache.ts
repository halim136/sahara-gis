import fs from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import definitions from '../sas_planet_py/map_sources.json';

type Source = {id:string;cache_name?:string;url_template?:string;subdomains?:string[];max_zoom:number;format?:string;name:string;is_grid?:boolean};
export const sources: Record<string,Source> = {...definitions.MAP_SOURCES,...definitions.OVERLAYS};
const extensions=['jpg','png','jpeg','webp','gif'];
export class TileError extends Error {constructor(public status:number,message:string){super(message);}}
export function tileSpec(query:Record<string,unknown>){
  const source=typeof query.source==='string'?query.source:'';
  const known=Object.hasOwn(sources,source)?sources[source]:null;
  if(!known?.url_template||!known.cache_name)throw new TileError(400,'Unknown map source');
  const coords=['z','x','y'].map(key=>{
    const value=query[key];
    if(typeof value!=='string'||!/^(0|[1-9]\d*)$/.test(value))throw new TileError(400,'Use integer XYZ coordinates');
    return Number(value);
  });
  const [z,x,y]=coords;
  if(z>known.max_zoom||!Number.isSafeInteger(x)||!Number.isSafeInteger(y)||x>=2**z||y>=2**z)throw new TileError(400,'Tile outside source bounds');
  return {source,z,x,y};
}
export type TileSpec=ReturnType<typeof tileSpec>;
export function imageType(bytes:Buffer){
  if(bytes.length>=8&&bytes.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10])))return {ext:'png',mime:'image/png'};
  if(bytes.length>=3&&bytes[0]===255&&bytes[1]===216&&bytes[2]===255)return {ext:'jpg',mime:'image/jpeg'};
  if(bytes.length>=12&&bytes.toString('ascii',0,4)==='RIFF'&&bytes.toString('ascii',8,12)==='WEBP')return {ext:'webp',mime:'image/webp'};
  if(bytes.length>=6&&/^GIF8[79]a$/.test(bytes.toString('ascii',0,6)))return {ext:'gif',mime:'image/gif'};
  throw new TileError(502,'The source did not return a supported tile image');
}
export class MapDiskCache {
  private pending=new Map<string,Promise<{bytes:Buffer;mime:string;hit:boolean}>>();
  constructor(public root:string,readonly legacyRoot:string,private fetcher:typeof fetch=fetch){}
  async switchRoot(next:string){if(this.pending.size)throw Error('Wait for current map requests before changing cache folders.');const previous=this.root;this.root=path.resolve(next);try{await this.initialize();}catch(error){this.root=previous;throw error;}}
  async initialize(){
    await fs.mkdir(this.root,{recursive:true});
    await Promise.all(Object.values(sources).filter(s=>s.cache_name).map(s=>fs.mkdir(path.join(this.root,s.cache_name!),{recursive:true})));
  }
  tilePath(spec:TileSpec,ext:string){
    return path.join(this.root,sources[spec.source].cache_name!, 'z'+spec.z,String(spec.y),spec.x+'.'+ext);
  }
  async save(spec:TileSpec,bytes:Buffer){
    if(bytes.length>8*1024*1024)throw new TileError(413,'Tile image too large');
    const type=imageType(bytes),file=this.tilePath(spec,type.ext);
    await fs.mkdir(path.dirname(file),{recursive:true});
    const temporary=file+'.'+randomUUID()+'.tmp';
    try{
      await fs.writeFile(temporary,bytes);
      for(let attempt=0;attempt<6;attempt++){
        try{await fs.rename(temporary,file);break;}catch(error:any){
          if(!['EPERM','EACCES','EBUSY'].includes(error.code)||attempt===5)throw error;
          await new Promise(resolve=>setTimeout(resolve,10*(attempt+1)));
        }
      }
    }
    finally{await fs.unlink(temporary).catch(()=>{});}
    return {bytes,mime:type.mime,hit:false};
  }
  async read(spec:TileSpec){
    const known=sources[spec.source], exts=[...new Set([known.format||'jpg',...extensions])];
    for(const ext of exts){
      const paths=[this.tilePath(spec,ext),
        path.join(this.root,known.cache_name!,'z'+(spec.z+1),String(Math.floor(spec.x/1024)),'x'+spec.x,String(Math.floor(spec.y/1024)),'y'+spec.y+'.'+ext),
        path.join(this.legacyRoot,spec.source,'z'+spec.z,String(Math.floor(spec.x/1024)),'x'+spec.x,String(Math.floor(spec.y/1024)),'y'+spec.y+'.'+ext)];
      for(let index=0;index<paths.length;index++){
        let bytes:Buffer;
        try{bytes=await fs.readFile(paths[index]);}catch(error:any){if(error.code==='ENOENT'||error.code==='ENOTDIR')continue;throw error;}
        let mime:string;
        try{mime=imageType(bytes).mime;}catch{continue;}
        if(index>0)await this.save(spec,bytes);
        return {bytes,mime,hit:true};
      }
    }
    return null;
  }
  async refresh(spec:TileSpec,verify?:(bytes:Buffer)=>Promise<void>){
    const source=sources[spec.source],sub=source.subdomains?.[Math.abs(spec.x+spec.y)%source.subdomains.length]||'';
    const url=source.url_template!.replaceAll('{s}',sub).replaceAll('{z}',String(spec.z)).replaceAll('{x}',String(spec.x)).replaceAll('{y}',String(spec.y));
    const response=await this.fetcher(url,{signal:AbortSignal.timeout(15000)});if(!response.ok)throw new TileError(502,'Repair download failed');
    const chunks:Uint8Array[]=[];let size=0;for await(const chunk of response.body!){size+=chunk.length;if(size>8*1024*1024)throw new TileError(413,'Tile too large');chunks.push(chunk);}
    const bytes=Buffer.concat(chunks);if(verify)await verify(bytes);const result=await this.save(spec,bytes);
    // Preserve older encodings as backups, so a damaged JPG cannot mask a repaired PNG.
    const current=imageType(bytes).ext;for(const ext of extensions)if(ext!==current){const old=this.tilePath(spec,ext);try{await fs.rename(old,old+'.previous-'+randomUUID());}catch(e:any){if(e.code!=='ENOENT')throw e;}}
    return result;
  }
  async get(spec:TileSpec,offline=false){
    const cached=await this.read(spec);if(cached)return cached;
    // Offline misses never enter the network queue or wait for online requests.
    if(offline)throw new TileError(404,'Tile is not available in cache_gmt');
    const key=[spec.source,spec.z,spec.x,spec.y].join('/');
    const pending=this.pending.get(key);if(pending)return pending;
    const task=(async()=>{
      const source=sources[spec.source],sub=source.subdomains?.[Math.abs(spec.x+spec.y)%source.subdomains.length]||'';
      const url=source.url_template!.replaceAll('{s}',sub).replaceAll('{z}',String(spec.z)).replaceAll('{x}',String(spec.x)).replaceAll('{y}',String(spec.y));
      const response=await this.fetcher(url,{headers:{'User-Agent':'SAS.Planet Portable/1.1 (Local Map Cache)','Referer':'https://www.google.com/'},signal:AbortSignal.timeout(15000)});
      if(!response.ok)throw new TileError(502,'Map source returned HTTP '+response.status);
      if(Number(response.headers.get('content-length'))>8*1024*1024)throw new TileError(413,'Tile image too large');
      const chunks:Uint8Array[]=[];let size=0;
      for await(const chunk of response.body!){size+=chunk.length;if(size>8*1024*1024)throw new TileError(413,'Tile image too large');chunks.push(chunk);}
      return this.save(spec,Buffer.concat(chunks));
    })();
    this.pending.set(key,task);
    try{return await task;}finally{this.pending.delete(key);}
  }
  async stats(){
    let total=0,count=0;const layers:{folder:string;tiles:number;size_mb:number}[]=[];
    const walk=async(dir:string):Promise<{bytes:number;tiles:number}>=>{
      let bytes=0,tiles=0;
      for(const entry of await fs.readdir(dir,{withFileTypes:true})){
        const file=path.join(dir,entry.name);
        if(entry.isDirectory()){const nested=await walk(file);bytes+=nested.bytes;tiles+=nested.tiles;}
        else if(entry.isFile()&&extensions.includes(path.extname(entry.name).slice(1).toLowerCase())){
          try{bytes+=(await fs.stat(file)).size;tiles++;}catch(error:any){if(error.code!=='ENOENT')throw error;}
        }
      }
      return {bytes,tiles};
    };
    for(const entry of await fs.readdir(this.root,{withFileTypes:true}))if(entry.isDirectory()){
      const {bytes,tiles}=await walk(path.join(this.root,entry.name));total+=bytes;count+=tiles;
      layers.push({folder:entry.name,tiles,size_mb:Number((bytes/1024**2).toFixed(2))});
    }
    return {total_tiles:count,total_size_bytes:total,total_size_mb:Number((total/1024**2).toFixed(2)),base_dir:this.root,format:'gm1',layers};
  }
}
