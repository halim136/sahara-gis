"""Horn terrain derivatives and Priority-Flood/D8 drainage, using real DEMs.
Horizontal distances and elevations are meters. A full valid 3x3 neighborhood is
required for derivatives. D8 uses steepest descent; flats route along the flood
parent tree, guaranteeing no cycles. Accumulation excludes the cell itself.
"""
import heapq
import math
from collections import deque

D8 = ((0,1,1),(1,1,2),(1,0,4),(1,-1,8),(0,-1,16),(-1,-1,32),(-1,0,64),(-1,1,128))


def valid(value):
    return value is not None and math.isfinite(value)


def terrain_metrics(grid, dx, dy, azimuth=315, altitude=45, z_factor=1):
    rows, cols = len(grid), len(grid[0])
    result = {name:[[None]*cols for _ in range(rows)] for name in ('slope','aspect','hillshade','tpi','roughness')}
    az, alt = math.radians(azimuth), math.radians(altitude)
    light = (math.sin(az)*math.cos(alt), math.cos(az)*math.cos(alt), math.sin(alt))
    for r in range(1,rows-1):
        xstep = dx[r] if isinstance(dx,list) else dx
        ystep = dy[r] if isinstance(dy,list) else dy
        for c in range(1,cols-1):
            window = [grid[y][x] for y in range(r-1,r+2) for x in range(c-1,c+2)]
            if not all(valid(v) for v in window):
                continue
            a,b,cc,d,e,f,g,h,i = window
            east = ((cc+2*f+i)-(a+2*d+g))/(8*xstep)
            north = ((a+2*b+cc)-(g+2*h+i))/(8*ystep)
            magnitude = math.hypot(east,north)
            result['slope'][r][c] = math.degrees(math.atan(magnitude))
            result['aspect'][r][c] = -1.0 if magnitude < 1e-12 else math.degrees(math.atan2(-east,-north))%360
            ex,ny = east*z_factor,north*z_factor
            shade = (-ex*light[0]-ny*light[1]+light[2])/math.sqrt(ex*ex+ny*ny+1)
            result['hillshade'][r][c] = max(0,min(255,round(shade*255)))
            result['tpi'][r][c] = e-(sum(window)-e)/8
            result['roughness'][r][c] = max(window)-min(window)
    return result


def drainage(grid, dx, dy):
    rows, cols = len(grid), len(grid[0])
    filled = [row[:] for row in grid]
    visited, parents, order = set(), {}, {}
    queue = []
    def neighbors(r,c):
        for dr,dc,code in D8:
            y,x=r+dr,c+dc
            if 0<=y<rows and 0<=x<cols and valid(grid[y][x]):
                yield y,x,code
    # All outer edges and cells adjacent to NoData drain out of the analysis domain.
    for r in range(rows):
        for c in range(cols):
            if valid(grid[r][c]) and (r in (0,rows-1) or c in (0,cols-1) or any(not valid(grid[r+dr][c+dc]) for dr,dc,_ in D8)):
                visited.add((r,c)); parents[(r,c)]=None; heapq.heappush(queue,(grid[r][c],r,c))
    while queue:
        height,r,c = heapq.heappop(queue)
        order[(r,c)] = len(order)
        for y,x,_ in neighbors(r,c):
            if (y,x) in visited:
                continue
            visited.add((y,x)); parents[(y,x)]=(r,c)
            filled[y][x] = max(height,grid[y][x])
            heapq.heappush(queue,(filled[y][x],y,x))
    targets, directions = {}, [[None]*cols for _ in range(rows)]
    for r,c in order:
        best, target = 0.0, None
        xstep = dx[r] if isinstance(dx,list) else dx
        ystep = dy[r] if isinstance(dy,list) else dy
        for y,x,_ in neighbors(r,c):
            drop = (filled[r][c]-filled[y][x])/math.hypot((x-c)*xstep,(y-r)*ystep)
            if drop > best:
                best, target = drop, (y,x)
        if target is None and parents[(r,c)] is not None:
            target=parents[(r,c)]
        targets[(r,c)] = target
        directions[r][c] = 0 if target is None else next(code for dr,dc,code in D8 if (r+dr,c+dc)==target)
    incoming = {key:0 for key in targets}
    accumulation = {key:0 for key in targets}
    for target in targets.values():
        if target is not None: incoming[target]+=1
    ready = deque(key for key,count in incoming.items() if count==0)
    processed=0
    while ready:
        key=ready.popleft(); processed+=1
        target=targets[key]
        if target is not None:
            accumulation[target]+=accumulation[key]+1
            incoming[target]-=1
            if incoming[target]==0:ready.append(target)
    if processed!=len(targets):
        raise ValueError('Drainage graph contains a cycle.')
    flow = [[accumulation.get((r,c)) for c in range(cols)] for r in range(rows)]
    depth = [[filled[r][c]-grid[r][c] if valid(grid[r][c]) else None for c in range(cols)] for r in range(rows)]
    return {'filled_dem':filled,'fill_depth':depth,'flow_direction':directions,'flow_accumulation':flow}


def metric_spacing(bbox, rows, cols):
    west,south,east,north=bbox
    dx,dy=(east-west)/cols,(north-south)/rows
    e2=0.0066943799901413165
    xsteps,ysteps=[],[]
    for r in range(rows):
        phi=math.radians(north-(r+.5)*dy)
        q=1-e2*math.sin(phi)**2
        xsteps.append(math.radians(dx)*6378137*math.cos(phi)/math.sqrt(q))
        ysteps.append(math.radians(dy)*6378137*(1-e2)/q**1.5)
    return xsteps,ysteps


def statistics(grid):
    vals=[v for row in grid for v in row if valid(v)]
    if not vals:return {'min':None,'max':None,'mean':None,'valid_cells':0}
    return {'min':min(vals),'max':max(vals),'mean':sum(vals)/len(vals),'valid_cells':len(vals)}
