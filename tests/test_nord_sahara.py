import json
import unittest
from pathlib import Path
from sas_planet_py.nord_sahara import wgs84_to_utm_nord_sahara,utm_nord_sahara_to_wgs84,nord_sahara_to_utm

POINTS=json.loads((Path(__file__).parent/'fixtures/nord_sahara_reference.json').read_text())['points']

class NordSahara(unittest.TestCase):
    def test_forward_matches_independent_proj_reference_in_four_zones(self):
        for point in POINTS:
            with self.subTest(point=point['name']):
                value=wgs84_to_utm_nord_sahara(point['lat'],point['lon'])
                self.assertEqual(value['zone'],point['zone']);self.assertEqual(value['epsg'],30700+point['zone'])
                self.assertAlmostEqual(value['easting'],point['easting'],delta=.02)
                self.assertAlmostEqual(value['northing'],point['northing'],delta=.02)
                self.assertEqual(value['transformation_epsg'],1253)

    def test_inverse_returns_original_wgs_coordinates(self):
        for point in POINTS:
            with self.subTest(point=point['name']):
                value=utm_nord_sahara_to_wgs84(point['easting'],point['northing'],point['zone'])
                self.assertAlmostEqual(value['wgs84_lat'],point['lat'],delta=.000002)
                self.assertAlmostEqual(value['wgs84_lon'],point['lon'],delta=.000002)

    def test_central_meridians_and_crs_codes(self):
        for zone in (29,30,31,32):
            value=nord_sahara_to_utm(30,(zone-1)*6-177,zone)
            self.assertEqual(value['easting'],500000);self.assertEqual(value['epsg'],30700+zone)

    def test_rejects_wrong_zones_and_outside_nord_sahara_area(self):
        for args in [(30,31,0),(36,3,28),(float('nan'),3,31),(36,3,True)]:
            with self.subTest(args=args),self.assertRaises(ValueError):wgs84_to_utm_nord_sahara(*args)
        with self.assertRaises(ValueError):utm_nord_sahara_to_wgs84(500000,4000000,33)


if __name__=='__main__':unittest.main()
