import io
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from sas_planet_py.tile_storage import FileSystemStorage, cache_layer
from sas_planet_py.tile_downloader import TileDownloader
from sas_planet_py.tile_stitcher import TileStitcher
from sas_planet_py.projections import tile_bounds


def png():
    stream=io.BytesIO();Image.new('RGB',(256,256),(20,90,150)).save(stream,'PNG');return stream.getvalue()


class GM1Cache(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.storage=FileSystemStorage(self.root)
        self.image=png()

    def test_native_gm1_uses_xyz_zoom_y_directory_and_x_filename(self):
        self.assertEqual(Path(self.storage.get_tile_path('google_sat',15,16994,12821)),self.root/'sat/z15/12821/16994.jpg')
        self.assertEqual(Path(self.storage.get_tile_path('google_sat',0,0,0)),self.root/'sat/z0/0/0.jpg')

    def test_native_source_names_and_labels_are_separate(self):
        self.assertEqual(cache_layer('google_sat'),'sat')
        self.assertEqual(cache_layer('esri_satellite'),'ArcGIS.Imagery')
        self.assertEqual(cache_layer('google_terrain'),'land')
        self.assertEqual(cache_layer('google_hybrid_overlay'),'Both')
        self.assertNotEqual(cache_layer('google_hybrid'),cache_layer('google_hybrid_overlay'))

    def test_real_image_extension_overrides_declared_source_extension(self):
        result=self.storage.save_tile('google_sat',3,4,2,self.image,'jpg')
        self.assertEqual(Path(result),self.root/'sat/z3/2/4.png')
        self.assertEqual(self.storage.load_tile('google_sat',3,4,2,'png'),self.image)
        self.assertFalse((self.root/'sat/z3/2/4.jpg').exists())

    def test_imported_gm1_file_is_read_without_transposing_axes(self):
        file=self.root/'sat/z3/2/4.png';file.parent.mkdir(parents=True);file.write_bytes(self.image)
        self.assertEqual(self.storage.load_tile('google_sat',3,4,2,'png'),self.image)
        self.assertIsNone(self.storage.load_tile('google_sat',3,2,4,'png'))

    def test_sas_hierarchy_has_one_based_zoom(self):
        sas=FileSystemStorage(self.root,'sas')
        self.assertEqual(Path(sas.get_tile_path('google_sat',15,16994,12821)),self.root/'sat/z16/16/x16994/12/y12821.jpg')
        sas.save_tile('google_sat',3,4,2,self.image,'png')
        self.assertEqual(self.storage.load_tile('google_sat',3,4,2,'png'),self.image)
        self.assertTrue((self.root/'sat/z3/2/4.png').exists())

    def test_old_web_cache_is_recovered_without_deleting_original(self):
        legacy=self.root/'old';old=legacy/'google_sat/z3/0/x4/0/y2.png';old.parent.mkdir(parents=True);old.write_bytes(self.image)
        storage=FileSystemStorage(self.root/'new',legacy_dir=legacy)
        self.assertEqual(storage.load_tile('google_sat',3,4,2,'png'),self.image)
        self.assertTrue(old.exists());self.assertEqual((self.root/'new/sat/z3/2/4.png').read_bytes(),self.image)

    def test_default_path_can_be_portable_and_ignores_current_directory(self):
        with patch('sas_planet_py.tile_storage.DEFAULT_CACHE_DIR',self.root/'portable/cache_gmt'):
            storage=FileSystemStorage()
            self.assertEqual(Path(storage.base_dir),self.root/'portable/cache_gmt')

    def test_invalid_coordinates_extensions_and_paths_are_rejected(self):
        for values in [('google_sat',3,8,0,'jpg'),('google_sat',-1,0,0,'jpg'),('../sat',3,0,0,'jpg'),
                       ('sat/other',3,0,0,'jpg'),('google_sat',3,0,0,'../x'),('google_sat',True,0,0,'jpg')]:
            with self.subTest(values=values),self.assertRaises(ValueError):self.storage.get_tile_path(*values)

    def test_atomic_writes_leave_complete_image_and_no_temporary_files(self):
        with ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(lambda _:self.storage.save_tile('google_sat',3,4,2,self.image),range(12)))
        self.assertEqual((self.root/'sat/z3/2/4.png').read_bytes(),self.image)
        self.assertEqual(list(self.root.rglob('*.tmp')),[])

    def test_server_error_pages_are_not_saved_as_tiles(self):
        with self.assertRaises(ValueError):self.storage.save_tile('google_sat',3,4,2,b'<html>error</html>')
        self.assertEqual(self.storage.get_stats()['total_tiles'],0)

    def test_stats_count_images_and_exclude_metadata(self):
        self.storage.save_tile('google_sat',3,4,2,self.image)
        (self.root/'metadata.json').write_text('{}')
        result=self.storage.get_stats();self.assertEqual(result['total_tiles'],1)
        self.assertEqual(result['total_size_bytes'],len(self.image))

    def bbox(self):
        b=tile_bounds(4,2,3);dx=(b['max_lon']-b['min_lon'])/4;dy=(b['max_lat']-b['min_lat'])/4
        return (b['min_lon']+dx,b['min_lat']+dy,b['max_lon']-dx,b['max_lat']-dy)

    def test_batch_downloader_reuses_same_gm1_cache_even_with_png_in_jpg_source(self):
        self.storage.save_tile('google_sat',3,4,2,self.image)
        engine=TileDownloader();job=engine.create_job('fixture','google_sat',self.bbox(),[3],storage_path=str(self.root))
        with patch('urllib.request.urlopen',side_effect=AssertionError('Unexpected network')) as network:engine.run_job(job)
        network.assert_not_called();self.assertEqual(job.cached_tiles,1);self.assertEqual(job.downloaded_tiles,0)

    def test_stitcher_reuses_gm1_cache_without_network(self):
        self.storage.save_tile('google_sat',3,4,2,self.image)
        output=self.root/'output.png'
        with patch('urllib.request.urlopen',side_effect=AssertionError('Unexpected network')) as network:
            TileStitcher.stitch_bbox('google_sat',self.bbox(),3,str(output),cache_dir=str(self.root))
        network.assert_not_called()
        with Image.open(output) as image:self.assertEqual(image.getpixel((100,100)),(20,90,150))


if __name__=='__main__':unittest.main()
