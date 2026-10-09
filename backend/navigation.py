"""Run trained checkpoints in the simulator's Python environment."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from kenny_rl.environment import validate_environment

SIMULATOR=Path(__file__).resolve().parents[2]/'Kenny---Automotive-self-driving-trash-can'
RUNS=SIMULATOR/'runs'
LOCK=threading.Lock()


def models():
    result=[]
    for path in RUNS.rglob('*.zip'):
        source=path.parent.parent if path.parent.name=='checkpoints' else path.parent
        if not (source/'config.json').is_file() or not (source/'contract.json').is_file():continue
        try:
            config=json.loads((source/'config.json').read_text())
            stage=config['environment']['stage']
        except (KeyError,ValueError):continue
        result.append({'id':path.relative_to(RUNS).as_posix(),'stage':stage,'bytes':path.stat().st_size})
    # Prefer full or mixed trained runs, and best checkpoints, over installation smoke runs.
    rank={'full':0,'dynamic':1,'mixed':2,'static':3,'empty':4}
    result.sort(key=lambda m:('smoke' in m['id'] or 'validation' in m['id'],rank.get(m['stage'],5),not m['id'].endswith('best.zip'),m['id']))
    return result


def simulate(payload):
    environment=payload['environment'];validate_environment(environment)
    mid=payload['model']
    if mid not in {m['id'] for m in models()}:raise ValueError('Select a checkpoint from the model list')
    steps=payload.get('steps',1200);seed=payload.get('seed',42)
    if type(steps) is not int or not 1<=steps<=3000:raise ValueError('Steps must be 1–3000')
    if type(seed) is not int or not 0<=seed<=2**32-1:raise ValueError('Seed must be an integer from 0 to 4294967295')
    python=Path(os.environ.get('KENNY_SIM_PYTHON',str(SIMULATOR/'.venv/bin/python')))
    if not python.is_file():raise ValueError('Simulator Python missing; set KENNY_SIM_PYTHON to the environment with Torch and Stable Baselines3 installed')
    if not LOCK.acquire(blocking=False):raise ValueError('Another navigation test is running. Wait for it to finish.')
    try:
        with tempfile.TemporaryDirectory(prefix='kenny-navigation-') as temp:
            input_path=Path(temp)/'environment.json';output_path=Path(temp)/'replay.json'
            input_path.write_text(json.dumps(environment,allow_nan=False))
            proc=subprocess.run([str(python),'-m','kenny_rl.replay','--environment',str(input_path),
                '--model',str(RUNS/mid),'--steps',str(steps),'--seed',str(seed),'--output',str(output_path)],
                cwd=SIMULATOR,env={**os.environ,'MPLCONFIGDIR':temp,'OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'},
                capture_output=True,text=True,timeout=180)
            if proc.returncode:
                raise ValueError('Simulation failed: '+(proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else proc.stdout.strip()[-500:]))
            result=json.loads(output_path.read_text());result['model']=mid;result['environment_name']=environment.get('name','Untitled environment')
            return result
    except subprocess.TimeoutExpired:raise ValueError('Navigation test exceeded 180 seconds. Reduce steps or map size.')
    finally:LOCK.release()
