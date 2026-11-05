import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {build} from 'esbuild';

const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const OUT=path.join(ROOT,'releases','SASPlanet-Portable-win-x64-v1.5');
const APP=path.join(OUT,'app');
const PYTHON=process.env.BUILD_PYTHON||'python';
const command=(exe,args,env={})=>execFileSync(exe,args,{cwd:ROOT,stdio:'inherit',windowsHide:true,env:{...process.env,...env}});
const exists=async p=>!!await fs.stat(p).catch(()=>false);
if(process.platform!=='win32')throw new Error('Build this package on Windows x64.');
if(await exists(path.join(OUT,'data','settings.json')))throw new Error('This output has been used. Move it aside before rebuilding to avoid repacking personal data.');
await fs.mkdir(APP,{recursive:true});
const gisLock=JSON.parse(await fs.readFile(path.join(ROOT,'scripts/portable/gis-runtime-lock.json'),'utf8'));
const manifest=await fs.readFile(path.join(OUT,'runtime-manifest.json'),'utf8').then(JSON.parse).catch(()=>({}));
if(gisLock.some(p=>manifest.gis?.[p.name]!==p.version))command(PYTHON,['scripts/portable/download_runtimes.py',OUT]);
console.log('Building local interface...');
command(process.execPath,['node_modules/typescript/bin/tsc','--noEmit']);
command(process.execPath,['node_modules/vite/bin/vite.js','build']);
console.log('Bundling production server...');
const bundle=await build({absWorkingDir:ROOT,entryPoints:['server.ts'],outfile:path.join(APP,'server.mjs'),bundle:true,platform:'node',format:'esm',target:'node24',external:['vite'],define:{'process.env.NODE_ENV':'"production"'},banner:{js:"import { createRequire as __createRequire } from 'node:module'; const require = __createRequire(import.meta.url);"},metafile:true,legalComments:'external',logLevel:'warning'});
await fs.mkdir(path.join(APP,'dist'),{recursive:true});
await fs.copyFile(path.join(ROOT,'dist','index.html'),path.join(APP,'dist','index.html'));
await fs.cp(path.join(ROOT,'dist','assets'),path.join(APP,'dist','assets'),{recursive:true,filter:s=>!s.split(path.sep).includes('aistudio')});
await fs.cp(path.join(ROOT,'sas_planet_py'),path.join(APP,'sas_planet_py'),{recursive:true,filter:s=>!s.split(path.sep).includes('__pycache__')&&!s.endsWith('.pyc')});
const mapDefinitions=JSON.parse(await fs.readFile(path.join(ROOT,'sas_planet_py','map_sources.json'),'utf8'));
for(const source of [...Object.values(mapDefinitions.MAP_SOURCES),...Object.values(mapDefinitions.OVERLAYS)])if(source.cache_name)await fs.mkdir(path.join(OUT,'cache_gmt',source.cache_name),{recursive:true});
for(const dir of ['data','licenses','app/cache','app/public/exports','source'])await fs.mkdir(path.join(OUT,dir),{recursive:true});

// Ship corresponding application sources and licenses; never copy .env, caches or exports.
for(const name of ['src','scripts','tests','server'])await fs.cp(path.join(ROOT,name),path.join(OUT,'source',name),{recursive:true});
await fs.cp(path.join(ROOT,'sas_planet_py'),path.join(OUT,'source','sas_planet_py'),{recursive:true,filter:s=>!s.split(path.sep).includes('__pycache__')&&!s.endsWith('.pyc')});
await fs.cp(path.join(ROOT,'public','assets','sasplanet'),path.join(OUT,'source','public','assets','sasplanet'),{recursive:true});
await fs.cp(path.join(ROOT,'public','fonts'),path.join(APP,'public','fonts'),{recursive:true});
await fs.cp(path.join(ROOT,'public','fonts'),path.join(OUT,'source','public','fonts'),{recursive:true});
await fs.copyFile(path.join(ROOT,'sas.planet.src-v.260808.zip'),path.join(OUT,'source','sas.planet.src-v.260808.zip'));
for(const name of ['server.ts','package.json','package-lock.json','vite.config.ts','tsconfig.json','index.html','requirements.txt','requirements-gis.txt','README.md','IMPLEMENTATION-v1.5.md'])await fs.copyFile(path.join(ROOT,name),path.join(OUT,'source',name));
await fs.copyFile(path.join(ROOT,'public','assets','sasplanet','LICENSE.txt'),path.join(OUT,'licenses','SASPlanet-GPL-3.txt'));
await fs.copyFile(path.join(ROOT,'public','assets','sasplanet','NOTICE.md'),path.join(OUT,'licenses','SASPlanet-NOTICE.md'));
const seen=new Set(), licenses=[];
const lock=JSON.parse(await fs.readFile(path.join(ROOT,'package-lock.json'),'utf8'));
const packageDirs=new Set([
  ...Object.keys(bundle.metafile.inputs).map(input=>path.dirname(path.resolve(ROOT,input))),
  ...Object.keys(lock.packages||{}).filter(p=>p.includes('node_modules/')).map(p=>path.resolve(ROOT,p)),
]);
for(const inputDir of packageDirs){
  let dir=inputDir;
  if(!await exists(dir))continue;
  while(dir!==ROOT&&dir!==path.dirname(dir)){
    if(await exists(path.join(dir,'package.json'))){
      const pkg=JSON.parse(await fs.readFile(path.join(dir,'package.json'),'utf8'));
      if(!seen.has(dir)){seen.add(dir);const id=(pkg.name+'-'+pkg.version).replace(/[^a-zA-Z0-9._-]/g,'_');let copied=[];
        for(const entry of await fs.readdir(dir))if(/^(licen[cs]e|copying|notice)([. -]|$)/i.test(entry)&& (await fs.stat(path.join(dir,entry))).isFile()){await fs.copyFile(path.join(dir,entry),path.join(OUT,'licenses',id+'-'+entry));copied.push(entry);}
        licenses.push({name:pkg.name,version:pkg.version,license:pkg.license||'See included notices',files:copied});
      }break;
    }dir=path.dirname(dir);
  }
}
await fs.writeFile(path.join(OUT,'licenses','node-packages.json'),JSON.stringify(licenses,null,2));
await fs.writeFile(path.join(OUT,'licenses','README.txt'),'Node.js license: runtime/node/LICENSE\nCPython license: runtime/python/LICENSE.txt\nPillow and bundled library licenses: runtime/python/Lib/site-packages/pillow-*.dist-info/licenses/\nApplication icons and referenced SAS.Planet source: included GNU GPL-3 license and original archive under source/sas.planet.src-v.260808.zip.\nCorresponding application source: source/ and app/sas_planet_py/.\n');
const icon=path.join(ROOT,'build','portable-icon.ico');await fs.mkdir(path.dirname(icon),{recursive:true});
command(PYTHON,['-c',"import zipfile,sys; z=zipfile.ZipFile('sas.planet.src-v.260808.zip'); open(sys.argv[1],'wb').write(z.read('sas.planet.src-v.260808/Resources/MainIcon/icon128.ico'))",icon]);
console.log('Compiling portable launcher...');
const compiler=path.join(process.env.WINDIR||'C:/Windows','Microsoft.NET','Framework64','v4.0.30319','csc.exe');
command(compiler,['/nologo','/target:winexe','/platform:x64','/optimize+','/utf8output','/reference:System.Windows.Forms.dll','/reference:System.Drawing.dll','/reference:System.Web.Extensions.dll','/win32icon:'+icon,'/out:'+path.join(OUT,'SAS.Planet Portable.exe'),path.join(ROOT,'scripts','portable','Launcher.cs')]);
await fs.writeFile(path.join(OUT,'SAS.Planet Portable.exe.config'),'<?xml version="1.0" encoding="utf-8"?><configuration><startup><supportedRuntime version="v4.0" sku=".NETFramework,Version=v4.8" /></startup></configuration>');
await fs.writeFile(path.join(OUT,'Stop.cmd'),'@echo off\r\n"%~dp0SAS.Planet Portable.exe" --stop\r\n');
const guide=`SAS.Planet Portable — Windows 10/11 64-bit

التشغيل دون تثبيت
1. فك ضغط الحزمة بالكامل، ثم شغّل SAS.Planet Portable.exe.
2. يُفتح البرنامج في نافذة مستقلة باستخدام Edge أو Chrome الموجود في ويندوز. عند غيابهما يفتح في المتصفح الافتراضي.
3. لا تحتاج إلى تثبيت Python أو Node.js أو مكتبات التحليل؛ جميعها مضمنة.
4. لإنهاء التشغيل: انقر أيقونة البرنامج بجانب الساعة واختر «إنهاء البرنامج»، أو شغّل Stop.cmd.
5. انقل المجلد بالكامل إلى حاسوب آخر أو USB، ولا تنقل ملف EXE وحده.

البيانات المحمولة
- data/settings.json: الإعدادات والمواقع المحفوظة وآخر مشهد.
- data/browser: ملف متصفح مستقل لهذه النسخة عند استخدام Edge/Chrome؛ ملفات الخرائط تحفظ في cache_gmt.
- cache_gmt: كاش الخرائط بمجلدات مستقلة مثل sat وBoth وArcGIS.Imagery، وبنية GM1 الأصلية: المصدر/z{التكبير}/Y/X.jpg.
- app/cache/terrain: بيانات الارتفاع المخزنة وملفات SRTM المستوردة.
- app/public/exports: خرائط ArcGIS والملفات المصدرة.
- app/cache/projects: المشاريع المحلية والنسخ الاحتياطية.
- الأدوات الاحترافية: مشاريع .sasgis، تحرير والتقاط وتراجع، جودة DEM ونقاط التحقق، استيراد فهرس أوراق، أطلس A4/A3 بالمقياس.
- عرض الأرض 3D ← تصدير للطباعة: STL/3MF وتقسيم حسب الطابعة وخطة تركيب ودبابيس.
- فهرس INCT الرسمي غير مرفق؛ استورده من مصدر موثوق بصيغة GeoJSON.
- data/launcher.log: سجل التشغيل عند الحاجة.
يمكن نسخ مجلدات المصادر من cache_gmt في SAS.Planet إلى cache_gmt بجانب ملف EXE، ثم اختيار المصدر والتكبير المناسبين ووضع عدم الاتصال.
استخدم مجلداً قابلاً للكتابة مثل Documents أو USB. لا يلزم تشغيل كمسؤول. لا تُضاف خدمات أو عناصر تشغيل تلقائي أو إعدادات PATH.

دون إنترنت
الواجهة ومحرك التحليل يعملان محلياً. خرائط وصور وارتفاعات غير مخزنة تتطلب إنترنت لتنزيلها أول مرة. للتحليل دون إنترنت استورد ملفات SRTM HGT أو استخدم بيانات سبق تخزينها، ثم فعّل وضع عدم الاتصال.

هذه النسخة لويندوز 10 الحديث أو ويندوز 11 بنظام x64. تعتمد واجهة المشغّل على .NET Framework 4.8 المدمج في هذه الأنظمة، وتستخدم متصفح ويندوز الموجود؛ لا يوجد مُثبّت للبرنامج.

Start: extract ALL files and run SAS.Planet Portable.exe.
Stop: tray icon > Exit, or Stop.cmd. Copy the WHOLE folder when moving the app.
Python, Node.js and the complete GIS runtime (GDAL/rasterio, PROJ/pyproj, NumPy, OpenCV, Shapely, ReportLab, Pillow) are included. The launcher uses the Windows built-in .NET Framework 4.8 and an existing Edge/Chrome/default browser.
Maps/elevation data that has not been cached requires a connection. Local SRTM terrain analysis and stored map tiles can be used offline.
`;
await fs.writeFile(path.join(OUT,'ابدأ هنا - README.txt'),'\uFEFF'+guide,'utf8');
await fs.writeFile(path.join(OUT,'BUILD-INFO.json'),JSON.stringify({application:'SAS.Planet Portable',version:'1.5.0',arch:'x64',built:new Date().toISOString(),nodeBundle:'server.mjs',sourceIncluded:true},null,2));
// No real settings, browser profiles, cached maps or exports enter the distributable.
console.log('Portable folder ready: '+OUT);
command(PYTHON,['scripts/portable/archive_release.py',OUT]);
command(PYTHON,['scripts/portable/update_existing.py']);
