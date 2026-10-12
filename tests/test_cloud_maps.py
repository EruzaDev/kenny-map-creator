import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / 'Kenny---Automotive-self-driving-trash-can'))
from backend.cloud_maps import remote_map, upload, CloudMapError


class CloudMapTests(unittest.TestCase):
    def setUp(self):
        self.environment = json.loads((ROOT / 'fixtures/marker-destination-room.json').read_text())
        self.packet = {'environment': self.environment, 'sha256': 'a' * 64, 'revision': 1, 'updated': 1.}

    def test_fetch_uses_configured_cloud_and_pi_token(self):
        with patch.dict('os.environ', {'KENNY_API_URL': 'https://test.example/', 'KENNY_PI_TOKEN': 'secret'}), patch('backend.cloud_maps.urlopen') as send:
            send.return_value.__enter__.return_value = io.BytesIO(json.dumps(self.packet).encode())
            self.assertEqual(remote_map(), self.packet)
            request = send.call_args.args[0]
            self.assertEqual(request.full_url, 'https://test.example/api/map')
            self.assertEqual(request.get_header('Authorization'), 'Bearer secret')
            self.assertIsNone(request.data)

    def test_upload_removes_background_and_uses_revision_hash(self):
        with patch('backend.cloud_maps.remote_map', side_effect=[self.packet, {**self.packet, 'revision': 2}]) as remote:
            result = upload({'environment': {**self.environment, 'background': {'data': 'image'}}})
            payload = remote.call_args.args[0]
            self.assertNotIn('background', payload['environment'])
            self.assertEqual(payload['expected_sha256'], self.packet['sha256'])
            self.assertEqual(result['revision'], 2)

    def test_not_deployed_and_conflict_errors_are_actionable(self):
        with patch('backend.cloud_maps.urlopen', side_effect=HTTPError('https://test/api/map', 404, 'Not found', {}, io.BytesIO(b'{}'))):
            with self.assertRaisesRegex(CloudMapError, 'not deployed'):
                remote_map()
        error = HTTPError('https://test/api/map', 409, 'Conflict', {}, io.BytesIO(b'{"detail":"Finish pending calls"}'))
        with patch('backend.cloud_maps.urlopen', side_effect=error):
            with self.assertRaisesRegex(CloudMapError, 'Finish pending calls') as raised:
                remote_map()
            self.assertEqual(raised.exception.status, 409)


if __name__ == '__main__':
    unittest.main()
