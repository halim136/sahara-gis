"""Prepare a moved Arabic-path desktop test copy; never use release user data."""
import json,os,shutil,time,math,subprocess,sys
if hasattr(sys.stdout, "reconfigure"):sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];RELEASE=ROOT/'releases/SASPlanet-Portable-win-x64-v1.5'
def linkcopy(source,target):
    try:os.link(source,target)
    except OSError:shutil.copy2(source,target)
def prepare():
    base=ROOT/'build/sahara-desktop-review';base.mkdir(parents=True,exist_ok=True);initial=base/('قبل النقل '+str(time.time_ns()));initial.mkdir()
    for folder in ('runtime','app'):
        def ignore(directory,names):
            p=Path(directory)
            return [name for name in names if name=='__pycache__' or name in ('cache','exports') or folder=='app' and p==RELEASE/'app' and name=='dist']
        shutil.copytree(RELEASE/folder,initial/folder,copy_function=linkcopy,ignore=ignore)
    shutil.copytree(ROOT/'dist',initial/'app/dist',copy_function=linkcopy)
    shutil.copy2(RELEASE/'Sahara GIS.exe',initial/'Sahara GIS.exe');shutil.copy2(RELEASE/'Sahara GIS.exe.config',initial/'Sahara GIS.exe.config')
    data=initial/'data';data.mkdir();cache=initial/'carry/cache_gmt';cache.mkdir(parents=True)
    x=int((3.05+180)/360*512);lat=math.radians(36.75);y=int((1-math.asinh(math.tan(lat))/math.pi)/2*512)
    for xx in range(x-4,x+5):
      for yy in range(y-3,y+4):
        out=cache/'sat/z9'/str(yy)/(str(xx)+'.png');out.parent.mkdir(parents=True,exist_ok=True);im=Image.new('RGB',(256,256),'#d9c395');d=ImageDraw.Draw(im)
        for offset in (30,70,110,150,190,230):d.arc((-130+offset,-30,390,310+offset),20,250,fill='#927548',width=2)
        d.rectangle((0,0,255,255),outline='#377e83',width=2);d.text((14,16),'OFFLINE CACHE TEST',fill='#163f4c');d.text((14,35),f'z9 / {xx} / {yy}',fill='#163f4c');im.save(out)
    (data/'cache-location.json').write_text(json.dumps({'path':'carry/cache_gmt'}),'utf8')
    state={'sas:settings:v1':json.dumps({'language':'ar','theme':'classic','coordinateSystem':'utm_nord_sahara','nordSaharaZone':31,'rememberView':True}),'sas:last-view:v1':json.dumps({'lat':36.75,'lon':3.05,'zoom':9}),'sas_offline_mode':'true'}
    (data/'settings.json').write_text(json.dumps(state),'utf8')
    target=base/('جهاز آخر مع مسافات '+str(time.time_ns()));initial.rename(target)
    (base/'current.json').write_text(json.dumps({'folder':str(target),'cache':str(target/'carry/cache_gmt'),'original_settings':state},ensure_ascii=False,indent=2),'utf8')
    env=dict(os.environ,PATH=str(Path(os.environ['WINDIR'])/'System32'),PYTHONHOME='Z:/not-installed',PYTHONPATH='Z:/not-installed',NODE_PATH='Z:/not-installed',NODE_OPTIONS='--invalid-host-option',ELECTRON_RUN_AS_NODE='1',BROWSER='Z:/not-installed')
    proc=subprocess.Popen([str(target/'Sahara GIS.exe')],cwd=target,env=env,creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(600):
        if (target/'data/desktop-session.json').is_file():
            desktop=json.loads((target/'data/desktop-session.json').read_text('utf8'));assert desktop['engine']=='45.2.1' and desktop['name']=='Sahara GIS';print(json.dumps({'folder':str(target),'launcher_pid':proc.pid,'desktop':desktop},ensure_ascii=False),flush=True);return
        if proc.poll() is not None:raise AssertionError('Launcher exited before native window: '+str(proc.returncode))
        time.sleep(.1)
    raise TimeoutError('Native window timeout; inspect '+str(target/'data/launcher.log'))
if __name__=='__main__':prepare()
