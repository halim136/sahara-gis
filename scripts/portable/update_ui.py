"""Patch the existing v1.5 interface and ZIP without collecting live user data."""
import hashlib,json,shutil,subprocess,zipfile
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
FOLDER=ROOT/'releases/SASPlanet-Portable-win-x64-v1.5'
ARCHIVE=ROOT/'releases/SAS.Planet-Portable-Windows-x64-v1.5.zip'
PREFIX='SASPlanet-Portable-v1.5/'
SOURCES=['src/App.tsx','src/components/HeaderNavbar.tsx','src/index.css','scripts/portable/update_ui.py']
def main():
    if not ARCHIVE.is_file() or not (FOLDER/'app/server.mjs').is_file():raise ValueError('Existing v1.5 release required.')
    for args in (['node','node_modules/typescript/bin/tsc','--noEmit'],['node','node_modules/vite/bin/vite.js','build']):
        subprocess.run(args,cwd=ROOT,check=True)
    dist=ROOT/'dist';target=FOLDER/'app/dist'
    # Keep old assets for already-open windows; switch the entry point last.
    for file in dist.rglob('*'):
        if file.is_file() and file.relative_to(dist).parts[0] in ('assets','fonts'):
            dest=target/file.relative_to(dist);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,dest)
    shutil.copy2(dist/'index.html',target/'index.html')
    updates={}
    for source in SOURCES:
        file=ROOT/source;dest=FOLDER/'source'/source;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,dest);updates[PREFIX+'source/'+source]=file
    info=FOLDER/'BUILD-INFO.json';metadata=json.loads(info.read_text('utf8'));metadata['ui_updated_utc']=datetime.now(timezone.utc).isoformat();info.write_text(json.dumps(metadata,indent=2),'utf8');updates[PREFIX+'BUILD-INFO.json']=info
    for file in dist.rglob('*'):
        if file.is_file() and (file.relative_to(dist).parts[0] in ('assets','fonts') or file.relative_to(dist).as_posix()=='index.html'):updates[PREFIX+'app/dist/'+file.relative_to(dist).as_posix()]=file
    temporary=ARCHIVE.with_suffix('.updating.zip')
    # Reuse the original clean ZIP as the manifest. Never enumerate personal
    # data, caches or project folders from the running portable application.
    with zipfile.ZipFile(ARCHIVE) as previous,zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as output:
        for entry in previous.infolist():
            if not entry.filename.startswith(PREFIX):raise ValueError('Unexpected archive root.')
            relative=entry.filename[len(PREFIX):]
            if relative.startswith(('data/','app/cache/','app/public/exports/')) or relative.startswith('cache_gmt/') and not entry.is_dir():raise ValueError('Original archive contains user data.')
            if entry.filename in updates or relative.startswith('app/dist/'):continue
            output.writestr(entry,previous.read(entry.filename))
        for name,file in updates.items():output.write(file,name)
    temporary.replace(ARCHIVE)
    digest=hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    ARCHIVE.with_suffix('.zip.sha256').write_text(digest+'  '+ARCHIVE.name+'\n')
    print('Updated existing v1.5 interface and ZIP. Settings, map cache and projects preserved.',flush=True)
    print(str(ARCHIVE),flush=True)
if __name__=='__main__':main()
