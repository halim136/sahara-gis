"""Automated topographic map sheet: stitch the chosen map source over a selected
grid square, reproject to the chosen CRS, export a georeferenced JP2, and compose
a print-ready PDF sheet (neatline, kilometric grid, title, scale bar, north arrow,
legend box, neighbour index and publisher line)."""
import math
import os
import io
import uuid
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image, ImageFont, ImageDraw
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, A3, A2, A1, A0, landscape
from reportlab.lib.utils import ImageReader
from pyproj import Transformer, CRS as PJCRS
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds
import rasterio
from .gis_common import output_file, download, APP, target_crs, warped_bytes
from .tile_stitcher import TileStitcher

PAGES = {'A4': A4, 'A3': A3, 'A2': A2, 'A1': A1, 'A0': A0}
_ALIASES = {'lambert_nord': 'EPSG:30791', 'lambert_sud': 'EPSG:30792',
            'web_mercator': 'EPSG:3857', 'wgs84': 'EPSG:4326'}


def _resolve_crs(key, bbox):
    if key in ('utm_ns_auto', 'utm_wgs84_auto'):
        return target_crs(key, bbox)
    epsg = _ALIASES.get(key, key)
    if not str(epsg).startswith('EPSG:') or not str(epsg)[5:].isdigit():
        raise ValueError('Select a valid coordinate system.')
    c = PJCRS.from_epsg(int(str(epsg)[5:]))
    return c, c.name


def _auto_utm(bbox):
    lon = (bbox[0] + bbox[2]) / 2
    lat = (bbox[1] + bbox[3]) / 2
    zone = int((lon + 180) // 6) + 1
    return PJCRS.from_epsg((32600 if lat >= 0 else 32700) + zone)


def _title_image(title):
    from arabic_reshaper import reshape
    from bidi.algorithm import get_display
    disp = get_display(reshape(title))
    font = ImageFont.truetype(str(APP / 'public/fonts/NotoSansArabic.ttf'), 72, layout_engine=ImageFont.Layout.BASIC)
    box = font.getbbox(disp)
    img = Image.new('RGBA', (box[2] - box[0] + 20, box[3] - box[1] + 20))
    ImageDraw.Draw(img).text((10 - box[0], 10 - box[1]), disp, font=font, fill='black')
    return img


def topo_sheet(p):
    bbox = [float(v) for v in p['bbox']]
    if not (bbox[0] < bbox[2] and bbox[1] < bbox[3]):
        raise ValueError('Invalid sheet bbox.')
    crs, label = _resolve_crs(p.get('crs', 'utm_ns_auto'), bbox)
    geographic = not crs.is_projected
    work = crs if crs.is_projected else _auto_utm(bbox)
    page = p.get('page', 'A1')
    if page not in PAGES:
        raise ValueError('Select A4, A3, A2, A1 or A0.')
    size = landscape(PAGES[page]) if p.get('landscape', False) else PAGES[page]
    pw, ph = size
    scale = float(p.get('scale', 25000))
    if not 100 <= scale <= 5000000:
        raise ValueError('Scale denominator must be 100–5,000,000.')
    source = p.get('source', 'google_sat')
    zoom = int(p.get('zoom', 15))
    if not 1 <= zoom <= 22:
        raise ValueError('Zoom must be 1–22.')
    offline = bool(p.get('offline', False))
    title = str(p.get('title') or p.get('sheet_id') or 'Topographic map')[:200]

    RC = 150                      # right marginalia column (legend / neighbours)
    x0, y0 = 58, 74
    mw = pw - x0 - RC - 28
    mh = ph - y0 - 58
    if mw < 120 or mh < 120:
        raise ValueError('Page too small for the map frame.')

    fwd = Transformer.from_crs(4326, work.to_wkt(), always_xy=True)
    inv = Transformer.from_crs(work.to_wkt(), 4326, always_xy=True)
    cx, cy = fwd.transform((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
    width = mw * .0254 / 72 * scale
    height = mh * .0254 / 72 * scale
    bounds = [cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2]
    perim = [inv.transform(bounds[0] + width * t, bounds[1] + height * u)
             for t, u in [(i / 20, u) for i in range(21) for u in (0, 1)] + [(u, i / 20) for i in range(21) for u in (0, 1)]]
    gb = [min(x for x, _ in perim), min(y for _, y in perim), max(x for x, _ in perim), max(y for _, y in perim)]

    # Stitch the source tiles over the geographic frame (web mercator), then warp to
    # the working CRS and crop exactly to the printed frame.
    tmp = Path(tempfile.gettempdir()) / (uuid.uuid4().hex + '.tif')
    stitch = TileStitcher.stitch_bbox(source_id=source, bbox=tuple(gb), zoom=zoom,
                                      output_image_path=str(tmp), target_crs='EPSG:3857',
                                      offline=offline)
    raw = tmp.read_bytes()
    for suf in ('.tif', '.tfw', '.wld', '.prj'):
        try:
            os.remove(str(tmp).replace('.tif', suf))
        except OSError:
            pass

    # Embed at the tiles' native ground resolution so the sheet keeps the full
    # detail of the chosen zoom (no blur from downsampling); cap to keep the file
    # and the PDF sane for very large pages / low scales.
    clat = (gb[1] + gb[3]) / 2
    ground_res = 156543.03392 * math.cos(math.radians(clat)) / (2 ** zoom)  # m/px (web mercator)
    native_w = width / ground_res if ground_res > 0 else 4000.0
    px_w = int(min(max(native_w, 1400.0), 12000.0))
    px_h = max(1, round(px_w * mh / mw))
    reference = (from_bounds(*bounds, px_w, px_h), px_w, px_h)
    warped, _ = warped_bytes(raw, work, reference)
    with MemoryFile(warped) as mem, mem.open() as src:
        arr = src.read()
        transform = src.transform
    rgb = np.moveaxis(arr[:3], 0, 2).astype(np.uint8)
    image = Image.fromarray(rgb, 'RGB')

    # Georeferenced JP2 deliverable (working CRS).
    jp2_path = output_file('topo_sheet', '.jp2')
    with rasterio.open(str(jp2_path), 'w', driver='JP2OpenJPEG', width=rgb.shape[1], height=rgb.shape[0],
                       count=3, dtype='uint8', crs=work, transform=transform) as dst:
        dst.write(np.moveaxis(rgb, 2, 0))
    with open(str(jp2_path).replace('.jp2', '.j2w'), 'w', encoding='utf-8') as wf:
        wf.write('\n'.join(str(v) for v in (transform.a, transform.d, transform.b, transform.e,
                                            transform.c + transform.a / 2, transform.f + transform.e / 2)))

    # ---- Compose the PDF sheet ----
    pdf_path = output_file('topo_sheet', '.pdf')
    pdf = canvas.Canvas(str(pdf_path), pagesize=size)
    pdf.setTitle(title)
    _buf = io.BytesIO()
    image.save(_buf, 'JPEG', quality=88, optimize=True)
    _buf.seek(0)
    pdf.drawImage(ImageReader(_buf), x0, y0, mw, mh)

    def PX(x):
        return x0 + (x - bounds[0]) / width * mw

    def PY(y):
        return y0 + (y - bounds[1]) / height * mh

    raw_step = width / 6
    power = 10 ** math.floor(math.log10(raw_step))
    step = next((m * power for m in (1, 2, 5, 10) if m * power >= raw_step), 10 * power)
    xs = np.arange(math.ceil(bounds[0] / step) * step, bounds[2], step)
    ys = np.arange(math.ceil(bounds[1] / step) * step, bounds[3], step)

    pdf.saveState()
    clip = pdf.beginPath()
    clip.rect(x0, y0, mw, mh)
    pdf.clipPath(clip, stroke=0)
    pdf.setStrokeColorRGB(.80, .13, .13)    # red kilometric grid, like the classic sheets
    pdf.setLineWidth(.4)
    for x in xs:
        pdf.line(PX(x), y0, PX(x), y0 + mh)
    for y in ys:
        pdf.line(x0, PY(y), x0 + mw, PY(y))
    pdf.restoreState()

    pdf.setStrokeColorRGB(0, 0, 0)
    pdf.setLineWidth(1.3)
    pdf.rect(x0, y0, mw, mh)

    pdf.setFont('Helvetica', 6.5)
    pdf.setFillColorRGB(0, 0, 0)
    if geographic:
        for x in xs:
            if x0 < PX(x) < x0 + mw:
                lon, _ = inv.transform(x, cy)
                pdf.drawCentredString(PX(x), y0 - 9, '%.3f' % lon)
                pdf.drawCentredString(PX(x), y0 + mh + 4, '%.3f' % lon)
        for y in ys:
            if y0 < PY(y) < y0 + mh:
                _, lat = inv.transform(cx, y)
                for xx in (x0 - 8, x0 + mw + 10):
                    pdf.saveState(); pdf.translate(xx, PY(y)); pdf.rotate(90); pdf.drawCentredString(0, 0, '%.3f' % lat); pdf.restoreState()
    else:
        for x in xs:
            if x0 < PX(x) < x0 + mw:
                pdf.drawCentredString(PX(x), y0 - 9, str(round(x / 1000)))
                pdf.drawCentredString(PX(x), y0 + mh + 4, str(round(x / 1000)))
        for y in ys:
            if y0 < PY(y) < y0 + mh:
                for xx in (x0 - 8, x0 + mw + 10):
                    pdf.saveState(); pdf.translate(xx, PY(y)); pdf.rotate(90); pdf.drawCentredString(0, 0, str(round(y / 1000))); pdf.restoreState()

    # Title (Arabic-aware) + subtitle.
    if any('؀' <= c <= 'ۿ' for c in title):
        ti = _title_image(title)
        tw = min(mw, ti.width / ti.height * 26)
        pdf.drawImage(ImageReader(ti), x0 + (mw - tw) / 2, ph - 52, tw, 26, mask='auto')
    else:
        pdf.setFont('Helvetica-Bold', 18)
        pdf.drawCentredString(x0 + mw / 2, ph - 42, title)
    pdf.setFont('Helvetica-Bold', 9)
    pdf.drawCentredString(x0 + mw / 2, ph - 26, ('ALGÉRIE   1:' + format(round(scale), ',')))

    # Scale bar (metric), derived from the same map-to-paper transform.
    bar = step
    bw = bar / width * mw
    while bw > mw * .33:
        bar /= 2; bw = bar / width * mw
    pdf.setFillColorRGB(0, 0, 0)
    pdf.rect(x0, 46, bw / 2, 5, fill=1)
    pdf.rect(x0 + bw / 2, 46, bw / 2, 5)
    pdf.setFont('Helvetica', 7)
    pdf.drawString(x0, 35, '0')
    pdf.drawRightString(x0 + bw, 35, (str(round(bar)) + ' m' if bar < 1000 else str(round(bar / 1000)) + ' km'))

    # North arrow.
    nx, ny = x0 + mw - 18, y0 + mh - 40
    ar = pdf.beginPath(); ar.moveTo(nx, ny + 24); ar.lineTo(nx - 6, ny); ar.lineTo(nx, ny + 5); ar.lineTo(nx + 6, ny); ar.close()
    pdf.drawPath(ar, fill=1)
    pdf.setFont('Helvetica-Bold', 10)
    pdf.drawCentredString(nx, ny + 28, 'N')

    pdf.setFont('Helvetica', 7)
    pdf.drawString(x0, 24, label + '  ·  Grid north  ·  ' + ('Lon/Lat graticule' if geographic else 'Grid ' + (str(round(step / 1000)) + ' km' if step >= 1000 else str(round(step)) + ' m')))
    pdf.drawRightString(x0 + mw, 24, 'Zoom Z' + str(zoom) + '  ·  ' + str(source))

    # ---- Right marginalia column: legend + neighbour index ----
    lx = pw - RC - 14
    ly = y0
    pdf.setStrokeColorRGB(0, 0, 0)
    pdf.setLineWidth(.8)
    pdf.rect(lx, ly, RC, mh)
    top = ly + mh - 16
    pdf.setFont('Helvetica-Bold', 9)
    pdf.drawCentredString(lx + RC / 2, top, 'LÉGENDE')
    pdf.line(lx + 6, top - 4, lx + RC - 6, top - 4)
    legend = p.get('legend')
    if not isinstance(legend, list) or not legend:
        legend = ['Route principale', 'Piste', 'Oued / cours d\'eau', 'Courbe de niveau',
                  'Agglomération', 'Point coté', 'Limite de feuille']
    pdf.setFont('Helvetica', 7.5)
    yy = top - 20
    for item in legend[:16]:
        pdf.setFillColorRGB(.1, .1, .1)
        pdf.rect(lx + 8, yy, 10, 6, fill=1)
        pdf.setFillColorRGB(0, 0, 0)
        pdf.drawString(lx + 24, yy, str(item).encode('ascii', 'replace').decode()[:26])
        yy -= 14
        if yy < ly + 120:
            break

    # Neighbour index (3x3, centre highlighted).
    iy = ly + 60
    cell = (RC - 40) / 3
    pdf.setFont('Helvetica-Bold', 7)
    pdf.drawString(lx + 8, iy + 3 * cell + 8, 'Feuilles voisines')
    for r in range(3):
        for c in range(3):
            X = lx + 20 + c * cell
            Y = iy + (2 - r) * cell
            if r == 1 and c == 1:
                pdf.setFillColorRGB(.85, .85, .85); pdf.rect(X, Y, cell, cell, fill=1); pdf.setFillColorRGB(0, 0, 0)
            pdf.rect(X, Y, cell, cell)
    sid = str(p.get('sheet_id') or title)[:16]
    pdf.setFont('Helvetica', 5.5)
    pdf.drawCentredString(lx + 20 + 1.5 * cell, iy + 1.5 * cell - 2, sid)

    # CRS / sheet note inside the box.
    pdf.setFont('Helvetica', 6.5)
    pdf.drawString(lx + 8, ly + 34, 'CRS: ' + label.encode('ascii', 'replace').decode()[:30])
    pdf.drawString(lx + 8, ly + 24, 'Feuille: ' + sid)
    pdf.drawString(lx + 8, ly + 14, '1:' + format(round(scale), ',') + ' · ' + page)

    # Publisher line.
    pub = str(p.get('publisher') or 'Sahara GIS — صحارى GIS · Service cartographique')[:160]
    pdf.setFont('Helvetica', 7)
    pdf.drawCentredString(pw / 2, 10, pub.encode('ascii', 'replace').decode())

    pdf.showPage()
    pdf.save()
    return {'files': [{'name': page + ' topographic PDF', 'url': download(pdf_path)},
                      {'name': 'Georeferenced JP2', 'url': download(jp2_path)}],
            'statistics': {'scale': scale, 'page': page, 'crs': label, 'zoom': zoom,
                           'grid_step_m': step, 'map_bounds': bounds, 'geographic_bbox': gb,
                           'source': source, 'image_px': [px_w, px_h], 'offline': offline,
                           'tiles': stitch.get('total_tiles'),
                           'from_cache': stitch.get('from_cache'),
                           'downloaded': stitch.get('downloaded'),
                           'missing_tiles': max(0, (stitch.get('total_tiles') or 0) - (stitch.get('downloaded_or_cached') or 0))}}
