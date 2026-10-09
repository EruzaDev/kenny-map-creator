import io
import json
from pathlib import Path
import sys
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT.parent/'Kenny---Automotive-self-driving-trash-can'))
import cv2
import numpy as np
from backend.services import marker_image,marker_pdf,export_bundle

class DictionaryTests(unittest.TestCase):
    def test_high_ids_detect_and_legacy_patterns_match(self):
        detector=cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_1000))
        for mid in (50,250,999):
            _,ids,_=detector.detectMarkers(np.asarray(marker_image(mid,'DICT_4X4_1000')))
            self.assertEqual(ids.ravel().tolist(),[mid])
        for mid in (0,7,49):
            self.assertTrue(np.array_equal(np.asarray(marker_image(mid)),np.asarray(marker_image(mid,'DICT_4X4_1000'))))
        for mid in (-1,1000):
            with self.assertRaises(ValueError):marker_image(mid,'DICT_4X4_1000')
    def test_export_preserves_dictionary_and_prints_high_id(self):
        env=json.loads((ROOT/'fixtures/marker-destination-room.json').read_text())
        env['dictionary']='DICT_4X4_1000'
        destination=next(m for m in env['markers'] if m['id']==env['destination_marker_id'])
        destination['id']=999
        env['destination_marker_id']=999
        with zipfile.ZipFile(io.BytesIO(export_bundle(env))) as archive:
            self.assertIn('markers/marker-999.png',archive.namelist())
            self.assertIn(b'DICT_4X4_1000',archive.read('markers.pdf'))
            self.assertEqual(json.loads(archive.read('environment.json'))['dictionary'],'DICT_4X4_1000')
