import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ros.bridge import MappingSource, project_scan, depth_marker_pairs


class LiveBridgeTests(unittest.TestCase):
    def test_relative_marker_observations_require_same_fresh_depth_frame(self):
        frame={'state':'Scanning','dictionary':'DICT_4X4_50','observed_at':100.,'detections':[
            {'id':34,'registered':True,'camera_position_m':[0.,0.,1.], 'depth_samples':20},
            {'id':35,'registered':True,'camera_position_m':[.2,0.,1.], 'depth_samples':18},
            {'id':36,'registered':True,'camera_position_m':[.3,0.,1.]}]}
        packet=depth_marker_pairs(frame,100.1)
        self.assertEqual([v['id'] for v in packet['detections']],[34,35])
        self.assertIsNone(depth_marker_pairs(frame,101.))
        with patch('ros.bridge.time.monotonic',return_value=10.) as clock:
            source=MappingSource();source.update_markers(packet,age=.1)
            self.assertEqual(source.snapshot()['marker_observations']['age_s'],.1)
            clock.return_value=12.
            self.assertIsNone(source.snapshot()['marker_observations'])

    def test_pose_and_scan_without_map_do_not_fabricate_an_occupancy_grid(self):
        source=MappingSource()
        source.update_pose([1,2,.3],frame='odom',source='Wheel odometry only')
        source.update_scan({'frame':None,'points':[],'base_points':[[1,0]],'origin':None})
        packet=source.snapshot()
        self.assertEqual(packet['type'],'telemetry')
        self.assertIsNone(packet['grid'])
        self.assertEqual(packet['pose_frame'],'odom')
        self.assertIsNone(packet['scan']['frame'])

    def test_map_pose_and_scan_freshness_are_independent(self):
        with patch('ros.bridge.time.monotonic',return_value=10.) as clock:
            source=MappingSource()
            source.update_map({'width':1,'height':1,'data':[0]},'slam_map')
            source.update_pose([0,0,0],frame='slam_map',age=.1)
            source.update_scan({'frame':'slam_map','points':[[1,0]],'base_points':[[1,0]]},age=.1)
            self.assertTrue(source.snapshot()['pose_live'])
            clock.return_value=11.
            packet=source.snapshot()
            self.assertFalse(packet['pose_live'])
            self.assertGreater(packet['scan']['age_s'],.5)
            source.update_pose(None,error='TF unavailable')
            self.assertFalse(source.snapshot()['pose_live'])
            self.assertEqual(source.snapshot()['pose'],[0,0,0])

    def test_scan_projection_uses_mount_rotation_and_filters_invalid_returns(self):
        scan=SimpleNamespace(ranges=[1,0,float('nan'),float('inf'),20],angle_min=0.,
            angle_increment=math.pi/2,range_min=.1,range_max=8.)
        points=project_scan(scan,[2,3,.38],[0,0,1,0])
        self.assertEqual(points,[[1.,3.]])
        points=project_scan(scan,[2,3,.38],[0,0,math.sin(math.pi/4),math.cos(math.pi/4)])
        self.assertEqual(points,[[2.,4.]])
