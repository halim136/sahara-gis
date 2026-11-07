// Portable preferences live alongside the executable, independent of localhost port.
const KEYS=['sas:settings:v1','sas:saved-views:v1','sas:last-view:v1','sas_offline_mode','sas:marks:v1','sas:analyses:v1','sas:camera3d:v1','sas:field:v1','sas:windows:v1','sas:last-source:v1'];
let portable=false;let timer:ReturnType<typeof setTimeout>|undefined;
const snapshot=()=>Object.fromEntries(KEYS.flatMap(key=>{const value=localStorage.getItem(key);return value===null?[]:[[key,value]];}));
function flush(){if(!portable)return;try{void fetch('/api/portable/state',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(snapshot()),keepalive:true}).catch(()=>{});}catch{}}
export async function hydratePortableState(){
  try{const response=await fetch('/api/portable/state',{signal:AbortSignal.timeout(3000)});if(!response.ok)return;const data=await response.json();portable=data.portable===true;
    if(portable&&data.state&&typeof data.state==='object')for(const key of KEYS)if(typeof data.state[key]==='string')localStorage.setItem(key,data.state[key]);
  }catch{}
  window.addEventListener('pagehide',()=>{if(portable)try{navigator.sendBeacon('/api/portable/state',new Blob([JSON.stringify(snapshot())],{type:'application/json'}));}catch{}});
}
export function storeAppValue(key:string,value:string){localStorage.setItem(key,value);if(portable&&KEYS.includes(key)){clearTimeout(timer);timer=setTimeout(flush,250);}}
