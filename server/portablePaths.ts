import fs from 'node:fs';import path from 'node:path';
export function portableLayout(appDir:string,flag?:string){const parent=path.resolve(appDir,'..');const detected=path.basename(appDir).toLowerCase()==='app'&&fs.existsSync(path.join(parent,'runtime/node/node.exe'))&&fs.existsSync(path.join(parent,'runtime/python/python.exe'));return {portable:flag==='1'||detected,root:flag==='1'||detected?parent:path.resolve(appDir)};}
export function hasCacheData(folder:string){try{return fs.readdirSync(folder,{withFileTypes:true}).some(source=>source.isDirectory()&&fs.readdirSync(path.join(folder,source.name),{withFileTypes:true}).some(level=>level.isDirectory()&&/^z\d+$/.test(level.name)&&fs.readdirSync(path.join(folder,source.name,level.name)).length>0));}catch{return false;}}
export function resolveCacheLocation(root:string,appDir:string,configFile:string){
 const fallback=path.resolve(root,'cache_gmt');let warning='';
 try{const config=JSON.parse(fs.readFileSync(configFile,'utf8'));if(typeof config.path==='string'&&config.path.trim()){const candidate=path.resolve(root,config.path);if(fs.existsSync(candidate)&&fs.statSync(candidate).isDirectory())return {path:candidate,default_path:fallback,source:'configured',warning:''};warning='Previously selected cache folder unavailable; using cache_gmt beside the application.';}}catch{}
 const candidates=[fallback,path.resolve(appDir,'cache_gmt')];const populated=candidates.find(hasCacheData);
 return {path:populated||fallback,default_path:fallback,source:populated&&populated!==fallback?'discovered':'default',warning};
}
export function cacheConfigPath(root:string,folder:string){const relative=path.relative(root,folder);return relative&&!relative.startsWith('..'+path.sep)&&relative!=='..'&&!path.isAbsolute(relative)?relative:folder;}
