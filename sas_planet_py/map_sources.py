"""Map definitions shared by the local tile server and Python tools.
Cache names follow SAS.Planet ZMP NameInCache (Google labels = Both).
"""
import json
from pathlib import Path
from typing import Dict, Any, List

_DEFINITIONS=json.loads(Path(__file__).with_suffix('.json').read_text(encoding='utf-8'))
MAP_SOURCES: Dict[str, Dict[str, Any]]=_DEFINITIONS['MAP_SOURCES']
OVERLAYS: Dict[str, Dict[str, Any]]=_DEFINITIONS['OVERLAYS']


def get_source(source_id: str) -> Dict[str, Any]:
    if source_id in MAP_SOURCES:
        return MAP_SOURCES[source_id]
    if source_id in OVERLAYS:
        return OVERLAYS[source_id]
    return MAP_SOURCES["google_sat"]


def list_sources() -> List[Dict[str, Any]]:
    return list(MAP_SOURCES.values())


def list_overlays() -> List[Dict[str, Any]]:
    return list(OVERLAYS.values())
