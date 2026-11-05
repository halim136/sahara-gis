"""Update app/code in the existing v1.5; archive only known clean members."""
import hashlib,json,shutil,subprocess,zipfile,os
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
FOLDER=ROOT/'releases/SASPlanet-Portable-win-x64-v1.5'
ARCHIVE=ROOT/'releases/SAS.Planet-Portable-Windows-x64-v1.5.zip'
PREFIX='SASPlanet-Portable-v1.5/'
SOURCES=['tests/check_terrain_offline.py','src/components/Terrain3DViewer.tsx','tests/test_topography.py','tests/test_scene3d.py','tests/test_vector_import.py','src/App.tsx','src/components/HeaderNavbar.tsx','src/components/ProfessionalWorkbench.tsx','src/components/FieldLayers.tsx','src/components/FieldWorkbench.tsx','src/components/SelectionOpsModal.tsx','src/components/AlgeriaSheetGrid.tsx','src/components/MapCanvas.tsx','src/utils/nmea.ts','src/utils/portableState.ts','src/types/index.ts','src/index.css','server.ts','scripts/build-portable.mjs','server/mapCache.ts','server/portablePaths.ts','src/components/CacheManagerModal.tsx','src/components/StatusBar.tsx','index.html','tests/portable-paths.test.ts','scripts/portable/Launcher.cs','scripts/portable/Launcher.manifest','scripts/portable/download_desktop.py','scripts/portable/compile_desktop.py','scripts/portable/create_brand.py','scripts/desktop/main.cjs','scripts/desktop/preload.cjs','scripts/desktop/package.json','IMPLEMENTATION-sahara-v1.5.md','vite.config.ts','scripts/portable/update_ui.py','tests/test_field.py','tests/nmea.test.ts','tests/field_portable_checks.py','tests/smoke_portable.py','scripts/portable/update_existing.py','scripts/portable/bundle-update.mjs','README.md','IMPLEMENTATION-field-v1.5.md']
PYTHON=['terrain.py','scene3d.py','tile_stitcher.py','field_tracks.py','field_raster.py','field_planning.py','studio.py','vector_formats.py','projects.py']
def main():
    if not ARCHIVE.is_file() or not (FOLDER/'app/server.mjs').is_file():raise ValueError('Existing v1.5 release required.')
    sensitive=[FOLDER/'data/settings.json',FOLDER/'app/cache/projects']
    # Record settings bytes; the updater never writes anything below data/cache.
    settings=sensitive[0].read_bytes() if sensitive[0].is_file() else None
    for args in (['node','node_modules/typescript/bin/tsc','--noEmit'],['node','node_modules/vite/bin/vite.js','build'],['node','scripts/portable/bundle-update.mjs']):
        subprocess.run(args,cwd=ROOT,check=True)
    subprocess.run(['python','scripts/portable/compile_desktop.py'],cwd=ROOT,check=True)
    if not (ROOT/'build/desktop-runtime/electron.exe').is_file():subprocess.run(['python','scripts/portable/download_desktop.py'],cwd=ROOT,check=True)
    updates={}
    def copy(source,relative):
        dest=FOLDER/relative;dest.parent.mkdir(parents=True,exist_ok=True);tmp=dest.with_suffix(dest.suffix+'.updating');shutil.copy2(source,tmp)
        try:os.replace(tmp,dest)
        except PermissionError:
            # A running portable app locks its launcher and Electron resources.
            # They are safe to leave in place only when byte-identical; the ZIP
            # still receives the current build source.
            if dest.is_file() and hashlib.sha256(source.read_bytes()).digest()==hashlib.sha256(dest.read_bytes()).digest():
                tmp.unlink(missing_ok=True);updates[PREFIX+relative]=source;return
            if relative in ('Sahara GIS.exe','SAS.Planet Portable.exe'):
                # The launcher only starts the bundled desktop/server files,
                # which were updated above.  Keep an in-use launcher until the
                # next closed-app update, while the portable ZIP gets the new one.
                tmp.unlink(missing_ok=True);updates[PREFIX+relative]=source;print('Launcher is running; its update is pending until it is closed.',flush=True);return
            tmp.unlink(missing_ok=True);raise
        updates[PREFIX+relative]=dest
    # Keep old assets available to already-open windows; index switches last.
    dist=ROOT/'dist'
    for f in dist.rglob('*'):
        if f.is_file() and f.relative_to(dist).parts[0] in ('assets','fonts'):copy(f,'app/dist/'+f.relative_to(dist).as_posix())
    copy(ROOT/'build/server-update.mjs','app/server.mjs')
    legal=ROOT/'build/server-update.mjs.LEGAL.txt'
    if legal.exists():copy(legal,'app/server.mjs.LEGAL.txt')
    for name in PYTHON:
        copy(ROOT/'sas_planet_py'/name,'app/sas_planet_py/'+name);copy(ROOT/'sas_planet_py'/name,'source/sas_planet_py/'+name)
    for source in SOURCES:copy(ROOT/source,'source/'+source)
    desktop=ROOT/'build/desktop-runtime'
    for file in desktop.rglob('*'):
        if file.is_file():
            relative=file.relative_to(desktop).as_posix()
            if relative=='electron.exe':relative='Sahara GIS.exe'
            elif relative=='electron_wer.dll':relative='Sahara GIS_wer.dll'
            copy(file,'runtime/desktop/'+relative)
    for name in ('main.cjs','preload.cjs','package.json'):copy(ROOT/'scripts/desktop'/name,'runtime/desktop/resources/app/'+name)
    copy(ROOT/'public/assets/branding/sahara-gis.ico','runtime/desktop/resources/app/sahara-gis.ico')
    copy(ROOT/'build/desktop-download/runtime-lock.json','source/scripts/portable/desktop-runtime-lock.json')
    copy(ROOT/'build/Sahara GIS.exe','Sahara GIS.exe')
    legacy=FOLDER/'SAS.Planet Portable.exe'
    try:shutil.copy2(ROOT/'build/Sahara GIS.exe',legacy)
    except PermissionError:print('Old launcher is running; use Sahara GIS.exe after closing it.',flush=True)
    updates[PREFIX+'SAS.Planet Portable.exe']=ROOT/'build/Sahara GIS.exe'
    config=FOLDER/'Sahara GIS.exe.config';config.write_text('<?xml version="1.0" encoding="utf-8"?><configuration><startup><supportedRuntime version="v4.0" sku=".NETFramework,Version=v4.8" /></startup></configuration>','utf8');updates[PREFIX+'Sahara GIS.exe.config']=config
    stop=FOLDER/'Stop.cmd';stop.write_text('@echo off\n"%~dp0Sahara GIS.exe" --stop\n');updates[PREFIX+'Stop.cmd']=stop
    guide=FOLDER/'ابدأ هنا - README.txt';guide.write_text('Sahara GIS — صحارى GIS 1.5\n\nفك الضغط بالكامل وشغّل Sahara GIS.exe. نافذة مستقلة بمحرك مضمن؛ لا تحتاج Edge أو Chrome.\nعند النقل انسخ المجلد كاملاً بما فيه cache_gmt وdata وapp/cache. حزمة التوزيع النظيفة لا تحتوي خرائطك الشخصية.\nمن إدارة الكاش: فتح المجلد، اختيار كاش موجود، أو نسخ الكاش للنقل.\nأغلق النافذة لإغلاق البرنامج وخادمه. تبقى المشاريع والإعدادات محفوظة.\n','utf-8-sig');updates[PREFIX+guide.name]=guide
    copy(dist/'index.html','app/dist/index.html')

    info=FOLDER/'BUILD-INFO.json';metadata=json.loads(info.read_text('utf8'));metadata['application_updated_utc']=datetime.now(timezone.utc).isoformat();metadata['field_tools']=True;metadata['application']='Sahara GIS';metadata['desktop_engine']='Electron 45.2.1';metadata['independent_desktop_window']=True;info.write_text(json.dumps(metadata,indent=2),'utf8');updates[PREFIX+'BUILD-INFO.json']=info
    temporary=ARCHIVE.with_suffix('.updating.zip')
    with zipfile.ZipFile(ARCHIVE) as previous,zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as output:
        for entry in previous.infolist():
            if not entry.filename.startswith(PREFIX):raise ValueError('Unexpected archive root.')
            rel=entry.filename[len(PREFIX):]
            if rel.startswith(('data/','app/cache/','app/public/exports/')) or rel.startswith('cache_gmt/') and not entry.is_dir():raise ValueError('Original archive contains user data.')
            if entry.filename in updates or rel.startswith('app/dist/'):continue
            output.writestr(entry,previous.read(entry.filename))
        for name,file in updates.items():output.write(file,name)
    temporary.replace(ARCHIVE);digest=hashlib.sha256(ARCHIVE.read_bytes()).hexdigest();ARCHIVE.with_suffix('.zip.sha256').write_text(digest+'  '+ARCHIVE.name+'\n')
    report={'same_version':'1.5.0','archive_sha256':digest,'updated_files':len(updates),'updater_did_not_write_settings':True,'settings_unchanged_during_update':settings is None or sensitive[0].read_bytes()==settings,'personal_folders_enumerated':False,'restart_required_for_server':True}
    out=ROOT/'build/field-review';out.mkdir(parents=True,exist_ok=True);(out/'update-report.json').write_text(json.dumps(report,indent=2),'utf8')
    print('Updated v1.5 in place. Settings/cache/projects preserved; restart application for new APIs.',flush=True)
if __name__=='__main__':main()
