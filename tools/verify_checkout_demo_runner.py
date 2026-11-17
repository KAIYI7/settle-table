"""Run an isolated mock demo with the checkout demo enabled against an in-process stub bridge.

Browser-test only. The stub follows the KP-SETTLETABLE-TNG-01 v2.1 wire contract.
The bridge credential and namespace are disposable random values for this process.
The readiness endpoint reports the stub port so the test can drive the stub's
nonce-protected control channel (synthetic candidate, organizer confirm, expiry).
"""
import os
from pathlib import Path
import secrets
import sys
import uuid

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from tools import run_demo  # noqa: E402
from checkout_demo_stub import StubBridge  # noqa: E402

nonce = os.environ['SETTLETABLE_TEST_NONCE']
bridge_token = secrets.token_urlsafe(32)
stub = StubBridge(bridge_token, control_nonce=nonce)
os.environ.update({
    'SETTLETABLE_CHECKOUT_DEMO_ENABLED': '1',
    'SETTLETABLE_CHECKOUT_DEMO_NAMESPACE': str(uuid.uuid4()),
    'SETTLETABLE_CHECKOUT_DEMO_BASE_URL': stub.base_url,
    'SETTLETABLE_CHECKOUT_DEMO_CREDENTIAL': bridge_token,
})
os.environ.pop('SETTLETABLE_CHECKOUT_DEMO_CREDENTIALS_FILE', None)
os.environ.pop('SETTLETABLE_CHECKOUT_DEMO_CA_FILE', None)
readiness_path = '/__checkout_demo_ready/' + nonce
original_make_server = run_demo.make_server


def make_server(host, port, application):
    def wrapped(environ, start_response):
        if environ.get('REQUEST_METHOD') == 'GET' and environ.get('PATH_INFO') == readiness_path:
            body = f'owned-test-server:{stub.server.server_port}'.encode()
            start_response('200 OK', [('Content-Type', 'text/plain'), ('Content-Length', str(len(body)))])
            return [body]
        return application(environ, start_response)
    return original_make_server(host, port, wrapped)


run_demo.make_server = make_server
if __name__ == '__main__':
    run_demo.main()
