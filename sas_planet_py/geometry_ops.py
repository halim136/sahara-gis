"""Vector geometry operations (metric): buffer, offset, simplify, union, difference, convex hull.

Inputs are app marks (point/linestring/polygon with [lon,lat] coords) or GeoJSON
features. Metric operations are done in a local UTM zone, then reprojected to WGS84.
"""
from shapely.geometry import shape, mapping
from shapely.ops import unary_union, transform as sh_transform
from pyproj import Transformer


def _utm_epsg(lon, lat):
    zone = int((lon + 180) // 6) + 1
    return (32600 if lat >= 0 else 32700) + zone


def _mark_to_geom(m):
    t = m.get('type')
    c = m.get('coords')
    if t == 'point':
        return {'type': 'Point', 'coordinates': c}
    if t == 'linestring':
        return {'type': 'LineString', 'coordinates': c}
    if t == 'polygon':
        ring = c if (c and isinstance(c[0][0], (int, float))) else c[0]
        ring = list(ring)
        if ring and ring[0] != ring[-1]:
            ring = ring + [ring[0]]
        return {'type': 'Polygon', 'coordinates': [ring]}
    return None


def _geoms(features):
    out = []
    for f in features:
        g = None
        if isinstance(f, dict):
            if 'geometry' in f:
                g = f['geometry']
            elif 'type' in f and 'coords' in f:
                g = _mark_to_geom(f)
            elif 'coordinates' in f:
                g = f
        if g:
            try:
                out.append(shape(g))
            except Exception:
                pass
    return out


def geom_ops(p):
    op = p.get('op')
    feats = p.get('features') or []
    geoms = _geoms(feats)
    if not geoms:
        raise ValueError('Select at least one feature.')
    c = geoms[0].centroid
    epsg = _utm_epsg(c.x, c.y)
    fwd = Transformer.from_crs(4326, epsg, always_xy=True).transform
    inv = Transformer.from_crs(epsg, 4326, always_xy=True).transform
    pg = [sh_transform(fwd, g) for g in geoms]
    dist = float(p.get('distance', 0) or 0)
    tol = float(p.get('tolerance', 0) or 0)

    if op == 'buffer':
        if dist == 0:
            raise ValueError('Buffer distance (m) must not be zero.')
        res = [g.buffer(dist) for g in pg]
    elif op == 'simplify':
        if tol <= 0:
            raise ValueError('Simplify tolerance (m) must be positive.')
        res = [g.simplify(tol, preserve_topology=True) for g in pg]
    elif op == 'offset':
        if dist == 0:
            raise ValueError('Offset distance (m) must not be zero.')
        side = p.get('side', 'left')
        res = []
        for g in pg:
            try:
                res.append(g.parallel_offset(abs(dist), side))
            except Exception:
                pass
    elif op == 'union':
        res = [unary_union(pg)]
    elif op == 'difference':
        base = pg[0]
        for g in pg[1:]:
            base = base.difference(g)
        res = [base]
    elif op == 'convexhull':
        res = [unary_union(pg).convex_hull]
    else:
        raise ValueError('Unknown geometry operation.')

    out = []
    for g in res:
        if g is None or g.is_empty:
            continue
        out.append({'type': 'Feature', 'properties': {'op': op}, 'geometry': mapping(sh_transform(inv, g))})
    if not out:
        raise ValueError('The operation produced no geometry.')
    return {'geojson': {'type': 'FeatureCollection', 'features': out},
            'statistics': {'op': op, 'inputs': len(geoms), 'outputs': len(out), 'utm_epsg': epsg}}
