"""Download redistribution archives from official sources, with SHA-256 checks."""
import hashlib
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

NODE='24.22.2'
PYTHON='3.13.17'
PYTHON_SHA='9e35319bffedab8b36ad44d8f377cb4f1733bcec257a0b6d04d94f01486ddb38'
ROOT=Path(__file__).resolve().parents[2]
CACHE=ROOT/'build'/'portable-downloads'
CACHE.mkdir(parents=True,exist_ok=True)


def read(url):
    with urllib.request.urlopen(url,timeout=90) as response:return response.read()


def download(url,name,expected):
    path=CACHE/name
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==expected:return path
    print('Downloading '+name,flush=True)
    payload=read(url)
    actual=hashlib.sha256(payload).hexdigest()
    if actual!=expected:raise ValueError('SHA-256 mismatch: '+name)
    path.write_bytes(payload)
    return path


def extract(zip_path,destination):
    with zipfile.ZipFile(zip_path) as archive:
        base=destination.resolve()
        for name in archive.namelist():
            if not (base/name).resolve().is_relative_to(base):raise ValueError('Unsafe archive member')
        archive.extractall(destination)
        if str(zip_path).endswith('.whl'):
            for name in archive.namelist():
                for part in ('.data/platlib/','.data/purelib/'):
                    if part in name and not name.endswith('/'):
                        relative=name.split(part,1)[1];target=(base/relative).resolve()
                        if not target.is_relative_to(base):raise ValueError('Unsafe wheel data path')
                        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.read(name))


def main():
    out=Path(sys.argv[1]).resolve()
    if not out.is_relative_to(ROOT/'releases'):raise ValueError('Output must be inside releases/')
    node_name='node-v'+NODE+'-win-x64.zip'
    hashes=read('https://nodejs.org/dist/v'+NODE+'/SHASUMS256.txt').decode()
    node_sha=next(line.split()[0] for line in hashes.splitlines() if line.split()[-1]==node_name)
    node_zip=download('https://nodejs.org/dist/v'+NODE+'/'+node_name,node_name,node_sha)
    node_dir=out/'runtime'/'node';node_dir.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(node_zip) as archive:
        prefix='node-v'+NODE+'-win-x64/'
        for name in ('node.exe','LICENSE'):(node_dir/name).write_bytes(archive.read(prefix+name))
    py_name='python-'+PYTHON+'-embed-amd64.zip'
    py_zip=download('https://www.python.org/ftp/python/'+PYTHON+'/'+py_name,py_name,PYTHON_SHA)
    py_dir=out/'runtime'/'python';py_dir.mkdir(parents=True,exist_ok=True);extract(py_zip,py_dir)
    # ._pth isolates the runtime from installed Python, PYTHONPATH and user site packages.
    (py_dir/'python313._pth').write_text('python313.zip\n.\nLib/site-packages\n../../app\n',encoding='utf-8')
    lock=json.loads((ROOT/'scripts/portable/gis-runtime-lock.json').read_text())
    site=py_dir/'Lib'/'site-packages';site.mkdir(parents=True,exist_ok=True)
    for item in lock:
        local=ROOT/'build/gis-wheels-win313'/item['file']
        if local.is_file() and hashlib.sha256(local.read_bytes()).hexdigest()==item['sha256']:wheel_path=local
        else:wheel_path=download(item['url'],item['file'],item['sha256'])
        extract(wheel_path,site)
    manifest={'platform':'Windows 10/11 x64','node':NODE,'python':PYTHON,'pillow':'12.3.0','gis':{item['name']:item['version'] for item in lock},
              'downloads':[{'file':node_name,'sha256':node_sha,'source':'https://nodejs.org/dist/v'+NODE+'/'},
                           {'file':py_name,'sha256':PYTHON_SHA,'source':'https://www.python.org/ftp/python/'+PYTHON+'/'},*lock]}
    (out/'runtime-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'node':NODE,'python':PYTHON,'pillow':'12.3.0'}),flush=True)

if __name__=='__main__':main()
