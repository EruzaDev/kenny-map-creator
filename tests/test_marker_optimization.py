import copy
import math
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / 'Kenny---Automotive-self-driving-trash-can'))
from backend.marker_optimization import optimize, Placement


def room():
    return {'version': 1, 'frame_id': 'map', 'units': 'meters', 'name': 'Placement test', 'dictionary': 'DICT_4X4_50',
        'grid': {'width': 60, 'height': 40, 'resolution': .1, 'origin': [0., 0., 0.], 'data': [0] * 2400},
        'start': [1., 1.], 'goal': [.5, .5], 'destination_marker_id': 7, 'obstacles': [],
        'markers': [{'uid': 'marker-7', 'id': 7, 'x': .5, 'y': .5, 'z': 0., 'yaw': 0., 'size': .2, 'mount': 'floor'}]}


class MarkerOptimizationTests(unittest.TestCase):
    def test_improves_coverage_preserves_identity_and_is_deterministic(self):
        environment = room()
        original = copy.deepcopy(environment)
        result = optimize({'environment': environment})
        self.assertGreater(result['coverage_after_percent'], result['coverage_before_percent'])
        self.assertTrue(result['changes'])
        marker = result['markers'][0]
        for key in ('id', 'uid', 'size', 'mount'):
            self.assertEqual(marker[key], original['markers'][0][key])
        self.assertLessEqual(math.dist([marker['x'], marker['y']], [.5, .5]), 1.5)
        self.assertEqual(result['goal'], [marker['x'], marker['y']])
        self.assertEqual(environment, original)
        self.assertEqual(optimize({'environment': environment}), result)

    def test_selected_scope_preserves_other_marker_positions(self):
        environment = room()
        environment['markers'].append({**environment['markers'][0], 'uid': 'marker-8', 'id': 8, 'x': 5., 'y': 3.})
        result = optimize({'environment': environment, 'marker_ids': [7]})
        self.assertEqual(result['markers'][1], environment['markers'][1])
        self.assertTrue(all(change['id'] == 7 for change in result['changes']))

    def test_unknown_and_occupied_space_occlude_visibility(self):
        environment = room()
        for y in range(40):
            environment['grid']['data'][y * 60 + 20] = -1
        placement = Placement(environment, .4, 2.5)
        marker = {**environment['markers'][0], 'x': 2.5, 'y': 1.}
        self.assertFalse(placement.valid(marker))
        self.assertFalse(placement.visibility(marker).any())

    def test_wall_height_adjustment_is_explicit_and_arrival_stays_reachable(self):
        environment = room()
        marker = environment['markers'][0]
        marker.update(x=.1, y=2., z=1., mount='wall', yaw=0.)
        unchanged_height = optimize({'environment': environment})
        self.assertEqual(unchanged_height['markers'][0]['z'], 1.)
        adjusted = optimize({'environment': environment, 'adjust_wall_height': True})
        self.assertGreater(adjusted['coverage_after_percent'], adjusted['coverage_before_percent'])
        self.assertEqual(adjusted['markers'][0]['z'], .4)
        self.assertTrue(Placement(environment, .4, 2.5).valid(adjusted['markers'][0]))

    def test_rotated_map_uses_world_coordinates_and_rejects_invalid_options(self):
        environment = room()
        environment['grid']['origin'] = [10., 20., math.pi/2]
        environment['start'], environment['goal'] = [9., 21.], [9.5, 20.5]
        environment['markers'][0].update(x=9.5, y=20.5)
        result = optimize({'environment': environment})
        self.assertTrue(Placement(environment, .4, 2.5).valid(result['markers'][0]))
        self.assertGreaterEqual(result['coverage_after_percent'], result['coverage_before_percent'])
        for change in ({'max_shift_m': float('nan')}, {'marker_ids': [999]}, {'min_spacing_m': -1}):
            with self.assertRaises(ValueError):
                optimize({'environment': environment, **change})


if __name__ == '__main__':
    unittest.main()
