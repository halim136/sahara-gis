"""Nord Sahara 1959 (EPSG:4307), UTM 29N–32N (EPSG:30729–30732).
Clarke 1880 (RGS); WGS84 datum transformation EPSG:1253 (-186,-93,310 m),
published accuracy 44 m. Constants are shared with the browser's Proj4js display.
References: OSGeo/PROJ data/sql/{ellipsoid,projected_crs,helmert_transformation}.sql.
"""
import json
import math
from pathlib import Path
from typing import Dict, Any, Tuple

PARAMETERS=json.loads(Path(__file__).with_name('nord_sahara_params.json').read_text('utf-8'))
CLARKE_A=PARAMETERS['a']
CLARKE_F=1/PARAMETERS['rf']
CLARKE_B=CLARKE_A*(1-CLARKE_F)
CLARKE_E2=CLARKE_F*(2-CLARKE_F)
WGS84_A=6378137.0
WGS84_F=1/298.257223563
WGS84_B=WGS84_A*(1-WGS84_F)
WGS84_E2=WGS84_F*(2-WGS84_F)
DX,DY,DZ=PARAMETERS['towgs84']


def _geographic(lat,lon):
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in (lat,lon)) or not (-90 < lat < 90 and -180 <= lon <= 180):
        raise ValueError('Invalid geographic coordinates.')


def _zone(zone,auto=False):
    if isinstance(zone,bool) or not isinstance(zone,int) or zone not in ([0]+PARAMETERS['zones'] if auto else PARAMETERS['zones']):
        raise ValueError('Use Nord Sahara UTM zone 29, 30, 31 or 32.')


def _cartesian(lat,lon,h,a,f):
    _geographic(lat,lon)
    phi,lam=math.radians(lat),math.radians(lon)
    e2=f*(2-f);n=a/math.sqrt(1-e2*math.sin(phi)**2)
    return ((n+h)*math.cos(phi)*math.cos(lam),(n+h)*math.cos(phi)*math.sin(lam),(n*(1-e2)+h)*math.sin(phi))


def _geodetic(x,y,z,a,f):
    e2=f*(2-f);p=math.hypot(x,y)
    phi=math.atan2(z,p*(1-e2))
    for _ in range(16):
        n=a/math.sqrt(1-e2*math.sin(phi)**2)
        next_phi=math.atan2(z+e2*n*math.sin(phi),p)
        if abs(next_phi-phi)<1e-14:
            phi=next_phi;break
        phi=next_phi
    n=a/math.sqrt(1-e2*math.sin(phi)**2)
    h=p/math.cos(phi)-n
    return math.degrees(phi),math.degrees(math.atan2(y,x)),h


def wgs84_to_nord_sahara_geodetic(lat_wgs,lon_wgs,h_wgs=0.0):
    x,y,z=_cartesian(lat_wgs,lon_wgs,h_wgs,WGS84_A,WGS84_F)
    return _geodetic(x-DX,y-DY,z-DZ,CLARKE_A,CLARKE_F)


def nord_sahara_geodetic_to_wgs84(lat_ns,lon_ns,h_ns=0.0):
    x,y,z=_cartesian(lat_ns,lon_ns,h_ns,CLARKE_A,CLARKE_F)
    return _geodetic(x+DX,y+DY,z+DZ,WGS84_A,WGS84_F)


def nord_sahara_to_utm(lat_ns: float, lon_ns: float, zone: int = 0) -> Dict[str, Any]:
    """
    Project Nord Sahara 1959 coordinates (on Clarke 1880) to UTM grid (Easting, Northing).
    If zone is 0, auto-detects zone (29, 30, 31, or 32).
    """
    _geographic(lat_ns,lon_ns)
    _zone(zone,auto=True)
    if zone == 0:
        zone = int((lon_ns + 180.0) / 6.0) + 1
    _zone(zone)

    # Central meridian
    lon0 = (zone - 1) * 6 - 180 + 3
    lon0_rad = math.radians(lon0)
    lat_rad = math.radians(lat_ns)
    lon_rad = math.radians(lon_ns)

    a = CLARKE_A
    e2 = CLARKE_E2
    e_prime2 = e2 / (1.0 - e2)
    k0 = 0.9996

    n = a / math.sqrt(1.0 - e2 * (math.sin(lat_rad) ** 2))
    t = math.tan(lat_rad) ** 2
    c = e_prime2 * (math.cos(lat_rad) ** 2)
    a_term = math.cos(lat_rad) * (lon_rad - lon0_rad)

    # True distance along the meridian from equator to latitude
    m = a * (
        (1.0 - e2 / 4.0 - 3.0 * (e2**2) / 64.0 - 5.0 * (e2**3) / 256.0) * lat_rad
        - (3.0 * e2 / 8.0 + 3.0 * (e2**2) / 32.0 + 45.0 * (e2**3) / 1024.0) * math.sin(2.0 * lat_rad)
        + (15.0 * (e2**2) / 256.0 + 45.0 * (e2**3) / 1024.0) * math.sin(4.0 * lat_rad)
        - (35.0 * (e2**3) / 3072.0) * math.sin(6.0 * lat_rad)
    )

    easting = 500000.0 + k0 * n * (
        a_term
        + (1.0 - t + c) * (a_term**3) / 6.0
        + (5.0 - 18.0 * t + t**2 + 72.0 * c - 58.0 * e_prime2) * (a_term**5) / 120.0
    )

    northing = k0 * (
        m
        + n * math.tan(lat_rad) * (
            (a_term**2) / 2.0
            + (5.0 - t + 9.0 * c + 4.0 * (c**2)) * (a_term**4) / 24.0
            + (61.0 - 58.0 * t + t**2 + 600.0 * c - 330.0 * e_prime2) * (a_term**6) / 720.0
        )
    )

    epsg_map = {z:30700+z for z in PARAMETERS["zones"]}

    return {
        "zone": zone,
        "hemisphere": "N",
        "easting": round(easting, 2),
        "northing": round(northing, 2),
        "epsg": epsg_map[zone],
        "central_meridian": lon0,
        "transformation_epsg": PARAMETERS["operation"],
        "transformation_accuracy_m": PARAMETERS["accuracy_m"],
        "datum": "Nord Sahara 1959 (Clarke 1880 RGS)",
        "formatted": f"UTM NS {zone}N {int(easting)}E {int(northing)}N"
    }


def utm_to_nord_sahara(easting: float, northing: float, zone: int) -> Tuple[float, float]:
    """Convert UTM Easting/Northing in Nord Sahara 1959 back to geodetic Lat/Lon."""
    _zone(zone)
    if any(isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) for v in (easting,northing)) or not (abs(easting)<=3000000 and 0<=northing<=10000000):
        raise ValueError('Invalid UTM Easting/Northing.')
    k0 = 0.9996
    a = CLARKE_A
    e2 = CLARKE_E2
    e_prime2 = e2 / (1.0 - e2)

    lon0 = (zone - 1) * 6 - 180 + 3
    x = easting - 500000.0
    y = northing

    m = y / k0
    mu = m / (a * (1.0 - e2 / 4.0 - 3.0 * (e2**2) / 64.0 - 5.0 * (e2**3) / 256.0))

    e1 = (1.0 - math.sqrt(1.0 - e2)) / (1.0 + math.sqrt(1.0 - e2))
    phi1 = mu + (3.0 * e1 / 2.0 - 27.0 * (e1**3) / 32.0) * math.sin(2.0 * mu) \
        + (21.0 * (e1**2) / 16.0 - 55.0 * (e1**4) / 32.0) * math.sin(4.0 * mu) \
        + (151.0 * (e1**3) / 96.0) * math.sin(6.0 * mu)

    c1 = e_prime2 * (math.cos(phi1)**2)
    t1 = math.tan(phi1)**2
    n1 = a / math.sqrt(1.0 - e2 * (math.sin(phi1)**2))
    r1 = a * (1.0 - e2) / ((1.0 - e2 * (math.sin(phi1)**2))**1.5)
    d = x / (n1 * k0)

    lat = phi1 - (n1 * math.tan(phi1) / r1) * (
        (d**2) / 2.0
        - (5.0 + 3.0 * t1 + 10.0 * c1 - 4.0 * (c1**2) - 9.0 * e_prime2) * (d**4) / 24.0
        + (61.0 + 90.0 * t1 + 298.0 * c1 + 45.0 * (t1**2) - 252.0 * e_prime2 - 3.0 * (c1**2)) * (d**6) / 720.0
    )

    lon = math.radians(lon0) + (
        d
        - (1.0 + 2.0 * t1 + c1) * (d**3) / 6.0
        + (5.0 - 2.0 * c1 + 28.0 * t1 - 3.0 * (c1**2) + 8.0 * e_prime2 + 24.0 * (t1**2)) * (d**5) / 120.0
    ) / math.cos(phi1)

    return math.degrees(lat), math.degrees(lon)


def wgs84_to_utm_nord_sahara(lat_wgs: float, lon_wgs: float, force_zone: int = 0) -> Dict[str, Any]:
    """
    End-to-end transformation:
    Takes standard WGS84 GPS Lat/Lon -> converts to Nord Sahara 1959 datum -> projects to UTM Zone.
    """
    _geographic(lat_wgs,lon_wgs)
    _zone(force_zone,auto=True)
    west,south,east,north=PARAMETERS['bbox']
    if not (west<=lon_wgs<east and south<=lat_wgs<=north):raise ValueError('Location outside Nord Sahara 1959 area.')
    if force_zone==0:force_zone=int((lon_wgs+180)/6)+1
    lat_ns, lon_ns, _ = wgs84_to_nord_sahara_geodetic(lat_wgs, lon_wgs)
    res = nord_sahara_to_utm(lat_ns, lon_ns, zone=force_zone)
    res["lat_nord_sahara"] = round(lat_ns, 6)
    res["lon_nord_sahara"] = round(lon_ns, 6)
    res["wgs84_input"] = {"lat": lat_wgs, "lon": lon_wgs}
    return res


def utm_nord_sahara_to_wgs84(easting: float, northing: float, zone: int) -> Dict[str, Any]:
    """
    End-to-end inverse transformation:
    Takes UTM Nord Sahara coordinates (Easting, Northing, Zone) -> converts to WGS84 GPS Lat/Lon.
    """
    lat_ns, lon_ns = utm_to_nord_sahara(easting, northing, zone)
    lat_wgs, lon_wgs, _ = nord_sahara_geodetic_to_wgs84(lat_ns, lon_ns)
    return {
        "wgs84_lat": round(lat_wgs, 6),
        "wgs84_lon": round(lon_wgs, 6),
        "nord_sahara_lat": round(lat_ns, 6),
        "nord_sahara_lon": round(lon_ns, 6),
        "zone": zone
    }
