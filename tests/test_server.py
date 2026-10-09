"""Exercise HTTP route handling without binding prohibited server sockets."""
import base64
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT.parent/'Kenny---Automotive-self-driving-trash-can'))
from backend.server import Handler
from ros.bridge import MappingSource


class Routes(unittest.TestCase):
    def call(self,path,body=None):
        handler=Handler.__new__(Handler);handler.path=path
        raw=json.dumps(body).encode() if body is not None else b''
        handler.headers={'Content-Length':str(len(raw))};handler.rfile=io.BytesIO(raw)
        result={}
        def respond(body,status=200,content_type='application/json',filename=None):result.update(body=body,status=status,content_type=content_type,filename=filename)
        handler.respond=respond;handler.log_error=lambda *args:None
        (handler.do_POST if body is not None else handler.do_GET)()
        return result
    def test_marker_and_missing(self):
        r=self.call('/api/markers/7.png');self.assertEqual(r['status'],200);self.assertTrue(r['body'].startswith(b'\x89PNG'))
        self.assertEqual(self.call('/api/markers/50.png')['status'],422)
        self.assertEqual(self.call('/../../backend/server.py')['status'],404)
    def test_export_validation_and_success(self):
        env=json.loads((ROOT/'fixtures/sample-room.json').read_text())
        r=self.call('/api/export',env);self.assertEqual(r['status'],200);self.assertTrue(r['body'].startswith(b'PK'))
        env['start']=[100,100]
        self.assertEqual(self.call('/api/export',env)['status'],422)
    def test_map_source_age_and_immutability(self):
        source=MappingSource();self.assertIsNone(source.snapshot())
        env=json.loads((ROOT/'fixtures/sample-room.json').read_text())
        source.update_map(env['grid']);source.update_pose([0,0,0]);snap=source.snapshot()
        source.update_map({**env['grid'],'origin':[0,0,0]})
        self.assertEqual(snap['grid']['origin'],[-2,-1,0]);self.assertGreater(source.snapshot()['revision'],snap['revision'])
        with patch('ros.bridge.time.time',return_value=source.updated+10):self.assertGreaterEqual(source.snapshot()['map_age_seconds'],10)

if __name__=='__main__':unittest.main()

class AudioAssetRoutes(unittest.TestCase):
    def call(self,path,body=None):
        return Routes.call(self,path,body)
    def test_url_encoded_recording_name_is_served(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            asset=Path(temp)/'dist/assets/im near-test.mp3';asset.parent.mkdir(parents=True);asset.write_bytes(b'example recording')
            with patch('backend.server.ROOT',Path(temp)):
                response=self.call('/assets/im%20near-test.mp3')
            self.assertEqual(response['status'],200)
            self.assertEqual(response['content_type'],'audio/mpeg')
            self.assertEqual(response['body'],b'example recording')
