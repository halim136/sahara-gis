"""
Tile Downloader Engine
Based on SAS.Planet's RegionProcess/Download:
- u_ThreadDownloadTiles.pas
- u_TileDownloaderSimple.pas
- u_DownloadSession.pas
"""

import time
import urllib.request
import urllib.error
import random
from typing import List, Tuple, Dict, Any, Callable, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from .projections import lon_lat_to_tile
from .map_sources import get_source
from .tile_storage import FileSystemStorage, MBTilesStorage, DEFAULT_CACHE_DIR

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 SAS.Planet/26.08.08"
)


class DownloadJob:
    """Represents a batch tile download job with progress tracking."""
    def __init__(
        self,
        job_id: str,
        source_id: str,
        bbox: Tuple[float, float, float, float], # min_lon, min_lat, max_lon, max_lat
        zooms: List[int],
        storage_type: str = "gm1",
        storage_path: Optional[str] = None,
        concurrency: int = 4
    ):
        self.job_id = job_id
        self.source_id = source_id
        self.bbox = bbox
        self.zooms = sorted(zooms)
        self.storage_type = storage_type
        self.storage_path = storage_path
        self.concurrency = concurrency

        self.total_tiles = 0
        self.downloaded_tiles = 0
        self.cached_tiles = 0
        self.failed_tiles = 0
        self.bytes_downloaded = 0
        self.status = "idle" # idle, running, paused, completed, cancelled, error
        self.error_message = ""
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.tile_queue: List[Tuple[int, int, int]] = [] # (zoom, x, y)
        self._calculate_queue()

    def _calculate_queue(self):
        min_lon, min_lat, max_lon, max_lat = self.bbox
        queue = []
        for z in self.zooms:
            x_min, y_max = lon_lat_to_tile(min_lon, min_lat, z)
            x_max, y_min = lon_lat_to_tile(max_lon, max_lat, z)
            # Ensure correct coordinate order
            x_start, x_end = min(x_min, x_max), max(x_min, x_max)
            y_start, y_end = min(y_min, y_max), max(y_min, y_max)
            for x in range(x_start, x_end + 1):
                for y in range(y_start, y_end + 1):
                    queue.append((z, x, y))
        self.tile_queue = queue
        self.total_tiles = len(queue)

    def to_dict(self) -> Dict[str, Any]:
        elapsed = (time.time() - self.start_time) if self.start_time and not self.end_time else (
            (self.end_time - self.start_time) if self.start_time and self.end_time else 0.0
        )
        speed_kb = round((self.bytes_downloaded / 1024.0) / elapsed, 1) if elapsed > 0 else 0.0
        progress_pct = round((self.downloaded_tiles + self.cached_tiles) / max(1, self.total_tiles) * 100, 1)

        return {
            "job_id": self.job_id,
            "source_id": self.source_id,
            "bbox": self.bbox,
            "zooms": self.zooms,
            "storage_type": self.storage_type,
            "total_tiles": self.total_tiles,
            "downloaded": self.downloaded_tiles,
            "cached": self.cached_tiles,
            "failed": self.failed_tiles,
            "bytes_downloaded": self.bytes_downloaded,
            "progress_percent": progress_pct,
            "speed_kb_s": speed_kb,
            "elapsed_s": round(elapsed, 1),
            "status": self.status,
            "error": self.error_message
        }


class TileDownloader:
    """Multi-source, multi-threaded batch tile downloader."""

    def __init__(self):
        self.jobs: Dict[str, DownloadJob] = {}

    def create_job(
        self,
        job_id: str,
        source_id: str,
        bbox: Tuple[float, float, float, float],
        zooms: List[int],
        storage_type: str = "gm1",
        storage_path: Optional[str] = None,
        concurrency: int = 4
    ) -> DownloadJob:
        job = DownloadJob(job_id, source_id, bbox, zooms, storage_type, storage_path, concurrency)
        self.jobs[job_id] = job
        return job

    def run_job(self, job: DownloadJob, progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        job.status = "running"
        job.start_time = time.time()

        source = get_source(job.source_id)
        url_template = source.get("url_template", "")
        subdomains = source.get("subdomains", [])
        ext = source.get("format", "jpg")

        # Initialize storage
        if job.storage_type == "mbtiles":
            storage = MBTilesStorage(job.storage_path or str(DEFAULT_CACHE_DIR / (job.job_id + '.mbtiles')))
            min_lon, min_lat, max_lon, max_lat = job.bbox
            storage.set_metadata("name", f"SAS.Planet - {source.get('name', 'Map')}")
            storage.set_metadata("type", "baselayer")
            storage.set_metadata("version", "1.0")
            storage.set_metadata("description", "Exported from SAS.Planet Python Studio")
            storage.set_metadata("format", ext)
            storage.set_metadata("bounds", f"{min_lon},{min_lat},{max_lon},{max_lat}")
            storage.set_metadata("minzoom", str(min(job.zooms)))
            storage.set_metadata("maxzoom", str(max(job.zooms)))
        else:
            storage = FileSystemStorage(base_dir=job.storage_path, format_type=job.storage_type)

        def fetch_single(item: Tuple[int, int, int]) -> Tuple[int, int, int, bool, int, str]:
            z, x, y = item
            # Check if tile already cached
            existing = None
            if job.storage_type != 'mbtiles':
                for candidate in dict.fromkeys((ext,'jpg','png','jpeg','webp','gif')):
                    existing = storage.load_tile(job.source_id,z,x,y,candidate)
                    if existing:break
            if existing:
                return z, x, y, True, len(existing), "cached"

            # Form URL
            sub = random.choice(subdomains) if subdomains else ""
            url = url_template.format(z=z, x=x, y=y, s=sub)

            headers = {
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "*/*",
                "Referer": "https://www.google.com/"
            }

            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = resp.read()
                    if job.storage_type == "mbtiles":
                        storage.save_tile(z, x, y, data)
                    else:
                        storage.save_tile(job.source_id, z, x, y, data, ext)
                    return z, x, y, True, len(data), "downloaded"
            except Exception as e:
                return z, x, y, False, 0, str(e)

        try:
            with ThreadPoolExecutor(max_workers=job.concurrency) as executor:
                futures = {executor.submit(fetch_single, tile): tile for tile in job.tile_queue}
                last_notify = time.time()
                for future in as_completed(futures):
                    if job.status in ("cancelled", "paused"):
                        break
                    z, x, y, success, size, reason = future.result()
                    if success:
                        if reason == "cached":
                            job.cached_tiles += 1
                        else:
                            job.downloaded_tiles += 1
                            job.bytes_downloaded += size
                    else:
                        job.failed_tiles += 1

                    now = time.time()
                    if progress_callback and (now - last_notify >= 0.5 or (job.downloaded_tiles + job.cached_tiles + job.failed_tiles) == job.total_tiles):
                        last_notify = now
                        progress_callback(job.to_dict())

            job.end_time = time.time()
            if job.status == "running":
                job.status = "completed"
        except Exception as ex:
            job.status = "error"
            job.error_message = str(ex)
            job.end_time = time.time()
        finally:
            if job.storage_type == "mbtiles" and hasattr(storage, "close"):
                storage.close()

        if progress_callback:
            progress_callback(job.to_dict())
        return job
