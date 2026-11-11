#!/usr/bin/env python3
"""Run pytest in the prepared disposable app; block external network by default."""
import ipaddress
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'scratch/runtime/app'


def main():
    subprocess.run([sys.executable, str(ROOT / 'scripts/verify_baseline.py')], check=True)
    if not (APP / 'main.py').exists():
        raise SystemExit('Run .venv/bin/python scripts/prepare_review_runtime.py first')
    if not sys.argv[1:]:
        raise SystemExit('Specify test paths; this command does not run the full suite implicitly')
    manifest = APP.parent / 'file-hashes.json'
    if not manifest.is_file():
        raise SystemExit('Runtime checksum manifest missing; inspect/recreate the disposable runtime')
    for relative, expected in json.loads(manifest.read_text()).items():
        path = APP / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise SystemExit(f'Runtime file changed: {relative}; do not test a modified submission')
    os.environ.update(ADMIN_LOGIN='review-local', ADMIN_PASSWORD='review-local-only',
                      SECRET_KEY='synthetic-review-secret', GITHUB_TOKEN='synthetic-not-a-token',
                      CREDENTIALS_FILE=str(ROOT / 'scratch/runtime/no-real-credentials.json'),
                      GOOGLE_APPLICATION_CREDENTIALS=str(ROOT / 'scratch/runtime/no-real-credentials.json'),
                      PYTHON_DOTENV_DISABLED='1',
                      LOG_DIR=str(ROOT / 'scratch/runtime/logs'), PYTHONDONTWRITEBYTECODE='1')
    sys.dont_write_bytecode = True
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_lookup = socket.getaddrinfo

    def allowed(host):
        if isinstance(host, bytes):
            host = host.decode()
        if host in ('localhost', None):
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and not allowed(address[0]):
            raise OSError('External network blocked by review test guard; use a fake client')
        return original_connect(sock, address)

    def connect_ex(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and not allowed(address[0]):
            raise OSError('External network blocked by review test guard; use a fake client')
        return original_connect_ex(sock, address)

    def lookup(host, *args, **kwargs):
        if not allowed(host):
            raise OSError('External DNS blocked by review test guard; use a fake client')
        return original_lookup(host, *args, **kwargs)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.getaddrinfo = lookup
    # Python-level guard only: subprocesses/native code can bypass it. Not a sandbox.
    paths = []
    for argument in sys.argv[1:]:
        if argument.startswith('source/'):
            argument = str(APP / argument[len('source/'):])
        elif argument.startswith(('repro/', 'tests/')):
            argument = str(ROOT / argument)
        paths.append(argument)
    os.chdir(APP)
    sys.path.insert(0, str(APP))
    import pytest
    return pytest.main(['-p', 'no:cacheprovider', *paths])


if __name__ == '__main__':
    raise SystemExit(main())
