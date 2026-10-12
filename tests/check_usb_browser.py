"""Map/model/browser/USB integration. Default uses mocked motor API.

--live-zero exercises the attached ESP32 with power fixed to ZERO.
Requires a built editor backend on localhost:8000 and Playwright.
"""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-zero',action='store_true')
    args=parser.parse_args()
    project=json.loads((ROOT/'fixtures/marker-destination-room.json').read_text())
    requests=[];errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page()
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.add_init_script('localStorage.setItem("kenny-project",'+json.dumps(json.dumps(project))+');')
        def motor_api(route):
            action=route.request.url.rsplit('/',1)[-1]
            body=json.loads(route.request.post_data or '{}')
            requests.append((action,body))
            if args.live_zero:
                if action=='drive':assert body['v']==0 and body['w']==0
                route.continue_();return
            result={'ok':True}
            if action=='status':result={'ready':True,'armed':False,'estop':False}
            if action=='arm':result['lease']=123
            route.fulfill(status=200,content_type='application/json',body=json.dumps(result))
        page.route('**/api/usb/**',motor_api)
        page.goto('http://localhost:8000/')
        page.get_by_label('Trained model').select_option('releases/dynamic-v3-seed2/model/best.zip')
        page.get_by_label('Max steps').fill('30')
        page.get_by_label('Play “I’m near” within 5 meters').uncheck()
        if args.live_zero:
            page.get_by_label('USB motor power').focus()
            page.keyboard.press('Home')
        button=page.get_by_role('button',name='▶ Drive ESP32 with this map')
        assert button.is_disabled()
        page.get_by_role('button',name='▶ Run navigation test').click()
        button.wait_for(state='visible')
        page.wait_for_function('!Array.from(document.querySelectorAll("button")).find(b=>b.textContent.includes("Drive ESP32 with this map")).disabled',timeout=120000)
        button.click()
        page.get_by_text('Map command playback finished. ESP32 stopped.',exact=True).wait_for(timeout=15000)
        drives=[body for action,body in requests if action=='drive']
        assert drives and requests[-1][0]=='stop',requests
        if not args.live_zero:assert any(abs(body['v'])+abs(body['w'])>0 for body in drives)
        assert all(abs(body['v'])<=.1 and abs(body['w'])<=.6 for body in drives)
        # A second playback can be interrupted immediately through STOP.
        button.click()
        page.wait_for_timeout(250)
        page.get_by_role('button',name='■ STOP ROBOT').click()
        page.wait_for_timeout(400)
        assert requests[-1][0]=='stop'
        assert not errors,errors
        browser.close()
    print('Map + trained model + browser + '+('REAL ESP32 (ZERO POWER)' if args.live_zero else 'mock USB')+': passed completion and STOP checks')


if __name__=='__main__':main()
