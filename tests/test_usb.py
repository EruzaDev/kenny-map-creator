import io
import json
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.usb import usb_request


class UsbTests(unittest.TestCase):
    def test_drive_validation_before_any_hardware_request(self):
        for payload in ({'lease':1,'seq':1,'v':math.nan,'w':0},
                        {'lease':1,'seq':1,'v':.11,'w':0},
                        {'lease':0,'seq':1,'v':0,'w':0},
                        {'lease':1,'seq':True,'v':0,'w':0}):
            with patch('backend.usb.urlopen') as transport:
                with self.assertRaises(ValueError):usb_request('drive',payload)
                transport.assert_not_called()

    def test_commands_forward_to_local_bridge(self):
        with patch('backend.usb.urlopen',return_value=io.BytesIO(b'{"ok":true}')) as transport:
            self.assertTrue(usb_request('drive',{'lease':123,'seq':2,'v':.02,'w':0})['ok'])
            request=transport.call_args.args[0]
            self.assertEqual(request.full_url,'http://127.0.0.1:8765/api/drive')
            self.assertIn(b'lease=123',request.data)
            self.assertEqual(transport.call_args.kwargs['timeout'],.6)


if __name__=='__main__':unittest.main()
