"""Bounded RPC transport to one persistent simulator/model process."""
import atexit
import json
import os
from pathlib import Path
import queue
import subprocess
import threading


class Worker:
    def __init__(self):
        self.process = None
        self.python = None
        self.replies = None
        self.lock = threading.Lock()

    def stop(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            self.process.stdin.close()
            self.process.stdout.close()
            self.process = None

    def request(self, python, simulator, packet, timeout=180):
        with self.lock:
            if self.process is None or self.process.poll() is not None or self.python != str(python):
                self.stop()
                self.python = str(python)
                script = Path(__file__).with_name('model_worker.py')
                self.process = subprocess.Popen([str(python), '-u', str(script)], cwd=simulator,
                    env={**os.environ, 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1',
                         'PYTHONPATH': str(simulator) + os.pathsep + os.environ.get('PYTHONPATH', '')},
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
                self.replies = queue.Queue()
                stream, replies = self.process.stdout, self.replies

                def receive():
                    try:
                        for line in stream:
                            replies.put(line)
                    finally:
                        replies.put(None)

                threading.Thread(target=receive, daemon=True).start()
            try:
                self.process.stdin.write(json.dumps(packet) + '\n')
                self.process.stdin.flush()
                line = self.replies.get(timeout=timeout)
                if line is None:
                    raise ValueError('Resident model worker exited; check server logs')
                result = json.loads(line)
                if not result.get('ok'):
                    raise ValueError(result.get('detail', 'Model worker failed'))
                return result
            except queue.Empty:
                self.stop()
                raise ValueError('Navigation test exceeded 180 seconds. Reduce steps or map size.')
            except (BrokenPipeError, OSError, json.JSONDecodeError):
                self.stop()
                raise ValueError('Resident model connection failed; retry to reload the selected policy')


WORKER = Worker()
atexit.register(WORKER.stop)
