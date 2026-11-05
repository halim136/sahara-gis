"""COGO surveying: point by bearing+distance, and closed/open traverse with misclosure."""
from pyproj import Geod

_GEOD = Geod(ellps='WGS84')


def _pt(lon, lat):
    return {'type': 'Point', 'coordinates': [lon, lat]}


def _feat(geom, props):
    return {'type': 'Feature', 'properties': props, 'geometry': geom}


def cogo(p):
    start = p.get('start')
    if not start or len(start) != 2:
        raise ValueError('Provide a start point [lon, lat].')
    slon, slat = float(start[0]), float(start[1])
    if not (-180 <= slon <= 180 and -85 <= slat <= 85):
        raise ValueError('Start point is out of range.')
    mode = p.get('mode', 'point')

    if mode == 'point':
        brng = float(p.get('bearing', 0.0)) % 360.0
        dist = float(p.get('distance', 0.0))
        if not (dist > 0):
            raise ValueError('Distance must be greater than zero.')
        dlon, dlat, _ = _GEOD.fwd(slon, slat, brng, dist)
        name = str(p.get('name') or 'COGO point')[:80]
        feats = [
            _feat(_pt(dlon, dlat), {'name': name, 'bearing_deg': round(brng, 4), 'distance_m': round(dist, 3)}),
            _feat({'type': 'LineString', 'coordinates': [[slon, slat], [dlon, dlat]]}, {'name': name + ' — leg'}),
        ]
        return {'geojson': {'type': 'FeatureCollection', 'features': feats},
                'statistics': {'dest_lon': round(dlon, 8), 'dest_lat': round(dlat, 8), 'bearing_deg': round(brng, 4), 'distance_m': round(dist, 3)}}

    # traverse
    legs = p.get('legs') or []
    if not legs:
        raise ValueError('Provide at least one leg {bearing, distance}.')
    closed = bool(p.get('closed', False))
    name = str(p.get('name') or 'Traverse')[:80]
    pts = [[slon, slat]]
    perim = 0.0
    lon, lat = slon, slat
    for leg in legs:
        b = float(leg.get('bearing', 0.0)) % 360.0
        d = float(leg.get('distance', 0.0))
        if not (d > 0):
            raise ValueError('Each leg distance must be greater than zero.')
        lon, lat, _ = _GEOD.fwd(lon, lat, b, d)
        pts.append([lon, lat])
        perim += d

    stats = {'legs': len(legs), 'perimeter_m': round(perim, 3)}
    if closed:
        az, _, mis = _GEOD.inv(lon, lat, slon, slat)
        stats['misclosure_m'] = round(mis, 4)
        stats['misclosure_bearing_deg'] = round(az % 360.0, 3)
        stats['precision'] = ('1:%d' % round(perim / mis)) if mis > 1e-9 else '1:infinite'
        ring = pts + [[slon, slat]]
        area, _ = _GEOD.polygon_area_perimeter([x for x, _ in ring], [y for _, y in ring])
        stats['area_m2'] = round(abs(area), 3)
        geom = {'type': 'Polygon', 'coordinates': [ring]}
    else:
        geom = {'type': 'LineString', 'coordinates': pts}

    feats = [_feat(geom, {'name': name, **stats})]
    for i, (x, y) in enumerate(pts):
        feats.append(_feat(_pt(x, y), {'name': 'P%d' % i}))
    return {'geojson': {'type': 'FeatureCollection', 'features': feats}, 'statistics': stats}
