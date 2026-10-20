"""Receive cloud calls and run them in the local simulator, never on motors."""
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import threading
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

from .navigation import simulate, models
from kenny_rl.environment import validate_environment

STATE = Path(__file__).resolve().parents[1] / 'data/simulation-receiver.json'
DEPLOYMENT = Path(__file__).resolve().parents[2] / 'Kenny-Api/data/deployment.json'
LOCK = threading.Lock()


class DispatchUnavailable(ValueError):
    pass


def post(path, payload):
    base = os.environ.get('KENNY_API_URL', 'https://kenny-api.onrender.com').rstrip('/')
    token = os.environ.get('KENNY_PI_TOKEN') or os.environ.get('KENNY_DISPATCH_TOKEN', '')
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    try:
        with urlopen(Request(base + path, data=json.dumps(payload).encode(), headers=headers), timeout=15) as response:
            return json.load(response)
    except (URLError, TimeoutError, ConnectionError) as error:
        raise DispatchUnavailable(f'Cloud API unavailable: {error}. Will retry without repeating navigation.') from error


def save(state):
    temporary = STATE.with_suffix('.tmp')
    with temporary.open('w') as stream:
        json.dump(state, stream, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(STATE)


def destination(environment, job):
    if environment['dictionary'] != job['dictionary']:
        raise ValueError('API call dictionary does not match the open simulation map')
    marker = next((m for m in environment['markers'] if m['id'] == job['marker_id']), None)
    if marker is None:
        raise ValueError(f"ArUco ID {job['marker_id']} is missing from the open simulation map")
    offset = .5 if marker.get('mount') == 'wall' else 0
    goal = [marker['x'] + math.cos(marker['yaw']) * offset,
            marker['y'] + math.sin(marker['yaw']) * offset]
    # Simulation destinations follow the ID on the open editor map. The cloud
    # coordinates may describe a different test scene or the physical robot.
    return {**environment, 'goal': goal, 'destination_marker_id': marker['id'], 'destination_offset_m': offset}


def publish_simulation_pose(payload):
    require_simulation_mode()
    route = payload.get('route', [])
    if len(route) > 200:
        route = [route[int(i * (len(route) - 1) / 199)] for i in range(200)]
    return post('/api/pi/pose', {'worker': 'kenny-simulation', 'source': 'simulation',
        'pose': payload['pose'], 'goal': payload.get('goal'), 'route': route,
        'status': 'navigating' if payload.get('playing') else 'idle', 'detail': 'Editor simulation replay',
        'observed_at': time.time(), 'uncertainty_m': payload.get('uncertainty_m')})


def tick(payload):
    """Claim at most one call; pending results are retried before new navigation."""
    if not LOCK.acquire(blocking=False):
        return {'job': None, 'detail': 'Simulation receiver is already busy'}
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        with STATE.with_suffix('.lock').open('w') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {'job': None, 'detail': 'Simulation receiver is already busy'}
            return consume(payload)
    finally:
        LOCK.release()


def consume(payload):
    require_simulation_mode()
    state = json.loads(STATE.read_text()) if STATE.exists() else {'phase': 'idle'}
    if state['phase'] == 'running':
        # A simulator process crash cannot be interpreted as arrival.
        state.update(phase='finished', outcome={'status': 'failed', 'detail': 'Simulation receiver interrupted'}, replay=None)
        save(state)
    if state['phase'] == 'idle':
        environment = payload['environment']
        validate_environment(environment)
        if payload['model'] not in {m['id'] for m in models()}:
            raise ValueError('Select a checkpoint before connecting the receiver')
        signature = hashlib.sha256(json.dumps({k: environment.get(k) for k in
            ('grid', 'markers', 'obstacles', 'dictionary', 'frame_id')}, sort_keys=True).encode()).hexdigest()
        position = state.get('position') if state.get('map') == signature else None
        worker = 'kenny-simulation'
        job = post('/api/pi/claim', {'worker': worker})['job']
        if job is None:
            return {'job': None, 'detail': 'Connected — waiting for an ArUco call'}
        state = {'phase': 'running', 'job': job, 'worker': worker, 'map': signature, 'position': position}
        save(state)
        try:
            environment = destination(environment, job)
            if position is not None:
                environment['start'] = position
            replay = simulate({**payload, 'environment': environment})
            pose = replay['frames'][-1]['pose']
            state['position'] = pose[:2]
            state['replay'] = replay
            state['outcome'] = {'status': 'succeeded' if replay['info']['event'] == 'success' else 'failed',
                                'detail': f"Simulation: {replay['info']['event']}"}
        except (ValueError, KeyError, TypeError, IndexError) as error:
            state['replay'] = None
            state['outcome'] = {'status': 'failed', 'detail': str(error)[:2000]}
        state['phase'] = 'finished'
        save(state)
    post(f"/api/calls/{state['job']['id']}/result", {**state['outcome'], 'worker': state['worker']})
    result = {'job': state['job'], 'replay': state.get('replay'), **state['outcome']}
    save({'phase': 'idle', 'position': state.get('position'), 'map': state['map']})
    return result


def require_simulation_mode():
    if DEPLOYMENT.exists() and json.loads(DEPLOYMENT.read_text()).get('mode') == 'robot':
        raise ValueError('Robot mode is active. Switch to Simulation in the operations dashboard before connecting the simulation receiver.')
