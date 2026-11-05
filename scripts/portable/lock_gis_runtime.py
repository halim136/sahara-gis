"""Verify official PyPI wheel hashes, lock GIS dependencies and extract a dev runtime."""
import hashlib,json,sys,urllib.request,zipfile,email
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
WHEELS=ROOT/'build/gis-wheels-win313'
LOCK=ROOT/'scripts/portable/gis-runtime-lock.json'

def metadata(wheel):
    with zipfile.ZipFile(wheel) as archive:
        name=next(n for n in archive.namelist() if n.endswith('.dist-info/METADATA'))
        value=email.message_from_bytes(archive.read(name))
        return value['Name'],value['Version']

def main():
    WHEELS.mkdir(parents=True,exist_ok=True)
    pillow=ROOT/'build/portable-downloads/pillow-12.3.0-cp313-cp313-win_amd64.whl'
    if pillow.exists():(WHEELS/pillow.name).write_bytes(pillow.read_bytes())
    lock=[]
    for wheel in sorted(WHEELS.glob('*.whl')):
        name,version=metadata(wheel)
        if name.lower()=='pillow' and version!='12.3.0':continue
        with urllib.request.urlopen('https://pypi.org/pypi/'+name+'/'+version+'/json',timeout=45) as response:info=json.load(response)
        item=next(x for x in info['urls'] if x['filename']==wheel.name)
        digest=hashlib.sha256(wheel.read_bytes()).hexdigest()
        if digest!=item['digests']['sha256']:raise ValueError('Hash mismatch: '+wheel.name)
        lock.append({'name':name,'version':version,'file':wheel.name,'sha256':digest,'url':item['url']})
    LOCK.write_text(json.dumps(lock,indent=2)+'\n')
    destination=ROOT/'build/gis-python'
    destination.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(ROOT/'build/portable-downloads/python-3.13.17-embed-amd64.zip') as archive:archive.extractall(destination)
    site=destination/'Lib/site-packages';site.mkdir(parents=True,exist_ok=True)
    for item in lock:
        with zipfile.ZipFile(WHEELS/item['file']) as archive:archive.extractall(site)
    (destination/'python313._pth').write_text('python313.zip\n.\nLib/site-packages\n'+str(ROOT)+'\n')
    print(json.dumps({x['name']:x['version'] for x in lock}),flush=True)

if __name__=='__main__':main()
