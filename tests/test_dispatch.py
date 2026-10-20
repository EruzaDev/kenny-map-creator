import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / 'Kenny---Automotive-self-driving-trash-can'))
from backend import dispatch


class DispatchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.state = Path(temp.name) / 'receiver.json'
        self.patch('STATE', self.state)
        self.deployment = Path(temp.name) / 'deployment.json'
        self.patch('DEPLOYMENT', self.deployment)
        self.patch('models', return_value=[{'id': 'test/best.zip'}])
        self.environment = json.loads((ROOT / 'fixtures/marker-destination-room.json').read_text())
        marker = next(m for m in self.environment['markers'] if m['id'] == 12)
        import math
        self.goal = [marker['x'] + math.cos(marker['yaw']) * .5,
                     marker['y'] + math.sin(marker['yaw']) * .5]
        self.job = {'id': 'cloud-job', 'marker_id': 12, 'dictionary': self.environment['dictionary'],
                    'destination': {'frame_id': 'map', 'x': self.goal[0], 'y': self.goal[1]}}
        self.payload = {'environment': self.environment, 'model': 'test/best.zip'}
        self.replay = {'info': {'event': 'success'}, 'frames': [{'pose': self.goal + [0]}]}

    def patch(self, name, *args, **kwargs):
        patcher = patch.object(dispatch, name, *args, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_claim_resolves_marker_and_next_trip_uses_last_pose(self):
        post = self.patch('post', side_effect=[{'job': self.job}, {}, {'job': self.job}, {}])
        simulate = self.patch('simulate', return_value=self.replay)
        result = dispatch.tick(self.payload)
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(simulate.call_args.args[0]['environment']['goal'], self.goal)
        self.assertEqual(post.call_args.args[1]['worker'], 'kenny-simulation')
        dispatch.tick(self.payload)
        self.assertEqual(simulate.call_args.args[0]['environment']['start'], self.goal)

    def test_result_failure_retries_without_repeating_navigation(self):
        post = self.patch('post', side_effect=[{'job': self.job}, dispatch.DispatchUnavailable('offline'), {}])
        simulate = self.patch('simulate', return_value=self.replay)
        with self.assertRaises(dispatch.DispatchUnavailable):
            dispatch.tick(self.payload)
        self.assertEqual(json.loads(self.state.read_text())['phase'], 'finished')
        result = dispatch.tick(self.payload)
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(simulate.call_count, 1)
        self.assertEqual(post.call_args.args[0], '/api/calls/cloud-job/result')

    def test_missing_marker_fails_without_simulating(self):
        job = copy.deepcopy(self.job)
        job['marker_id'] = 999
        self.patch('post', side_effect=[{'job': job}, {}])
        simulate = self.patch('simulate')
        result = dispatch.tick(self.payload)
        self.assertEqual(result['status'], 'failed')
        self.assertIn('missing', result['detail'])
        simulate.assert_not_called()

    def test_simulation_uses_local_id_location_instead_of_cloud_coordinates(self):
        job = copy.deepcopy(self.job)
        job['destination']['x'] += 10
        self.patch('post', side_effect=[{'job': job}, {}])
        simulate = self.patch('simulate', return_value=self.replay)
        self.assertEqual(dispatch.tick(self.payload)['status'], 'succeeded')
        self.assertEqual(simulate.call_args.args[0]['environment']['goal'], self.goal)

    def test_restart_reports_interrupted_simulation_failed(self):
        self.state.write_text(json.dumps({'phase': 'running', 'job': self.job,
                                         'worker': 'kenny-simulation', 'map': 'signature'}))
        post = self.patch('post', return_value={})
        simulate = self.patch('simulate')
        result = dispatch.tick(self.payload)
        self.assertEqual(result['status'], 'failed')
        self.assertIn('interrupted', result['detail'])
        self.assertEqual(post.call_count, 1)
        simulate.assert_not_called()

    def test_timeout_is_not_success_and_empty_queue_does_not_simulate(self):
        self.patch('post', side_effect=[{'job': self.job}, {}, {'job': None}])
        simulate = self.patch('simulate', return_value={**self.replay, 'info': {'event': 'timeout'}})
        self.assertEqual(dispatch.tick(self.payload)['status'], 'failed')
        self.assertIsNone(dispatch.tick(self.payload)['job'])
        self.assertEqual(simulate.call_count, 1)

    def test_robot_mode_blocks_simulation_claims_and_pose_uploads(self):
        self.deployment.write_text(json.dumps({'mode': 'robot'}))
        post = self.patch('post')
        simulate = self.patch('simulate')
        with self.assertRaisesRegex(ValueError, 'Robot mode is active'):
            dispatch.tick(self.payload)
        with self.assertRaisesRegex(ValueError, 'Robot mode is active'):
            dispatch.publish_simulation_pose({'pose': [1, 2, 0]})
        post.assert_not_called()
        simulate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
