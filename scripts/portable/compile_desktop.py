"""Build the native desktop launcher using Windows .NET (no installer)."""
import os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
    subprocess.run(['python','scripts/portable/create_brand.py'],cwd=ROOT,check=True)
    compiler=Path(os.environ.get('WINDIR','C:/Windows'))/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    target=ROOT/'build/Sahara GIS.exe'
    subprocess.run([str(compiler),'/nologo','/target:winexe','/platform:x64','/optimize+','/utf8output','/reference:System.Windows.Forms.dll','/reference:System.Drawing.dll','/reference:System.Web.Extensions.dll','/win32icon:'+str(ROOT/'public/assets/branding/sahara-gis.ico'),'/win32manifest:'+str(ROOT/'scripts/portable/Launcher.manifest'),'/out:'+str(target),str(ROOT/'scripts/portable/Launcher.cs')],cwd=ROOT,check=True)
    print(str(target))
if __name__=='__main__':main()
