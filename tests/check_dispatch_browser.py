"""Check automatic waiting, incoming replay, and polling after playback."""
import json
from pathlib import Path
import subprocess
import time
from urllib.request import urlopen
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    python = ROOT.parent / 'Kenny---Automotive-self-driving-trash-can/.venv/bin/python'
    server = subprocess.Popen([str(python), str(ROOT / 'backend/server.py'), '--port', '8002'],
                              cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(80):
            try:
                with urlopen('http://127.0.0.1:8002/api/models', timeout=1):
                    break
            except OSError:
                time.sleep(.1)
        project = json.loads((ROOT / 'fixtures/marker-destination-room.json').read_text())
        replay = {'dt': .1, 'model': 'test/best.zip', 'seed': 42, 'robot_radius': .2,
                  'destination_marker_id': 12, 'goal': project['goal'], 'destination': project['goal'],
                  'info': {'event': 'success', 'steps': 2, 'interventions': 0, 'path_length': 1,
                           'localization_error': 0, 'no_route_steps': 0, 'intervention_reasons': {}},
                  'frames': [{'step': i, 'pose': [*project['start'], 0], 'estimate': [*project['start'], 0],
                              'route': [], 'event': 'success' if i else 'running', 'intervened': False,
                              'distance_to_destination_m': 1, 'near_goal': True} for i in range(2)]}
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            errors = []
            polls = []
            motors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.add_init_script('localStorage.setItem("kenny-project",' + json.dumps(json.dumps(project)) + ');')
            page.route('**/api/models', lambda route: route.fulfill(json=[{'id': 'test/best.zip', 'stage': 'mixed', 'bytes': 1}]))
            page.route('**/api/simulate/warm', lambda route: route.fulfill(json={'ok': True, 'model_resident': True}))
            page.route('**/api/dispatch/pose', lambda route: route.fulfill(json={'ok': True}))

            def poll(route):
                polls.append(json.loads(route.request.post_data))
                if len(polls) == 1:
                    route.fulfill(json={'job': {'marker_id': 12}, 'replay': replay, 'status': 'succeeded', 'detail': 'Simulation: success'})
                else:
                    route.fulfill(json={'job': None, 'detail': 'Connected — waiting for an ArUco call'})

            page.route('**/api/dispatch/tick', poll)
            page.route('**/api/usb/**', lambda route: (motors.append(route.request.url), route.fulfill(json={'ok': True})))
            page.goto('http://127.0.0.1:8002/')
            page.get_by_text('Destination reached', exact=True).wait_for(timeout=15000)
            page.get_by_text('Connected — waiting for an ArUco call', exact=True).wait_for(timeout=15000)
            assert len(polls) >= 2
            assert polls[0]['environment']['markers'] == project['markers']
            assert not errors, errors
            assert not motors, motors
            page.get_by_role('button', name='Disconnect API receiver').click()
            count = len(polls)
            page.wait_for_timeout(5500)
            assert len(polls) == count
            browser.close()
        print('Browser receiver: automatic polling, incoming replay, next-call waiting, disconnect, no motor calls passed')
    finally:
        server.terminate()
        server.wait(timeout=10)


if __name__ == '__main__':
    main()
