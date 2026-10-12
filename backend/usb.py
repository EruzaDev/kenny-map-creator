"""Same-origin adapter to the already-running local Kenny USB bridge."""
import json
import math
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BRIDGE='http://127.0.0.1:8765/api/'


def usb_request(action, payload=None):
    if action not in ('status','arm','drive','stop'):
        raise ValueError('Unknown USB command')
    if action=='drive':
        if not isinstance(payload,dict):raise ValueError('Missing drive command')
        lease,seq=payload.get('lease'),payload.get('seq')
        v,w=payload.get('v'),payload.get('w')
        if type(lease) is not int or not 0<lease<=2**32-1 or type(seq) is not int or not 0<=seq<=2**32-1:
            raise ValueError('Invalid USB session or sequence')
        if any(type(x) not in (int,float) or not math.isfinite(x) for x in (v,w)) or abs(v)>.1 or abs(w)>.6:
            raise ValueError('USB command exceeds controller limits')
        payload={'lease':lease,'seq':seq,'v':v,'w':w}
    body=None if action=='status' else urlencode(payload or {}).encode()
    try:
        with urlopen(Request(BRIDGE+action,data=body),timeout=.6) as response:
            result=json.load(response)
    except HTTPError as error:
        result=json.load(error)
        raise ValueError(result.get('error','ESP32 rejected the command')) from error
    except (URLError,TimeoutError,OSError) as error:
        raise ValueError('USB bridge unavailable. Start /home/kenny/joystick/scripts/usb_bridge.py') from error
    return result
