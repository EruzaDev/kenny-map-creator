"""Deterministic marker-placement suggestions from estimated occupancy geometry."""
import copy
import math

import cv2
import numpy as np

from kenny_rl.config import RobotConfig
from kenny_rl.environment import validate_environment, rasterize, local_point, destination_goal


class Placement:
    def __init__(self, environment, camera_height, maximum_range):
        self.environment = environment
        self.grid = environment['grid']
        self.occupancy = rasterize(environment)
        self.resolution = self.grid['resolution']
        padded = np.pad((self.occupancy == 0).astype(np.uint8), 1)
        clearance = cv2.distanceTransform(padded, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)[1:-1, 1:-1] * self.resolution
        self.walkable = clearance >= RobotConfig().radius + .05
        _, labels = cv2.connectedComponents(self.walkable.astype(np.uint8), connectivity=4)
        start = self.cell(environment['start'])
        if not self.inside(start) or not self.walkable[start[1], start[0]]:
            raise ValueError('Place robot start in free space with robot clearance before optimizing markers')
        self.reachable = labels == labels[start[1], start[0]]
        cells = np.argwhere(self.reachable)
        self.camera_height, self.maximum_range = camera_height, maximum_range
        # Cover the connected navigable region at bounded deterministic samples.
        indices = np.unique(np.linspace(0, len(cells) - 1, min(256, len(cells))).astype(int))
        self.samples = self.world(cells[indices, ::-1] + .5)

    def world(self, cells):
        points = np.asarray(cells) * self.resolution
        x, y, yaw = self.grid['origin']
        c, s = math.cos(yaw), math.sin(yaw)
        return points @ np.array([[c, s], [-s, c]]) + [x, y]

    def cell(self, point):
        return tuple(np.floor(local_point(point, self.grid['origin']) / self.resolution).astype(int))

    def inside(self, cell):
        return 0 <= cell[0] < self.grid['width'] and 0 <= cell[1] < self.grid['height']

    def valid(self, marker):
        center = self.cell([marker['x'], marker['y']])
        if not self.inside(center):
            return False
        goal = [marker['x'], marker['y']]
        if marker['mount'] == 'wall':
            goal = [marker['x'] + .5 * math.cos(marker['yaw']), marker['y'] + .5 * math.sin(marker['yaw'])]
        arrival = self.cell(goal)
        return self.inside(arrival) and self.reachable[arrival[1], arrival[0]]

    def visibility(self, marker):
        visible = np.zeros(len(self.samples), dtype=bool)
        if not self.valid(marker):
            return visible
        delta = self.samples - [marker['x'], marker['y']]
        distance = np.linalg.norm(delta, axis=1)
        elevation = np.degrees(np.arctan2(marker['z'] - self.camera_height, distance))
        robot = RobotConfig()
        eligible = (distance >= .4) & (distance <= self.maximum_range) & (elevation >= robot.camera_pitch_deg - robot.camera_vfov_deg / 2) & (elevation <= robot.camera_pitch_deg + robot.camera_vfov_deg / 2)
        if marker['mount'] == 'wall':
            eligible &= delta @ [math.cos(marker['yaw']), math.sin(marker['yaw'])] > .05
        indices = np.flatnonzero(eligible)
        if not len(indices):
            return visible
        # Sample at half a cell: unknown space and occupied cells occlude rays.
        # Exclude only the mounting cell at the marker end of wall rays.
        steps = max(2, math.ceil(self.maximum_range / (self.resolution / 2)))
        fractions = np.linspace(0, 1, steps + 1)[:-1]
        points = self.samples[indices, None, :] + fractions[None, :, None] * ([marker['x'], marker['y']] - self.samples[indices, None, :])
        ox, oy, yaw = self.grid['origin']
        px, py = points[..., 0] - ox, points[..., 1] - oy
        col = np.floor((math.cos(yaw) * px + math.sin(yaw) * py) / self.resolution).astype(int)
        row = np.floor((-math.sin(yaw) * px + math.cos(yaw) * py) / self.resolution).astype(int)
        inside = (col >= 0) & (row >= 0) & (col < self.grid['width']) & (row < self.grid['height'])
        blocked = np.ones(col.shape, dtype=bool)
        blocked[inside] = self.occupancy[row[inside], col[inside]] != 0
        if marker['mount'] == 'wall':
            mounting = self.cell([marker['x'], marker['y']])
            blocked[(col == mounting[0]) & (row == mounting[1])] = False
        visible[indices] = ~blocked.any(axis=1)
        return visible

    def candidates(self, marker, maximum_shift, adjust_height, budget):
        candidates = [copy.deepcopy(marker)]
        if marker['mount'] == 'floor':
            step = max(self.resolution, maximum_shift / 3)
            for dx in np.arange(-maximum_shift, maximum_shift + step / 2, step):
                for dy in np.arange(-maximum_shift, maximum_shift + step / 2, step):
                    if math.hypot(dx, dy) > maximum_shift:
                        continue
                    candidates.append({**marker, 'x': marker['x'] + float(dx), 'y': marker['y'] + float(dy)})
        else:
            radius = math.ceil(maximum_shift / self.resolution) + 1
            cx, cy = self.cell([marker['x'], marker['y']])
            for y in range(max(0, cy - radius), min(self.grid['height'], cy + radius + 1)):
                for x in range(max(0, cx - radius), min(self.grid['width'], cx + radius + 1)):
                    if self.occupancy[y, x] != 100:
                        continue
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        neighbor = x + dx, y + dy
                        if not self.inside(neighbor) or self.occupancy[neighbor[1], neighbor[0]] != 0:
                            continue
                        # Free-side wall face, slightly outside the occupied cell.
                        center = self.world([x + .5 + dx * (.5 + .02 / self.resolution), y + .5 + dy * (.5 + .02 / self.resolution)])
                        candidate = {**marker, 'x': float(center[0]), 'y': float(center[1]),
                                     'yaw': math.atan2(dy, dx) + self.grid['origin'][2]}
                        candidates.append(candidate)
            # Map boundaries are candidate room faces, pointing into the room.
            for x, y, angle in ((0, cy + .5, 0), (self.grid['width'] - 1e-6, cy + .5, math.pi),
                                (cx + .5, 0, math.pi/2), (cx + .5, self.grid['height'] - 1e-6, -math.pi/2)):
                center = self.world([x, y])
                candidates.append({**marker, 'x': float(center[0]), 'y': float(center[1]), 'yaw': angle + self.grid['origin'][2]})
        if adjust_height and marker['mount'] == 'wall':
            candidates += [{**candidate, 'z': self.camera_height} for candidate in candidates]
        candidates = [candidate for candidate in candidates if math.dist([candidate['x'], candidate['y'], candidate['z']], [marker['x'], marker['y'], marker['z']]) <= maximum_shift + 1e-8 and self.valid(candidate)]
        if len(candidates) > budget:
            # Keep a spread of nearby positions instead of only one side of a wall.
            candidates.sort(key=lambda candidate: (candidate['x'], candidate['y'], candidate['z'], candidate['yaw']))
            indices = np.unique(np.linspace(0, len(candidates) - 1, budget - 1).astype(int))
            candidates = [copy.deepcopy(marker), *[candidates[i] for i in indices]]
        return candidates


def optimize(payload):
    environment = copy.deepcopy(validate_environment(payload['environment']))
    maximum_shift, spacing = payload.get('max_shift_m', 1.5), payload.get('min_spacing_m', .6)
    camera_height, maximum_range = payload.get('camera_height_m', .4), payload.get('view_range_m', 2.5)
    for value, lower, upper, label in ((maximum_shift, .1, 5., 'Maximum shift'), (spacing, .1, 3., 'Minimum spacing'),
                                      (camera_height, .05, 2., 'Camera height'), (maximum_range, .5, 8., 'View range')):
        if type(value) not in (int, float) or not math.isfinite(value) or not lower <= value <= upper:
            raise ValueError(f'{label} is outside supported bounds')
    markers = environment['markers']
    if not markers:
        raise ValueError('Place at least one ArUco marker first')
    selected = payload.get('marker_ids', [m['id'] for m in markers])
    if not isinstance(selected, list) or not selected or any(type(mid) is not int or mid not in {m['id'] for m in markers} for mid in selected):
        raise ValueError('Choose existing marker IDs to optimize')
    placement = Placement(environment, camera_height, maximum_range)
    masks = [placement.visibility(marker) for marker in markers]
    before = np.logical_or.reduce(masks)
    counts = np.sum(masks, axis=0).astype(int)
    changes = []
    budget = max(3, min(32, 2400 // len(selected)))
    for index, original in enumerate(list(markers)):
        if original['id'] not in selected:
            continue
        counts -= masks[index]
        weights = 1 / (1 + counts)
        baseline_union = np.count_nonzero((counts > 0) | masks[index])
        best, best_mask = original, masks[index]
        best_score = float(weights @ best_mask)
        for candidate in placement.candidates(original, maximum_shift, payload.get('adjust_wall_height', False), budget):
            if not placement.valid(candidate):
                continue
            if any(math.dist([candidate['x'], candidate['y'], candidate['z']], [other['x'], other['y'], other['z']]) < max(spacing, candidate['size'] + other['size']) for j, other in enumerate(markers) if j != index):
                continue
            mask = placement.visibility(candidate)
            if np.count_nonzero((counts > 0) | mask) < baseline_union:
                continue
            shift = math.dist([candidate['x'], candidate['y'], candidate['z']], [original['x'], original['y'], original['z']])
            score = float(weights @ mask) - .03 * len(mask) * shift / maximum_shift
            if score > best_score + 1e-6:
                best, best_mask, best_score = candidate, mask, score
        markers[index], masks[index] = best, best_mask
        counts += best_mask
        if any(abs(best[key] - original[key]) > 1e-6 for key in ('x', 'y', 'z', 'yaw')):
            changes.append({'id': original['id'], 'before': original, 'after': best,
                            'visible_samples_before': int(placement.visibility(original).sum()),
                            'visible_samples_after': int(best_mask.sum())})
    environment['goal'] = destination_goal(environment)
    after = counts > 0
    return {'markers': markers, 'changes': changes, 'goal': environment['goal'],
            'coverage_before_percent': round(float(before.mean()) * 100, 1),
            'coverage_after_percent': round(float(after.mean()) * 100, 1),
            'sample_count': len(placement.samples),
            'detail': 'Estimated line-of-sight coverage from reachable floor positions; camera can turn toward markers. This is placement guidance, not measured localization.'}
