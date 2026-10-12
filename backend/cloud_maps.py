"""Same-origin editor adapter to the deployed API's persistent active map."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from kenny_rl.environment import validate_environment

MAX_BYTES = 32_000_000


class CloudMapError(ValueError):
    def __init__(self, message, status=503):
        super().__init__(message)
        self.status = status


def remote_map(payload=None):
    base = os.environ.get('KENNY_API_URL', 'https://kenny-api.onrender.com').rstrip('/')
    token = os.environ.get('KENNY_PI_TOKEN') or os.environ.get('KENNY_DISPATCH_TOKEN', '')
    headers = {'Accept': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    data = None
    if payload is not None:
        data = json.dumps(payload, allow_nan=False).encode()
        if len(data) > MAX_BYTES:
            raise CloudMapError('Map upload exceeds 32 MB', 413)
        headers['Content-Type'] = 'application/json'
    try:
        with urlopen(Request(base + '/api/map', data=data, headers=headers), timeout=60) as response:
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise CloudMapError('Fetched map exceeds 32 MB')
            result = json.loads(raw)
    except HTTPError as error:
        if error.code == 404:
            raise CloudMapError('Render map endpoints are not deployed yet. Deploy the updated Kenny-Api server.', 503) from error
        try:
            detail = json.loads(error.read(16384)).get('detail', str(error))
        except (ValueError, AttributeError):
            detail = str(error)
        raise CloudMapError(f'Render: {detail}', error.code) from error
    except (URLError, TimeoutError, ConnectionError) as error:
        raise CloudMapError(f'Render map service unavailable: {error}') from error
    except (ValueError, UnicodeDecodeError) as error:
        raise CloudMapError('Render returned an invalid map response') from error
    try:
        validate_environment(result['environment'])
        if not isinstance(result['sha256'], str) or len(result['sha256']) != 64 or type(result['revision']) is not int:
            raise ValueError('Missing map revision/hash')
    except (ValueError, KeyError, TypeError) as error:
        raise CloudMapError(f'Render map could not be opened: {error}') from error
    return result


def upload(payload):
    environment = {k: v for k, v in payload['environment'].items() if k != 'background'}
    validate_environment(environment)
    expected = payload.get('expected_sha256')
    if expected is None:
        expected = remote_map()['sha256']
    return remote_map({'environment': environment, 'expected_sha256': expected})
