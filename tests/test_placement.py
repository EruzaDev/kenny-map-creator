import copy
import io
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.placement import apply_placement
from ros.bridge import placement_transform, aligned_grid


class PlacementTests(unittest.TestCase):
    def setUp(self):
        self.map={'grid':{'width':1,'height':1,'data':[0]},'markers':[],'obstacles':[],
                  'frame_id':'map','dictionary':'DICT_4X4_50'}
        self.payload={'pose':[3.,4.,.5],'source_pose':[0.,0.,0.],'source_frame':'slam_map',
                      'session_id':'session','environment':self.map,'map_sha256':'hash'}
        self.source=Mock()
        self.source.apply_lock=threading.Lock()
        self.source.snapshot.return_value={'pose':[0.,0.,0.],'pose_frame':'slam_map','pose_live':True,'session_id':'session'}
        self.source.apply_callback.return_value={'pose':[3.,4.,.5],'frame':'map'}

    def apply(self,payload=None,stopped=True):
        with patch('backend.placement.remote_map',return_value={'environment':self.map,'sha256':'hash'}),patch('backend.placement.urlopen')as open_url:
            open_url.return_value.__enter__.return_value=io.BytesIO(json.dumps({'emergency_stop':stopped,'physical_stop_confirmed':stopped}).encode())
            return apply_placement(payload or self.payload,self.source)

    def test_explicit_stationary_placement_applies_map_pose_without_map_upload(self):
        result=self.apply()
        self.assertEqual(result['frame'],'map')
        self.source.apply_callback.assert_called_once_with([3.,4.,.5],'hash')
        self.assertIn('No motor command',result['detail'])

    def test_moving_robot_changed_map_or_session_cannot_apply(self):
        with self.assertRaisesRegex(ValueError,'stationary'):
            self.apply(stopped=False)
        with self.assertRaisesRegex(ValueError,'session changed'):
            self.apply({**self.payload,'session_id':'other'})
        with self.assertRaisesRegex(ValueError,'Render map changed'):
            self.apply({**self.payload,'map_sha256':'other'})
        different=copy.deepcopy(self.map);different['markers']=[{'id':5}]
        with self.assertRaisesRegex(ValueError,'upload this map first'):
            self.apply({**self.payload,'environment':different})
        self.source.apply_callback.assert_not_called()

    def test_invalid_or_changed_source_pose_is_refused(self):
        with self.assertRaisesRegex(ValueError,'finite'):
            self.apply({**self.payload,'pose':[float('nan'),1,0]})
        with self.assertRaisesRegex(ValueError,'Source pose changed'):
            self.apply({**self.payload,'source_pose':[1,0,0]})
        self.source.apply_callback.assert_not_called()

    def test_pose_and_occupancy_origin_transform_consistently_without_mutating_grid(self):
        import math
        transform=placement_transform([3,4,math.pi/2],[1,2,0])
        grid={'origin':[1,2,0],'width':2,'height':2,'data':[0,0,100,0]}
        result=aligned_grid(grid,transform)
        self.assertAlmostEqual(result['origin'][0],3)
        self.assertAlmostEqual(result['origin'][1],4)
        self.assertAlmostEqual(result['origin'][2],math.pi/2)
        self.assertEqual(grid['origin'],[1,2,0])
        self.assertEqual(result['data'],grid['data'])
