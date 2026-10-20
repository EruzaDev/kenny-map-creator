"""Explicit operator pose initialization; no motor commands or fake clearance."""
import math
from urllib.request import urlopen
import json

from .cloud_maps import remote_map


def apply_placement(payload, source):
    if not isinstance(payload,dict):raise ValueError('Placement request must be an object')
    if source is None:raise ValueError('ROS placement bridge unavailable')
    lock=getattr(source,'apply_lock',None)
    if lock is not None and not lock.acquire(blocking=False):
        raise ValueError('Another pose update is in progress; wait before applying again')
    try:return _apply_placement(payload,source)
    finally:
        if lock is not None:lock.release()


def _apply_placement(payload, source):
    if source is None or getattr(source,'apply_callback',None) is None:
        raise ValueError('ROS placement bridge unavailable; pose cannot be applied in fixture/offline mode')
    pose=payload.get('pose')
    if not isinstance(pose,list) or len(pose)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in pose):
        raise ValueError('Placement must contain finite x, y and heading radians')
    if max(abs(pose[0]),abs(pose[1]))>10000:
        raise ValueError('Placement is outside supported map coordinates')
    snapshot=source.snapshot()
    if snapshot is None or payload.get('session_id')!=snapshot.get('session_id'):
        raise ValueError('Live bridge session changed; place Kenny again')
    if not snapshot.get('pose_live') or payload.get('source_frame')!=snapshot.get('pose_frame'):
        raise ValueError('Fresh source-frame pose required; place Kenny again')
    measured=payload.get('source_pose')
    if not isinstance(measured,list) or len(measured)!=3 or any(type(v) not in (int,float) or not math.isfinite(v)for v in measured):
        raise ValueError('Measured source pose is required')
    difference=math.atan2(math.sin(measured[2]-snapshot['pose'][2]),math.cos(measured[2]-snapshot['pose'][2]))
    if math.dist(measured[:2],snapshot['pose'][:2])>.05 or abs(difference)>.05:
        raise ValueError('Source pose changed; review/re-place Kenny before applying')
    environment=payload.get('environment')
    if not isinstance(environment,dict):raise ValueError('Editor map is required')
    active=remote_map()
    if payload.get('map_sha256')!=active['sha256']:
        raise ValueError('Render map changed; fetch the latest map before applying pose')
    for key in ('grid','markers','obstacles','frame_id','dictionary'):
        if environment.get(key)!=active['environment'].get(key):
            raise ValueError('Editor geometry/markers differ from Render; upload this map first')
    with urlopen('http://127.0.0.1:8002/api/status',timeout=3) as response:
        operations=json.load(response)
    if not operations.get('emergency_stop') or not operations.get('physical_stop_confirmed'):
        raise ValueError('STOP and encoder-confirmed stationary wheels are required before applying pose')
    current=source.snapshot()
    if current is None or current.get('session_id')!=payload['session_id'] or current.get('pose_frame')!=payload['source_frame'] or not current.get('pose_live'):
        raise ValueError('Live reference changed during pose update; place Kenny again')
    difference=math.atan2(math.sin(measured[2]-current['pose'][2]),math.cos(measured[2]-current['pose'][2]))
    if math.dist(measured[:2],current['pose'][:2])>.05 or abs(difference)>.05:
        raise ValueError('Source pose changed during update; review the placement and apply again')
    result=source.apply_callback(pose,active['sha256'])
    return {**result,'detail':'Operator placement applied to map-frame SLAM pose. No motor command issued; absolute accuracy is not independently verified.'}
