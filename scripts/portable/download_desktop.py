"""Download the official Electron Windows runtime, pinned and SHA256 verified."""
import hashlib,json,urllib.request,zipfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];VERSION='45.2.1';NAME=f'electron-v{VERSION}-win32-x64.zip'
BASE=f'https://github.com/electron/electron/releases/download/v{VERSION}/'
def fetch(url,path):
    if path.is_file():return
    partial=path.with_suffix(path.suffix+'.partial')
    with urllib.request.urlopen(url,timeout=60) as response,partial.open('wb') as out:
        total=0
        while True:
            block=response.read(1024*1024)
            if not block:break
            out.write(block);total+=len(block)
            if total%(25*1024*1024)==0:print(f'Desktop runtime: {total//1024**2} MB',flush=True)
    partial.replace(path)
def main():
    cache=ROOT/'build/desktop-download';cache.mkdir(parents=True,exist_ok=True);checksums=cache/'SHASUMS256.txt';fetch(BASE+'SHASUMS256.txt',checksums)
    expected=next(line.split()[0] for line in checksums.read_text().splitlines() if line.split()[-1].lstrip('*')==NAME)
    archive=cache/NAME;fetch(BASE+NAME,archive)
    digest=hashlib.file_digest(archive.open('rb'),'sha256').hexdigest() if hasattr(hashlib,'file_digest') else hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest!=expected:raise ValueError('Official desktop runtime checksum mismatch.')
    target=ROOT/'build/desktop-runtime';target.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as source:source.extractall(target)
    (cache/'runtime-lock.json').write_text(json.dumps({'name':'Electron','version':VERSION,'file':NAME,'url':BASE+NAME,'sha256':digest,'checksums_url':BASE+'SHASUMS256.txt'},indent=2))
    print('Official Electron runtime extracted and verified: '+VERSION,flush=True)
if __name__=='__main__':main()
