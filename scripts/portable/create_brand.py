"""Original Sahara GIS icon: desert dunes, mountains and a compass."""
from pathlib import Path
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'public/assets/branding';OUT.mkdir(parents=True,exist_ok=True)
scale=4;im=Image.new('RGBA',(256*scale,256*scale));d=ImageDraw.Draw(im)
def xy(points):return [(int(x*scale),int(y*scale)) for x,y in points]
d.rounded_rectangle((8*scale,8*scale,248*scale,248*scale),radius=52*scale,fill='#113f4a',outline='#267d86',width=3*scale)
for x in (60,104,148,192):d.line(xy([(x,32),(x,224)]),fill='#23535b',width=scale)
for y in (64,108,152,196):d.line(xy([(32,y),(224,y)]),fill='#23535b',width=scale)
d.ellipse((159*scale,43*scale,207*scale,91*scale),fill='#f5bb58')
d.polygon(xy([(30,165),(95,71),(142,133),(169,100),(225,174)]),fill='#568f91')
d.polygon(xy([(63,117),(95,71),(125,111),(106,103),(95,113),(84,103)]),fill='#edf1db')
d.polygon(xy([(30,178),(68,157),(112,145),(154,148),(202,165),(228,174),(228,216),(28,216)]),fill='#d59a48')
d.polygon(xy([(29,204),(65,186),(106,174),(145,174),(183,189),(228,205),(218,225),(50,229)]),fill='#f1c478')
d.line(xy([(40,209),(83,191),(125,185),(166,190),(213,210)]),fill='#ffdf9e',width=3*scale)
d.polygon(xy([(202,106),(208,120),(222,126),(208,132),(202,146),(196,132),(182,126),(196,120)]),fill='#f1f5ef')
im=im.resize((256,256),Image.Resampling.LANCZOS);im.save(OUT/'sahara-gis.png');im.save(OUT/'sahara-gis.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print(str(OUT/'sahara-gis.ico'))
