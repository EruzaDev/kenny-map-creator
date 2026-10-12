"""Cloud preview/open and marker suggestion preview/apply/undo."""
import copy
import json
from pathlib import Path
import subprocess
import time
from urllib.request import urlopen

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def main():
    python = ROOT.parent / 'Kenny---Automotive-self-driving-trash-can/.venv/bin/python'
    server = subprocess.Popen([str(python), str(ROOT / 'backend/server.py'), '--port', '8003'],
                              cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(80):
            try:
                with urlopen('http://127.0.0.1:8003/api/models', timeout=1):
                    break
            except OSError:
                time.sleep(.1)
        project = json.loads((ROOT / 'fixtures/marker-destination-room.json').read_text())
        cloud = copy.deepcopy(project)
        cloud['name'] = 'Fetched cloud room'
        original = next(m for m in project['markers'] if m['id'] == 7)
        proposal = {**original, 'x': original['x'] + .5, 'y': original['y'] + .5}
        optimized = [{**m} if m['id'] != 7 else proposal for m in project['markers']]
        packet = {'environment': cloud, 'sha256': 'a' * 64, 'revision': 2, 'updated': 1}
        uploads = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.add_init_script('localStorage.setItem("kenny-project",' + json.dumps(json.dumps(project)) + ');')
            page.route('**/api/models', lambda route: route.fulfill(json=[]))
            page.route('**/api/cloud/map/fetch', lambda route: route.fulfill(json=packet))
            def upload(route):
                uploads.append(json.loads(route.request.post_data))
                route.fulfill(json={**packet, 'revision': 3, 'environment': uploads[-1]['environment']})
            page.route('**/api/cloud/map/upload', upload)
            page.route('**/api/markers/optimize', lambda route: route.fulfill(json={'markers': optimized,
                'changes': [{'id': 7, 'before': original, 'after': proposal, 'visible_samples_before': 5, 'visible_samples_after': 10}],
                'coverage_before_percent': 20, 'coverage_after_percent': 40, 'sample_count': 100, 'detail': 'Estimated geometry'}))
            page.goto('http://127.0.0.1:8003/')
            page.get_by_role('button', name='Fetch map from Render', exact=True).click()
            page.get_by_role('img', name='Map fetched from Render').wait_for()
            assert page.get_by_label('Map name').input_value() == project['name']
            page.get_by_role('button', name='Preview optimized ArUco positions', exact=True).click()
            page.locator('[data-marker-optimization-id="7"]').wait_for()
            page.get_by_role('button', name='Apply optimized positions', exact=True).click()
            page.wait_for_function('JSON.parse(localStorage.getItem("kenny-project")).markers.find(m=>m.id===7).x===.5')
            page.get_by_title('Undo', exact=True).click()
            page.wait_for_function('JSON.parse(localStorage.getItem("kenny-project")).markers.find(m=>m.id===7).x===0')
            page.get_by_role('button', name='Upload map to Render', exact=True).click()
            page.wait_for_function('document.querySelector(".notice")?.textContent.includes("Uploaded")')
            assert uploads[-1]['expected_sha256'] == packet['sha256']
            page.get_by_role('button', name='Fetch map from Render', exact=True).click()
            page.get_by_role('button', name='Open fetched map in editor', exact=True).click()
            expect(page.get_by_label('Map name')).to_have_value('Fetched cloud room')
            assert not errors, errors
            browser.close()
        print('Editor browser: read-only cloud fetch, upload hash, marker preview/apply/undo and fetched-map opening passed')
    finally:
        server.terminate()
        server.wait(timeout=10)


if __name__ == '__main__':
    main()
