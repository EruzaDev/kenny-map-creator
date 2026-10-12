"""Open Kenny Map Editor and start its local backend/USB bridge if needed."""
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
HOME=ROOT.parent


def available(url):
    try:
        with urlopen(url,timeout=1) as response:return response.status==200
    except OSError:return False


def start(args,log,cwd):
    with log.open('a') as output:
        subprocess.Popen(args,cwd=cwd,stdin=subprocess.DEVNULL,stdout=output,
                         stderr=subprocess.STDOUT,start_new_session=True)


def main():
    logs=ROOT/'artifacts';logs.mkdir(exist_ok=True)
    device=Path('/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0')
    if device.exists() and not available('http://127.0.0.1:8765/api/status'):
        start(['/usr/bin/python3',str(HOME/'joystick/scripts/usb_bridge.py'),'--port',str(device)],
              logs/'usb.log',HOME/'joystick')
    if not available('http://127.0.0.1:8000/api/models'):
        python=HOME/'Kenny---Automotive-self-driving-trash-can/.venv/bin/python'
        start([str(python),str(ROOT/'backend/server.py')],logs/'editor.log',ROOT)
    for _ in range(40):
        if available('http://127.0.0.1:8000/api/models'):break
        time.sleep(.25)
    subprocess.run(['xdg-open','http://localhost:8000/'],check=False)


if __name__=='__main__':main()
