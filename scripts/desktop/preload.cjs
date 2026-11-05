const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('saharaDesktop',Object.freeze({name:'Sahara GIS',openCache:()=>ipcRenderer.invoke('sahara:open-cache'),chooseCache:()=>ipcRenderer.invoke('sahara:choose-cache'),copyCache:()=>ipcRenderer.invoke('sahara:copy-cache')}));
