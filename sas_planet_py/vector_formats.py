"""Small, local vector importer/exporter for the formats used by SAS.Planet.

All imported coordinates are returned in WGS 84 longitude/latitude.  KML/KMZ and
GPX are defined in WGS 84; a zipped Shapefile must include its ``.prj`` file so
its coordinates can be converted safely.
"""
import binascii
import html
import json
import math
import re
import struct
import uuid
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from pyproj import CRS, Transformer


MAX_FEATURES = 50000
MAX_VECTOR_BYTES = 64 * 1024 * 1024


def _coordinate(value: Iterable[Any]) -> List[float]:
    point = list(value)
    if len(point) < 2:
        raise ValueError("A geometry contains an incomplete coordinate.")
    lon, lat = float(point[0]), float(point[1])
    if not math.isfinite(lon + lat) or not -180 <= lon <= 180 or not -90 <= lat <= 90:
        raise ValueError("A geometry has an invalid WGS84 coordinate.")
    return [lon, lat]


def _mark(name: str, kind: str, coords: Any, properties: Dict[str, Any] | None = None,
          description: str = "") -> Dict[str, Any]:
    return {
        "id": uuid.uuid4().hex,
        "name": name or "Feature",
        "type": kind,
        "coords": coords,
        "description": description or json.dumps(properties or {}, ensure_ascii=False),
        "color": "#0b8a87" if kind == "linestring" else "#8b5cf6",
        "category": "Imported vector",
        "properties": properties or {},
    }


def _marks_from_geometry(geometry: Dict[str, Any], properties: Dict[str, Any] | None = None,
                         name: str = "Feature", description: str = "") -> List[Dict[str, Any]]:
    """Flatten multipart geometry to the mark primitives understood by the map UI."""
    geometry = geometry or {}
    kind = geometry.get("type")
    coords = geometry.get("coordinates")
    props = properties or {}
    if kind == "Point":
        return [_mark(name, "point", _coordinate(coords), props, description)]
    if kind == "LineString":
        line = [_coordinate(p) for p in coords or []]
        return [_mark(name, "linestring", line, props, description)] if len(line) >= 2 else []
    if kind == "Polygon":
        rings = [[_coordinate(p) for p in ring] for ring in coords or []]
        return [_mark(name, "polygon", rings[0], {**props, "holes": rings[1:]}, description)] if rings and len(rings[0]) >= 3 else []
    if kind == "MultiPoint":
        return [_mark(f"{name} {i + 1}", "point", _coordinate(p), props, description) for i, p in enumerate(coords or [])]
    if kind == "MultiLineString":
        out: List[Dict[str, Any]] = []
        for i, line in enumerate(coords or []):
            out += _marks_from_geometry({"type": "LineString", "coordinates": line}, props, f"{name} {i + 1}", description)
        return out
    if kind == "MultiPolygon":
        out: List[Dict[str, Any]] = []
        for i, polygon in enumerate(coords or []):
            out += _marks_from_geometry({"type": "Polygon", "coordinates": polygon}, props, f"{name} {i + 1}", description)
        return out
    if kind == "GeometryCollection":
        out: List[Dict[str, Any]] = []
        for i, child in enumerate(geometry.get("geometries") or []):
            out += _marks_from_geometry(child, props, f"{name} {i + 1}", description)
        return out
    return []


def _marks_from_geojson(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    if data.get("type") == "FeatureCollection":
        features = data.get("features") or []
    elif data.get("type") == "Feature":
        features = [data]
    else:
        features = [{"type": "Feature", "properties": {}, "geometry": data}]
    if len(features) > MAX_FEATURES:
        raise ValueError(f"Vector import is limited to {MAX_FEATURES:,} features.")
    out: List[Dict[str, Any]] = []
    for index, feature in enumerate(features):
        props = feature.get("properties") or {}
        name = str(props.get("name") or props.get("Name") or props.get("title") or f"Feature {index + 1}")
        out += _marks_from_geometry(feature.get("geometry") or {}, props, name, str(props.get("description") or ""))
    return out


def _local_name(node: ET.Element) -> str:
    return node.tag.rsplit("}", 1)[-1]


def _first(node: ET.Element | None, name: str) -> ET.Element | None:
    if node is None:
        return None
    return next((child for child in node.iter() if _local_name(child) == name), None)


def _kml_coordinates(element: ET.Element | None) -> List[List[float]]:
    if element is None or not element.text:
        return []
    result: List[List[float]] = []
    for token in element.text.replace("\n", " ").replace("\t", " ").split():
        values = token.split(",")
        if len(values) >= 2:
            result.append(_coordinate(values[:2]))
    return result


def _parse_kml(content: str) -> List[Dict[str, Any]]:
    root = ET.fromstring(content)
    marks: List[Dict[str, Any]] = []
    placemarks = [node for node in root.iter() if _local_name(node) == "Placemark"]
    for index, place in enumerate(placemarks):
        name_node, desc_node = _first(place, "name"), _first(place, "description")
        name = name_node.text.strip() if name_node is not None and name_node.text else f"Placemark {index + 1}"
        description = desc_node.text if desc_node is not None and desc_node.text else ""
        polygons = [node for node in place.iter() if _local_name(node) == "Polygon"]
        if polygons:
            for polygon in polygons:
                outer = next((ring for ring in polygon.iter() if _local_name(ring) == "LinearRing"), None)
                ring = _kml_coordinates(_first(outer, "coordinates"))
                if len(ring) >= 3:
                    marks.append(_mark(name, "polygon", ring, {}, description))
            continue
        for child in place.iter():
            geometry_type = _local_name(child)
            if geometry_type not in ("Point", "LineString"):
                continue
            coordinates = _kml_coordinates(_first(child, "coordinates"))
            if geometry_type == "Point" and coordinates:
                marks.append(_mark(name, "point", coordinates[0], {}, description))
            elif geometry_type == "LineString" and len(coordinates) >= 2:
                marks.append(_mark(name, "linestring", coordinates, {}, description))
    return marks


# ---------------------------------------------------------------------------
# SAS.Planet marks database (.sml) importer
#
# A ``.sml`` file is a Delphi ``TClientDataSet`` serialised as a MIDAS
# ``DATAPACKET`` XML document.  Geometry lives in the ``LonLatArr`` blob as a
# packed array of 24-byte records: two 80-bit x87 ``Extended`` floats (lon, lat)
# followed by 4 reserved bytes.  NaN / out-of-range points separate the parts of
# multi-geometries, and a repeated first/last point marks a closed polygon.
# Reference: SAS.Planet Src/MarksDB/SML/u_GeometryFromStreamSML.pas.
# ---------------------------------------------------------------------------

_SML_POINT_SIZE = 24
# Only these description fields are retained on import (per the field spec).
_SML_WANTED_FIELDS = ("id", "nom", "type", "n_50000", "coup", "num")


def _read_extended80(raw: bytes) -> float:
    """Decode a 10-byte little-endian x87 ``Extended`` float."""
    mantissa = int.from_bytes(raw[0:8], "little")
    sign_exp = int.from_bytes(raw[8:10], "little")
    sign = -1.0 if (sign_exp >> 15) & 1 else 1.0
    exponent = sign_exp & 0x7FFF
    if exponent == 0x7FFF:
        return math.nan if (mantissa << 1) & ((1 << 64) - 1) else sign * math.inf
    if exponent == 0 and mantissa == 0:
        return sign * 0.0
    return sign * mantissa * 2.0 ** (exponent - 16383 - 63)


def _sml_geometry_points(blob: bytes) -> List[Optional[List[float]]]:
    """Return the blob's lon/lat points; ``None`` marks a part separator."""
    points: List[Optional[List[float]]] = []
    for offset in range(0, len(blob) - _SML_POINT_SIZE + 1, _SML_POINT_SIZE):
        lon = _read_extended80(blob[offset:offset + 10])
        lat = _read_extended80(blob[offset + 10:offset + 20])
        if not (math.isfinite(lon) and math.isfinite(lat)) or abs(lon) >= 360 or abs(lat) >= 360:
            points.append(None)
        else:
            points.append([lon, lat])
    return points


def _sml_marks_from_blob(blob: bytes, name: str, description: str,
                         properties: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Turn one SAS.Planet geometry blob into map marks (point/line/polygon)."""
    points = _sml_geometry_points(blob)
    count = len(points)
    if count == 0:
        return []
    if count == 1:
        return [_mark(name, "point", points[0], properties, description)] if points[0] is not None else []
    first, last = points[0], points[-1]
    is_polygon = False
    if first is not None and last is not None and first == last:
        is_polygon, count = True, count - 1   # drop the repeated closing vertex
    elif last is None:
        count -= 1                            # drop a trailing separator
    parts: List[List[List[float]]] = []
    current: List[List[float]] = []
    for point in points[:count]:
        if point is None:
            if current:
                parts.append(current)
                current = []
        else:
            current.append(point)
    if current:
        parts.append(current)
    if not parts:
        return []
    if is_polygon:
        rings = [ring for ring in parts if len(ring) >= 3]
        if not rings:
            return []
        return [_mark(name, "polygon", rings[0], {**properties, "holes": rings[1:]}, description)]
    if len(parts) == 1 and len(parts[0]) == 1:
        return [_mark(name, "point", parts[0][0], properties, description)]
    marks: List[Dict[str, Any]] = []
    for index, line in enumerate(parts):
        if len(line) >= 2:
            label = name if len(parts) == 1 else f"{name} {index + 1}"
            marks.append(_mark(label, "linestring", line, properties, description))
        elif len(line) == 1:
            marks.append(_mark(name, "point", line[0], properties, description))
    return marks


def _sml_field_map(metadata: ET.Element | None) -> Dict[str, tuple]:
    """Map each DATAPACKET field name (lower-cased) to (fieldtype, subtype)."""
    result: Dict[str, tuple] = {}
    if metadata is None:
        return result
    for field in metadata.iter():
        if _local_name(field) != "FIELD":
            continue
        attrib = {key.lower(): value for key, value in field.attrib.items()}
        name = attrib.get("attrname")
        if name:
            result[name.lower()] = (attrib.get("fieldtype", "").lower(), attrib.get("subtype", ""))
    return result


def _sml_decode_value(raw: Optional[str], meta: tuple) -> str:
    """Decode a ROW attribute to text, honouring ``bin.hex`` wide/ANSI blobs."""
    if raw is None:
        return ""
    fieldtype, subtype = meta if meta else ("", "")
    if fieldtype.startswith("bin.hex") or (not fieldtype and re.fullmatch(r"[0-9A-Fa-f]+", raw) and len(raw) % 2 == 0 and len(raw) > 8):
        try:
            data = binascii.unhexlify(raw)
        except (binascii.Error, ValueError):
            return raw
        if subtype.lower().startswith("wide"):
            return data.decode("utf-16-le", "replace").rstrip("\x00")
        return _decode_text(data)
    return raw


def _sml_blob_bytes(raw: Optional[str]) -> bytes:
    if not raw:
        return b""
    try:
        return binascii.unhexlify(raw)
    except (binascii.Error, ValueError):
        return b""


def _sml_extract_fields(description: str) -> Dict[str, str]:
    """Pull only the wanted ``key = value`` pairs out of a mark description."""
    text = description or ""
    found: Dict[str, str] = {}
    wanted = {name.lower(): name for name in _SML_WANTED_FIELDS}
    # HTML table layout: <tr><td>key</td><td>value</td></tr>
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.IGNORECASE | re.DOTALL):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", cell)).strip()
                 for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.IGNORECASE | re.DOTALL)]
        if len(cells) >= 2 and cells[0].lower() in wanted and wanted[cells[0].lower()] not in found:
            found[wanted[cells[0].lower()]] = cells[1]
    # Plain "key = value" / "key : value" lines (after stripping any markup).
    flattened = re.sub(r"<(br|/tr|/p|/div|/li)[^>]*>", "\n", text, flags=re.IGNORECASE)
    flattened = html.unescape(re.sub(r"<[^>]+>", "\n", flattened))
    for line in flattened.splitlines():
        match = re.match(r"\s*([A-Za-z0-9_]+)\s*[=:]\s*(.*?)\s*$", line)
        if match and match.group(1).lower() in wanted and wanted[match.group(1).lower()] not in found:
            found[wanted[match.group(1).lower()]] = match.group(2)
    # Preserve the canonical field order.
    return {name: found[name] for name in _SML_WANTED_FIELDS if name in found}


def _parse_sml(data: bytes) -> List[Dict[str, Any]]:
    """Parse a SAS.Planet ``.sml`` marks database into map marks."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as error:
        raise ValueError("The .sml file is not a valid SAS.Planet marks database.") from error
    metadata = next((node for node in root.iter() if _local_name(node) == "METADATA"), None)
    fields = _sml_field_map(metadata)
    rows = [node for node in root.iter() if _local_name(node) == "ROW"]
    if not rows:
        raise ValueError("No marks (ROW records) were found in the .sml file.")
    if len(rows) > MAX_FEATURES:
        raise ValueError(f"Vector import is limited to {MAX_FEATURES:,} features.")

    def attribute(row: ET.Element, key: str) -> Optional[str]:
        for name, value in row.attrib.items():
            if name.lower() == key:
                return value
        return None

    geometry_key = next((key for key in fields if key in ("lonlatarr", "lonlat", "points")), "lonlatarr")
    marks: List[Dict[str, Any]] = []
    for index, row in enumerate(rows):
        blob = _sml_blob_bytes(attribute(row, geometry_key))
        if not blob:
            continue
        row_name = _sml_decode_value(attribute(row, "name"), fields.get("name", ()))
        raw_descr = attribute(row, "descr")
        if raw_descr is None:
            raw_descr = attribute(row, "descript")
            descr_meta = fields.get("descript", ())
        else:
            descr_meta = fields.get("descr", ())
        description = _sml_decode_value(raw_descr, descr_meta)
        attributes = _sml_extract_fields(description)
        name = attributes.get("nom") or attributes.get("type") or row_name or f"Sheet {index + 1}"
        readable = "\n".join(f"{key} = {value}" for key, value in attributes.items())
        properties = {**attributes, "source_name": row_name}
        marks += _sml_marks_from_blob(blob, name, readable, properties)
        if len(marks) > MAX_FEATURES:
            raise ValueError(f"Vector import is limited to {MAX_FEATURES:,} features.")
    if not marks:
        raise ValueError("The .sml marks have no readable geometry.")
    return marks


# ---------------------------------------------------------------------------
# SAS.Planet marks database (.db3) importer
#
# The newer ``.db3`` marks store is an mORMot SQLite database.  Marks live in a
# ``Mark`` table whose ``mGeoWKB`` column holds standard OGC WKB geometry in
# WGS 84 lon/lat, with ``mName`` / ``mDesc`` text columns.  We discover the
# table/columns defensively so schema tweaks do not break the import.
# Reference: SAS.Planet Src/MarksDB/mORMot + Src/Geometry/u_GeometryFromWKB.pas.
# ---------------------------------------------------------------------------

_SQLITE_MAGIC = b"SQLite format 3\x00"


def _db3_pick_columns(columns: List[str]) -> Optional[tuple]:
    """Return (geometry, name, description) column names for a marks table."""
    lower = {name.lower(): name for name in columns}
    geometry = next((lower[key] for key in lower if "wkb" in key or key in ("geometry", "geo", "the_geom")), None)
    if geometry is None:
        return None
    name = next((lower[key] for key in ("mname", "name") if key in lower), None)
    description = next((lower[key] for key in ("mdesc", "descr", "description", "desc") if key in lower), None)
    return geometry, name, description


def _parse_db3(path: Path) -> List[Dict[str, Any]]:
    """Parse a SAS.Planet ``.db3`` SQLite marks database into map marks."""
    import sqlite3
    from shapely import wkb as shapely_wkb
    from shapely.geometry import mapping

    with path.open("rb") as handle:
        if handle.read(16) != _SQLITE_MAGIC:
            raise ValueError("The .db3 file is not a SAS.Planet SQLite marks database.")

    connection = sqlite3.connect("file:{}?mode=ro".format(path.as_uri()[7:]), uri=True)
    try:
        tables = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        target = None
        for table in tables:
            columns = [row[1] for row in connection.execute('PRAGMA table_info("%s")' % table.replace('"', '""'))]
            picked = _db3_pick_columns(columns)
            # Prefer the geometry table named like "Mark" over any FTS/view mirror.
            if picked and (target is None or table.lower() == "mark"):
                target = (table, picked)
                if table.lower() == "mark":
                    break
        if target is None:
            raise ValueError("No marks table with WKB geometry was found in the .db3 file.")
        table, (geometry_col, name_col, desc_col) = target

        def column_sql(name: Optional[str]) -> str:
            return '"%s"' % name.replace('"', '""') if name else "NULL"

        query = 'SELECT %s, %s, %s FROM "%s"' % (
            column_sql(geometry_col), column_sql(name_col), column_sql(desc_col),
            table.replace('"', '""'))
        marks: List[Dict[str, Any]] = []
        for index, (blob, row_name, description) in enumerate(connection.execute(query)):
            if not blob:
                continue
            try:
                geometry = shapely_wkb.loads(bytes(blob))
            except Exception:
                continue
            if geometry.is_empty:
                continue
            attributes = _sml_extract_fields(description or "")
            name = attributes.get("nom") or attributes.get("type") or (row_name or "").strip() or f"Sheet {index + 1}"
            readable = "\n".join(f"{key} = {value}" for key, value in attributes.items())
            properties = {**attributes, "source_name": (row_name or "").strip()}
            marks += _marks_from_geometry(mapping(geometry), properties, name, readable)
            if len(marks) > MAX_FEATURES:
                raise ValueError(f"Vector import is limited to {MAX_FEATURES:,} features.")
    finally:
        connection.close()
    if not marks:
        raise ValueError("The .db3 marks have no readable geometry.")
    return marks


def _decode_text(raw: bytes) -> str:
    for encoding in ("utf-8", "cp1256", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", "replace").strip()


def _read_dbf(data: bytes) -> List[Dict[str, Any]]:
    if len(data) < 33:
        return []
    count = struct.unpack_from("<I", data, 4)[0]
    header_size = struct.unpack_from("<H", data, 8)[0]
    record_size = struct.unpack_from("<H", data, 10)[0]
    fields, offset = [], 32
    while offset + 32 <= len(data) and data[offset] != 0x0D:
        desc = data[offset:offset + 32]
        fields.append((_decode_text(desc[:11].split(b"\0", 1)[0]), chr(desc[11]), desc[16]))
        offset += 32
    rows: List[Dict[str, Any]] = []
    for index in range(min(count, MAX_FEATURES)):
        start = header_size + index * record_size
        record = data[start:start + record_size]
        if len(record) < record_size or record[:1] == b"*":
            continue
        row, cursor = {}, 1
        for name, kind, width in fields:
            raw = _decode_text(record[cursor:cursor + width])
            cursor += width
            if raw:
                if kind in "NF":
                    try:
                        row[name] = float(raw) if "." in raw else int(raw)
                    except ValueError:
                        row[name] = raw
                else:
                    row[name] = raw
        rows.append(row)
    return rows


def _shapefile_geometries(data: bytes) -> List[Dict[str, Any]]:
    if len(data) < 100 or struct.unpack_from(">I", data, 0)[0] != 9994:
        raise ValueError("The ZIP does not contain a valid Shapefile .shp member.")
    geometries: List[Dict[str, Any]] = []
    offset = 100
    while offset + 8 <= len(data) and len(geometries) < MAX_FEATURES:
        content_words = struct.unpack_from(">I", data, offset + 4)[0]
        start, end = offset + 8, offset + 8 + content_words * 2
        offset = end
        if end > len(data) or start + 4 > end:
            break
        shape_type = struct.unpack_from("<I", data, start)[0]
        if shape_type == 0:
            geometries.append({})
        elif shape_type == 1 and start + 20 <= end:
            geometries.append({"type": "Point", "coordinates": list(struct.unpack_from("<dd", data, start + 4))})
        elif shape_type in (3, 5, 8) and start + 40 <= end:
            if shape_type == 8:
                amount = struct.unpack_from("<I", data, start + 36)[0]
                points = [list(struct.unpack_from("<dd", data, start + 40 + i * 16)) for i in range(amount) if start + 56 + i * 16 <= end]
                geometries.append({"type": "MultiPoint", "coordinates": points})
                continue
            parts, points_count = struct.unpack_from("<II", data, start + 36)
            parts_start = start + 44
            points_start = parts_start + parts * 4
            boundaries = list(struct.unpack_from("<" + "I" * parts, data, parts_start)) + [points_count]
            all_points = [list(struct.unpack_from("<dd", data, points_start + i * 16)) for i in range(points_count) if points_start + 16 * (i + 1) <= end]
            sequences = [all_points[boundaries[i]:boundaries[i + 1]] for i in range(parts) if boundaries[i] < len(all_points)]
            if shape_type == 3:
                geometries.append({"type": "LineString" if len(sequences) == 1 else "MultiLineString", "coordinates": sequences[0] if len(sequences) == 1 else sequences})
            else:
                geometries.append({"type": "Polygon" if len(sequences) == 1 else "MultiPolygon", "coordinates": [sequences[0]] if len(sequences) == 1 else [[ring] for ring in sequences]})
        else:
            geometries.append({})
    return geometries


def _reproject_geometry(geometry: Dict[str, Any], source_crs: str | None) -> Dict[str, Any]:
    if not source_crs:
        raise ValueError("Shapefile ZIP must include a .prj projection file.")
    crs = CRS.from_user_input(source_crs)
    if crs.equals(CRS.from_epsg(4326)):
        return geometry
    transform = Transformer.from_crs(crs, 4326, always_xy=True).transform
    def point(value: List[Any]) -> List[float]:
        lon, lat = transform(float(value[0]), float(value[1]))
        return _coordinate([lon, lat])
    def map_coordinates(value: Any) -> Any:
        if value and isinstance(value[0], (int, float)):
            return point(value)
        return [map_coordinates(child) for child in value or []]
    return {**geometry, "coordinates": map_coordinates(geometry.get("coordinates"))}


def _parse_shapefile_zip(path: Path) -> List[Dict[str, Any]]:
    with zipfile.ZipFile(path) as archive:
        members = [info for info in archive.infolist() if not info.is_dir()]
        if sum(info.file_size for info in members) > MAX_VECTOR_BYTES:
            raise ValueError("The Shapefile ZIP is larger than 64 MB when unpacked.")
        shp = next((info for info in members if info.filename.lower().endswith(".shp")), None)
        if not shp:
            raise ValueError("ZIP import needs a Shapefile .shp member.")
        stem = Path(shp.filename).with_suffix("").name.lower()
        def companion(ext: str):
            return next((item for item in members if Path(item.filename).stem.lower() == stem and item.filename.lower().endswith(ext)), None)
        dbf, prj = companion(".dbf"), companion(".prj")
        geometries = _shapefile_geometries(archive.read(shp))
        attributes = _read_dbf(archive.read(dbf)) if dbf else []
        crs = _decode_text(archive.read(prj)) if prj else None
        marks: List[Dict[str, Any]] = []
        for index, geometry in enumerate(geometries):
            if not geometry:
                continue
            props = attributes[index] if index < len(attributes) else {}
            converted = _reproject_geometry(geometry, crs)
            marks += _marks_from_geometry(converted, props, str(props.get("name") or props.get("NAME") or f"Feature {index + 1}"))
        return marks


def parse_vector_data(content: str) -> Dict[str, Any]:
    """Parse text GeoJSON, GPX or KML into map marks."""
    if len(content.encode("utf-8")) > MAX_VECTOR_BYTES:
        raise ValueError("Vector import is limited to 64 MB.")
    trimmed = content.lstrip()
    if trimmed.startswith("{") or trimmed.startswith("["):
        return {"format": "geojson", "marks": _marks_from_geojson(json.loads(trimmed))}
    if "<gpx" in trimmed.lower():
        from .field_tracks import parse_gpx
        return parse_gpx(content)
    if "<kml" in trimmed.lower():
        return {"format": "kml", "marks": _parse_kml(content)}
    raise ValueError("Select a KML, GPX or GeoJSON file.")


def parse_vector_file(path: str | Path) -> Dict[str, Any]:
    """Open KML/KMZ/GPX/GeoJSON or a ZIP Shapefile without extracting to disk."""
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if not file_path.is_file() or file_path.stat().st_size > MAX_VECTOR_BYTES:
        raise ValueError("Vector file not found or exceeds 64 MB.")
    if suffix == ".kmz":
        with zipfile.ZipFile(file_path) as archive:
            candidates = [info for info in archive.infolist() if info.filename.lower().endswith(".kml") and not info.is_dir()]
            if not candidates:
                raise ValueError("KMZ has no KML document.")
            info = min(candidates, key=lambda item: item.filename.lower() != "doc.kml")
            if info.file_size > MAX_VECTOR_BYTES:
                raise ValueError("KML inside KMZ exceeds 64 MB.")
            return {"format": "kmz", "marks": _parse_kml(_decode_text(archive.read(info)))}
    if suffix == ".zip":
        return {"format": "shapefile", "marks": _parse_shapefile_zip(file_path)}
    if suffix == ".sml":
        return {"format": "sml", "marks": _parse_sml(file_path.read_bytes())}
    if suffix == ".db3":
        return {"format": "db3", "marks": _parse_db3(file_path)}
    if suffix in (".kml", ".gpx", ".geojson", ".json"):
        return parse_vector_data(_decode_text(file_path.read_bytes()))
    raise ValueError("Supported vector files: KML, KMZ, GPX, GeoJSON, ZIP Shapefile, SAS.Planet .sml and .db3.")


def export_vector_data(marks: List[Dict[str, Any]], format_type: str = "geojson") -> str:
    """Export simple application marks to GeoJSON, GPX or KML."""
    fmt = format_type.lower()
    if fmt == "geojson":
        features = []
        for mark in marks:
            kind = mark.get("type", "point").lower()
            coords = mark.get("coords", [])
            geometry_type = "Point" if kind == "point" else ("LineString" if kind in ("line", "linestring") else "Polygon")
            coordinates = [coords] if geometry_type == "Polygon" and coords and not isinstance(coords[0][0], list) else coords
            features.append({"type": "Feature", "properties": {"id": mark.get("id"), "name": mark.get("name"), "description": mark.get("description", ""), "color": mark.get("color", "#3b82f6")}, "geometry": {"type": geometry_type, "coordinates": coordinates}})
        return json.dumps({"type": "FeatureCollection", "features": features}, indent=2, ensure_ascii=False)
    if fmt == "gpx":
        from .field_tracks import export_gpx
        return export_gpx(marks)
    if fmt == "kml":
        lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<kml xmlns="http://www.opengis.net/kml/2.2">', '  <Document>']
        for mark in marks:
            name, kind, coords = mark.get("name", "Mark"), mark.get("type", "point").lower(), mark.get("coords", [])
            lines += ["    <Placemark>", f"      <name>{name}</name>"]
            if kind == "point": lines += ["      <Point>", f"        <coordinates>{coords[0]},{coords[1]},0</coordinates>", "      </Point>"]
            elif kind in ("line", "linestring"):
                lines += ["      <LineString>", "        <coordinates>" + " ".join(f"{p[0]},{p[1]},0" for p in coords) + "</coordinates>", "      </LineString>"]
            elif kind == "polygon":
                ring = list(coords); ring += [ring[0]] if ring and ring[0] != ring[-1] else []
                lines += ["      <Polygon><outerBoundaryIs><LinearRing>", "        <coordinates>" + " ".join(f"{p[0]},{p[1]},0" for p in ring) + "</coordinates>", "      </LinearRing></outerBoundaryIs></Polygon>"]
            lines += ["    </Placemark>"]
        return "\n".join(lines + ["  </Document>", "</kml>"])
    if fmt in ("dxf", "dxf_ns"):
        return _export_dxf(marks, project_nord_sahara=(fmt == "dxf_ns"))
    raise ValueError("Supported export formats: GeoJSON, GPX, KML, DXF, DXF (Nord Sahara UTM).")


def _dxf_layer(name: str) -> str:
    """A DXF layer name: letters, digits, _ and - only (CAD-safe)."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", str(name or "MARKS")).strip("_")
    return (cleaned or "MARKS")[:31].upper()


def _export_dxf(marks: List[Dict[str, Any]], project_nord_sahara: bool = False) -> str:
    """Export marks as an AutoCAD DXF (R12 ASCII: POINT, TEXT and POLYLINE).

    Coordinates are WGS84 lon/lat, or projected to Nord Sahara 1959 UTM
    (metres, auto zone) when ``project_nord_sahara`` is set — the form Algerian
    survey offices load into AutoCAD/Covadis.
    """
    project = None
    if project_nord_sahara:
        from .nord_sahara import wgs84_to_utm_nord_sahara, PARAMETERS
        west, south, east, north = PARAMETERS["bbox"]
        zone_hint = []

        def project(lon: float, lat: float):
            if not (west <= lon < east and south <= lat <= north):
                raise ValueError("DXF (Nord Sahara) needs coordinates inside Algeria; use plain DXF for other areas.")
            forced = zone_hint[0] if zone_hint else 0
            result = wgs84_to_utm_nord_sahara(lat, lon, forced)
            if not zone_hint:
                zone_hint.append(result["zone"])  # keep every vertex in one UTM zone
            return result["easting"], result["northing"]

    def point(value) -> tuple:
        lon, lat = float(value[0]), float(value[1])
        return project(lon, lat) if project else (lon, lat)

    body: List[str] = []

    def emit(code: int, value) -> None:
        body.append(str(code)); body.append(str(value))

    for mark in marks:
        kind = str(mark.get("type", "point")).lower()
        coords = mark.get("coords", [])
        layer = _dxf_layer(mark.get("category") or mark.get("type") or "MARKS")
        if not coords:
            continue
        if kind == "point":
            x, y = point(coords)
            emit(0, "POINT"); emit(8, layer); emit(10, x); emit(20, y); emit(30, 0.0)
            label = str(mark.get("name") or "").strip()
            if label:
                emit(0, "TEXT"); emit(8, layer); emit(10, x); emit(20, y); emit(30, 0.0)
                emit(40, 2.0); emit(1, label.replace("\n", " "))
        elif kind in ("line", "linestring", "polygon"):
            ring = [point(p) for p in coords]
            if len(ring) < 2:
                continue
            closed = 1 if kind == "polygon" else 0
            emit(0, "POLYLINE"); emit(8, layer); emit(66, 1); emit(70, closed)
            for x, y in ring:
                emit(0, "VERTEX"); emit(8, layer); emit(10, x); emit(20, y); emit(30, 0.0)
            emit(0, "SEQEND")
    return "\n".join(["0", "SECTION", "2", "ENTITIES", *body, "0", "ENDSEC", "0", "EOF", ""])
