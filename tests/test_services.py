import base64
import copy
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT.parent/'Kenny---Automotive-self-driving-trash-can'))
import cv2
import numpy as np
import yaml
from PIL import Image
from backend.services import export_bundle, import_grid, marker_pdf, marker_image, marker_pose
from kenny_rl.environment import load_environment, validate_environment, merged_rectangles
from kenny_rl.config import RobotConfig


class ExportTests(unittest.TestCase):
    def setUp(self):self.env=json.loads((ROOT/'fixtures/sample-room.json').read_text())
    def test_marker_detection(self):
        detector=cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50))
        for mid in [0,7,49]:
            _,ids,_=detector.detectMarkers(np.asarray(marker_image(mid)))
            self.assertEqual(ids.ravel().tolist(),[mid])
    def test_export_import_negative_origin(self):
        self.env['grid']['data'][6]=-1;self.env['grid']['data'][5]=100
        with zipfile.ZipFile(io.BytesIO(export_bundle(self.env))) as z:
            meta=z.read('map.yaml').decode();pgm=z.read('map.pgm')
            self.assertTrue(pgm.startswith(b'P5'))
            grid=import_grid({'yaml':meta,'image':base64.b64encode(pgm).decode()})
            self.assertEqual(grid['origin'],[-2,-1,0]);self.assertEqual(grid['data'][6],-1);self.assertEqual(grid['data'][5],100)
            # The hand-placed wall is rasterized into navigation occupancy.
            self.assertGreater(sum(v==100 for v in grid['data']),1)
            self.assertEqual(json.loads(z.read('environment.json')),self.env)
            self.assertTrue(z.read('markers.pdf').startswith(b'%PDF'))
            self.assertEqual(yaml.safe_load(z.read('markers.yaml'))['markers'][0]['id'],7)
    def test_world_transform_rectangular_unknown(self):
        self.env['grid']['data'][6]=-1
        world=load_environment(self.env,RobotConfig())
        np.testing.assert_allclose(world.start,[1,1]);np.testing.assert_allclose(world.goal,[5,3])
        self.assertEqual(world.size,6)
        self.assertEqual(world.width,6);self.assertEqual(world.height,4)
        self.assertFalse(any(b[1]==4 and b[4]==6 for b in world.boxes))
        self.assertTrue(any(np.isclose(b[0],.3) and np.isclose(b[3],.35) for b in world.boxes))
    def test_rotated_origin(self):
        self.env['grid']['origin']=[-2,-1,math.pi/2]
        self.env['obstacles']=[];self.env['markers']=[];self.env['start']=[-3,0];self.env['goal']=[-5,4]
        world=load_environment(self.env,RobotConfig());np.testing.assert_allclose(world.start,[1,1]);np.testing.assert_allclose(world.goal,[5,3])
    def test_duplicate_blocked_and_invalid(self):
        bad=copy.deepcopy(self.env);bad['markers'][1]['id']=7
        with self.assertRaises(ValueError):validate_environment(bad)
        bad=copy.deepcopy(self.env);bad['grid']['data'][20*120+20]=-1
        with self.assertRaisesRegex(ValueError,'start'):load_environment(bad,RobotConfig())
        bad=copy.deepcopy(self.env);bad['obstacles'][0]['width']=-1
        with self.assertRaises(ValueError):validate_environment(bad)
    def test_wall_orientation(self):
        m=self.env['markers'][1];m['yaw']=0;q=marker_pose(m)['orientation_xyzw'];x,y,z,w=q
        rot=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)], [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)], [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
        np.testing.assert_allclose(rot@[0,0,1],[1,0,0],atol=1e-12);np.testing.assert_allclose(rot@[0,1,0],[0,0,1],atol=1e-12)
    def test_vector_pdf_print_size_and_detection(self):
        m=copy.deepcopy(self.env['markers'][0]);m['size']=.1
        pdf=marker_pdf([m]);self.assertIn(b'/Count 1',pdf)
        markers=[m]*5
        self.assertIn(b'/Count 5',marker_pdf(markers,1))
        self.assertIn(b'/Count 3',marker_pdf(markers,2))
        self.assertIn(b'/Count 2',marker_pdf(markers,4))
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'marker.pdf';p.write_bytes(pdf)
            subprocess.run(['pdftoppm','-png','-r','150','-singlefile',str(p),str(Path(temp)/'print')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            image=cv2.imread(str(Path(temp)/'print.png'))
            _,ids,_=cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)).detectMarkers(image)
            self.assertEqual(ids.ravel().tolist(),[7])
            # Exact 100mm / six modules, in PDF points.
            self.assertIn(f'{100/25.4*72/6:.6f}'.encode(),pdf)
    def test_merge_coverage(self):
        rng=np.random.default_rng(3);mask=rng.random((11,13))>.6;rebuilt=np.zeros_like(mask)
        for x0,y0,x1,y1 in merged_rectangles(mask,1):rebuilt[int(y0):int(y1),int(x0):int(x1)]=True
        np.testing.assert_array_equal(mask,rebuilt)

if __name__=='__main__':unittest.main()

class DestinationExportTests(unittest.TestCase):
    def test_export_records_marker_goal_and_announcement(self):
        env=json.loads((ROOT/'fixtures/sample-room.json').read_text())
        env['destination_marker_id']=12;env['goal']=[99,99]
        with zipfile.ZipFile(io.BytesIO(export_bundle(env))) as z:
            saved=json.loads(z.read('environment.json'))
            np.testing.assert_allclose(saved['goal'],[2,2])
            self.assertEqual(saved['destination_marker_id'],12)
            navigation=yaml.safe_load(z.read('navigation.yaml'))
            self.assertEqual(navigation['near_goal_distance_m'],5)
            self.assertEqual(navigation['near_goal_reference'],'destination_marker')
            self.assertEqual(navigation['destination_position_m'],[2,2.5])
            self.assertEqual(z.read(navigation['near_goal_audio']),(ROOT/'res/im near.mp3').read_bytes())
