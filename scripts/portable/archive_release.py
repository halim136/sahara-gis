import hashlib
import sys
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
folder=Path(sys.argv[1]).resolve()
if folder.parent!=ROOT/'releases':raise ValueError('Unexpected release folder')
# Refuse to distribute personal data from a release that was already used.
for private in [folder/'data'/'settings.json',folder/'data'/'browser']:
    if private.exists():raise ValueError('Used portable data exists; build a clean release instead.')
archive=folder.parent/'SAS.Planet-Portable-Windows-x64-v1.5.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as output:
    # Distribute empty source folders, never the user's cached imagery.
    output.writestr('SASPlanet-Portable-v1.5/cache_gmt/','')
    for directory in sorted((folder/'cache_gmt').iterdir()):
        if directory.is_dir():output.writestr('SASPlanet-Portable-v1.5/cache_gmt/'+directory.name+'/','')
    for item in sorted(folder.rglob('*')):
        if not item.is_file():continue
        rel=item.relative_to(folder)
        if '__pycache__' in rel.parts or item.suffix=='.pyc' or item.name.startswith('.env'):continue
        if rel.parts[0] in ('data','cache_gmt') or str(rel).replace('\\','/').startswith(('app/cache/','app/public/exports/')):continue
        output.write(item,Path('SASPlanet-Portable-v1.5')/rel)
checksum=hashlib.sha256(archive.read_bytes()).hexdigest()
archive.with_suffix('.zip.sha256').write_text(checksum+'  '+archive.name+'\n')
print(str(archive),flush=True)
print('Size MB: '+str(round(archive.stat().st_size/1024**2,2)),flush=True)
