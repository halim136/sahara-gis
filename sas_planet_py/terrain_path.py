"""Least-cost (terrain-aware) path over a DEM: good for planning roads/pipelines
that avoid steep slopes. Dijkstra on an elevation grid with a slope penalty."""
import math
import heapq
from .terrain import TerrainReader, validate_bbox


def _haversine(a, b):
    R = 6371000.0
    lon1, lat1 = math.radians(a[0]), math.radians(a[1])
    lon2, lat2 = math.radians(b[0]), math.radians(b[1])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(h)))


def terrain_path(p):
    start, end = p.get('start'), p.get('end')
    if not start or not end or len(start) != 2 or len(end) != 2:
        raise ValueError('Provide start and end points [lon, lat].')
    s_lon, s_lat = float(start[0]), float(start[1])
    e_lon, e_lat = float(end[0]), float(end[1])
    source = p.get('source', 'terrain')
    offline = bool(p.get('offline', False))
    res = int(p.get('resolution', 96))
    if res not in (64, 96, 128, 160):
        res = 96
    slope_weight = float(p.get('slope_weight', 6.0))
    max_slope = float(p.get('max_slope_deg', 0) or 0)

    mlon = abs(e_lon - s_lon) * 0.25 + 0.002
    mlat = abs(e_lat - s_lat) * 0.25 + 0.002
    west, east = min(s_lon, e_lon) - mlon, max(s_lon, e_lon) + mlon
    south, north = min(s_lat, e_lat) - mlat, max(s_lat, e_lat) + mlat
    bbox = [west, south, east, north]
    validate_bbox(bbox)

    grid = TerrainReader(source, offline).grid(bbox, res, res)['grid']
    N = res

    def elev(r, c):
        v = grid[r][c]
        return float(v) if (v is not None and math.isfinite(v)) else None

    def cell(lon, lat):
        c = round((lon - west) / (east - west) * (N - 1))
        r = round((north - lat) / (north - south) * (N - 1))
        return max(0, min(N - 1, r)), max(0, min(N - 1, c))

    sr, sc = cell(s_lon, s_lat)
    er, ec = cell(e_lon, e_lat)
    if elev(sr, sc) is None or elev(er, ec) is None:
        raise ValueError('No elevation coverage at the start or end. Cache terrain or import a DEM first.')

    midlat = (south + north) / 2
    dx = (east - west) * 111320.0 * math.cos(math.radians(midlat)) / (N - 1)
    dy = (north - south) * 111320.0 / (N - 1)
    diag = math.hypot(dx, dy)
    max_tan = math.tan(math.radians(max_slope)) if max_slope > 0 else None
    neigh = [(-1, 0, dy), (1, 0, dy), (0, -1, dx), (0, 1, dx),
             (-1, -1, diag), (-1, 1, diag), (1, -1, diag), (1, 1, diag)]

    INF = float('inf')
    dist = [[INF] * N for _ in range(N)]
    prev = [[None] * N for _ in range(N)]
    dist[sr][sc] = 0.0
    pq = [(0.0, sr, sc)]
    while pq:
        d, r, c = heapq.heappop(pq)
        if d > dist[r][c]:
            continue
        if (r, c) == (er, ec):
            break
        z0 = elev(r, c)
        if z0 is None:
            continue
        for dr, dc, h in neigh:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < N and 0 <= nc < N):
                continue
            z1 = elev(nr, nc)
            if z1 is None:
                continue
            slope = abs(z1 - z0) / h if h > 0 else 0.0
            if max_tan is not None and slope > max_tan:
                continue
            nd = d + h * (1.0 + slope_weight * slope * slope)
            if nd < dist[nr][nc]:
                dist[nr][nc] = nd
                prev[nr][nc] = (r, c)
                heapq.heappush(pq, (nd, nr, nc))

    if dist[er][ec] == INF:
        raise ValueError('No passable route found. Try a larger max slope or a wider area.')

    path = []
    cur = (er, ec)
    while cur is not None:
        r, c = cur
        path.append([west + c / (N - 1) * (east - west), north - r / (N - 1) * (north - south)])
        cur = prev[r][c]
    path.reverse()

    length = sum(_haversine(path[i - 1], path[i]) for i in range(1, len(path)))
    ascent = descent = 0.0
    prevz = elev(sr, sc)
    for lon, lat in path[1:]:
        r, c = cell(lon, lat)
        z = elev(r, c)
        if z is not None and prevz is not None:
            diff = z - prevz
            if diff > 0:
                ascent += diff
            else:
                descent += -diff
            prevz = z
    name = str(p.get('name') or 'Terrain route')[:80]
    feats = [{'type': 'Feature',
              'properties': {'name': name, 'length_m': round(length, 1), 'ascent_m': round(ascent, 1), 'descent_m': round(descent, 1)},
              'geometry': {'type': 'LineString', 'coordinates': path}}]
    return {'geojson': {'type': 'FeatureCollection', 'features': feats},
            'statistics': {'length_m': round(length, 1), 'ascent_m': round(ascent, 1), 'descent_m': round(descent, 1), 'grid': N, 'max_slope_deg': (max_slope or None)}}
