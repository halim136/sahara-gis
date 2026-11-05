const {app,BrowserWindow,ipcMain,dialog,shell,Menu}=require('electron');
const fs=require('node:fs/promises'),path=require('node:path');
const option=name=>process.argv.find(v=>v.startsWith('--'+name+'='))?.slice(name.length+3);
const root=path.resolve(option('root')||path.join(__dirname,'../../../..'));
const url=new URL(option('url')||'http://127.0.0.1:1/');
if(url.protocol!=='http:'||url.hostname!=='127.0.0.1'||url.pathname!=='/'||url.search||url.hash)throw Error('Invalid local application URL');
app.setName('Sahara GIS');app.setAppUserModelId('SaharaGIS.Portable');
app.setPath('userData',path.join(root,'data/desktop-browser'));
app.commandLine.appendSwitch('force-renderer-accessibility');
let win;
const own=event=>event.sender===win?.webContents&&event.senderFrame?.url.startsWith(url.origin+'/');
async function location(){const res=await fetch(url.origin+'/api/cache/location');if(!res.ok)throw Error('Cannot read cache location');return res.json();}
if(!app.requestSingleInstanceLock()){app.quit();}else{
 app.on('second-instance',()=>{if(win){if(win.isMinimized())win.restore();win.show();win.focus();}});
 app.whenReady().then(async()=>{
  const state=JSON.parse(await fs.readFile(path.join(root,'data/session.json'),'utf8'));
  const health=await (await fetch(url.origin+'/api/health')).json();
  if(state.instance!==health.instance||!health.portable)throw Error('Local application session does not match this folder');
  Menu.setApplicationMenu(null);
  win=new BrowserWindow({title:'Sahara GIS — صحارى GIS',width:1280,height:820,minWidth:850,minHeight:560,show:false,backgroundColor:'#f3f5f7',autoHideMenuBar:true,icon:path.join(__dirname,'sahara-gis.ico'),webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true,zoomFactor:1,spellcheck:false}});
  win.webContents.setZoomFactor(1);win.webContents.setVisualZoomLevelLimits(1,1);
  win.webContents.on('page-title-updated',event=>{event.preventDefault();win.setTitle('Sahara GIS — صحارى GIS');});
  win.webContents.on('will-navigate',(event,target)=>{if(new URL(target).origin!==url.origin)event.preventDefault();});
  win.webContents.setWindowOpenHandler(({url:target})=>{if(/^https?:/.test(target))void shell.openExternal(target);return {action:'deny'};});
  const session=win.webContents.session;
  session.setPermissionCheckHandler((contents,permission,origin)=>contents===win.webContents&&origin===url.origin&&['serial','clipboard-sanitized-write'].includes(permission));
  session.setPermissionRequestHandler((contents,permission,callback,details)=>callback(contents===win.webContents&&details.requestingUrl?.startsWith(url.origin+'/')&&['serial','clipboard-sanitized-write'].includes(permission)));
  session.on('select-serial-port',async(event,ports,contents,callback)=>{
   event.preventDefault();if(contents!==win.webContents||!contents.getURL().startsWith(url.origin+'/'))return callback('');
   if(!ports.length){await dialog.showMessageBox(win,{type:'info',message:'لم يتم العثور على منفذ GPS. وصّل الجهاز ثم أعد المحاولة.',buttons:['حسناً']});return callback('');}
   const result=await dialog.showMessageBox(win,{type:'question',title:'GPS — Sahara GIS',message:'اختر منفذ جهاز GPS',buttons:[...ports.map(p=>p.displayName||p.portName),'إلغاء'],cancelId:ports.length});
   callback(ports[result.response]?.portId||'');
  });
  ipcMain.handle('sahara:open-cache',async event=>{if(!own(event))throw Error('Invalid window');const info=await location();const folder=path.resolve(info.path);const error=await shell.openPath(folder);return {success:!error,path:folder,error};});
  ipcMain.handle('sahara:choose-cache',async event=>{if(!own(event))throw Error('Invalid window');const result=await dialog.showOpenDialog(win,{title:'اختر مجلد cache_gmt الذي يحتوي الخرائط',properties:['openDirectory','createDirectory']});return result.canceled?null:result.filePaths[0];});
  ipcMain.handle('sahara:copy-cache',async event=>{
   if(!own(event))throw Error('Invalid window');const info=await location();const source=path.resolve(info.path);
   const result=await dialog.showOpenDialog(win,{title:'اختر مكان نسخ الكاش للنقل إلى جهاز آخر',properties:['openDirectory','createDirectory']});if(result.canceled)return {cancelled:true};
   const selected=result.filePaths[0],target=path.resolve(path.basename(selected).toLowerCase()==='cache_gmt'?selected:path.join(selected,'cache_gmt'));
   const within=(base,file)=>{const rel=path.relative(base,file);return rel===''||(!rel.startsWith('..'+path.sep)&&rel!=='..'&&!path.isAbsolute(rel));};
   if(within(source,target)||within(target,source))throw Error('اختر مجلداً منفصلاً عن مجلد الكاش الحالي.');
   await fs.cp(source,target,{recursive:true,force:false,errorOnExist:false,filter:async file=>{const st=await fs.lstat(file);return !st.isSymbolicLink()&&(st.isDirectory()||/\.(?:png|jpe?g|webp|gif|bmp)$/i.test(file));}});
   return {success:true,path:target};
  });
  win.once('ready-to-show',()=>{win.show();win.focus();});
  win.on('closed',()=>{win=null;app.quit();});
  await win.loadURL(url.href);
  await fs.writeFile(path.join(root,'data/desktop-session.json'),JSON.stringify({pid:process.pid,window:true,name:'Sahara GIS',engine:process.versions.electron,chromium:process.versions.chrome,root,url:url.href}));
 }).catch(async error=>{await dialog.showMessageBox({type:'error',title:'Sahara GIS',message:error.message});app.quit();});
 app.on('window-all-closed',()=>app.quit());
 app.on('before-quit',()=>{void fs.unlink(path.join(root,'data/desktop-session.json')).catch(()=>{});});
}
