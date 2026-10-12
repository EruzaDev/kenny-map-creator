"""Persistent simulator subprocess: load/warm once, reuse policy for each trip."""
import contextlib
import json
from pathlib import Path
import sys

import numpy as np
import torch
from stable_baselines3 import PPO
from kenny_rl.config import load_config
from kenny_rl.env import KennyEnv
from kenny_rl.replay import run_replay


class ModelCache:
    def __init__(self):
        self.checkpoint = None
        self.model = None

    def load(self, checkpoint):
        checkpoint = Path(checkpoint).resolve()
        if checkpoint == self.checkpoint:
            return self.model
        source = checkpoint.parent.parent if checkpoint.parent.name == 'checkpoints' else checkpoint.parent
        robot, config, training = load_config(source / 'config.json')
        env = KennyEnv(robot, config)
        expected = json.loads(json.dumps(env.contract()))
        env.close()
        if json.loads((source / 'contract.json').read_text()) != expected:
            raise ValueError('Checkpoint contract differs from the current simulator')
        # Keep one selected policy in memory rather than accumulating runs.
        self.model = None
        model = PPO.load(checkpoint, device='cpu', custom_objects={
            'lr_schedule': lambda _: 0., 'learning_rate': 0.,
            'clip_range': lambda _: float(training.get('clip_range', .2)), 'clip_range_vf': None})
        model.predict(np.zeros(expected['frame_size'] * config.history, dtype=np.float32), deterministic=True)
        self.model, self.checkpoint = model, checkpoint
        return model


def main():
    torch.set_num_threads(1)
    cache = ModelCache()
    for line in sys.stdin:
        try:
            packet = json.loads(line)
            with contextlib.redirect_stdout(sys.stderr):
                model = cache.load(packet['model'])
                if packet['operation'] == 'replay':
                    result = run_replay(json.loads(Path(packet['input']).read_text()), packet['model'],
                        packet['steps'], packet['seed'], model=model, controller=packet['controller'])
                    Path(packet['output']).write_text(json.dumps(result, allow_nan=False))
                elif packet['operation'] != 'warm':
                    raise ValueError('Unknown model worker operation')
            reply = {'ok': True, 'model_resident': True}
        except Exception as error:
            reply = {'ok': False, 'detail': str(error)}
        print(json.dumps(reply), flush=True)


if __name__ == '__main__':
    main()
