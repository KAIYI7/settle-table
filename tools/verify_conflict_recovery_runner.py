"""Run an isolated mock demo with a per-process readiness endpoint for browser tests."""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools import run_demo

original_make_server = run_demo.make_server
readiness_path = '/__conflict_test_ready/' + os.environ['SETTLETABLE_TEST_NONCE']


def make_server(host, port, application):
    def wrapped(environ, start_response):
        if environ.get('REQUEST_METHOD') == 'GET' and environ.get('PATH_INFO') == readiness_path:
            body = b'owned-test-server'
            start_response('200 OK', [('Content-Type', 'text/plain'), ('Content-Length', str(len(body)))])
            return [body]
        return application(environ, start_response)
    return original_make_server(host, port, wrapped)


run_demo.make_server = make_server
if __name__ == '__main__':
    run_demo.main()
