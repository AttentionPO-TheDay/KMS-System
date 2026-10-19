"""Keep both site origins valid without moving browser keys or recreating containers."""
import http.client
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import time

BASE = Path('/home/rbf/kms-sys')
ROOT = BASE / 'releases/browser-origin-compat-20261019'
ACCESS = BASE / 'server-access-ip-20261019'
OLD, NEW = '10.112.125.22', '10.129.114.144'


def run(*args):
    p = subprocess.run(args, capture_output=True, timeout=30)
    if p.returncode:
        raise RuntimeError('COMMAND_FAILED ' + ' '.join(args[:3]))
    return p.stdout


def services():
    ids = run('docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project=kms-ops').decode().split()
    return {c['Name']: {'id': c['Id'], 'startedAt': c['State']['StartedAt']}
            for c in json.loads(run('docker', 'inspect', *ids))}


def check_origin(host, context):
    with socket.create_connection((NEW, 8443), timeout=10) as tcp:
        with context.wrap_socket(tcp, server_hostname=host) as tls:
            tls.sendall(('GET /updatedel/demo HTTP/1.1\r\nHost: ' + host + ':8443\r\nConnection: close\r\n\r\n').encode())
            response = http.client.HTTPResponse(tls)
            response.begin()
            assert response.status == 200, 'ORIGIN_HTTP_FAILED'
            response.read()


def main():
    os.umask(0o077)
    backup = ROOT / 'backup'
    backup.mkdir(mode=0o700)
    before = services()
    (backup / 'services.json').write_text(json.dumps(before))
    cert = ACCESS / 'tls/server.crt'
    key = ACCESS / 'tls/server.key'
    template = ACCESS / 'kms-demo.template'
    original_cert, original_template = cert.read_bytes(), template.read_bytes()
    (backup / 'server.crt').write_bytes(original_cert)
    (backup / 'kms-demo.template').write_bytes(original_template)
    new_cert = ROOT / 'kms-compatible-server.crt'
    run('openssl', 'req', '-x509', '-new', '-key', str(key), '-days', '365',
        '-out', str(new_cert), '-subj', '/CN=' + NEW,
        '-addext', 'subjectAltName=IP:' + OLD + ',IP:' + NEW,
        '-addext', 'basicConstraints=critical,CA:FALSE')
    for address in (OLD, NEW):
        run('openssl', 'verify', '-trusted', str(new_cert), '-verify_ip', address, str(new_cert))
    old_names = 'server_name ' + NEW + ';'
    text = original_template.decode()
    assert text.count(old_names) == 2, 'UNEXPECTED_NGINX_TEMPLATE'
    text = text.replace(old_names, 'server_name ' + OLD + ' ' + NEW + ';')
    text = text.replace('return 308 https://' + NEW + ':8443$request_uri;',
                        'return 308 https://$host:8443$request_uri;')
    try:
        cert.write_bytes(new_cert.read_bytes())
        # Preserve the inode of the file bind-mounted into the running gateway.
        template.write_text(text)
        run('docker', 'exec', 'kms_gateway', 'cp', '/etc/nginx/kms-demo.template', '/etc/nginx/kms-demo.conf')
        run('docker', 'exec', 'kms_gateway', 'nginx', '-t')
        run('docker', 'exec', 'kms_gateway', 'nginx', '-s', 'reload')
        time.sleep(0.5)
        context = ssl.create_default_context(cafile=str(new_cert))
        for address in (OLD, NEW):
            check_origin(address, context)
        assert services() == before, 'A_KMS_CONTAINER_CHANGED'
    except Exception:
        cert.write_bytes(original_cert)
        template.write_bytes(original_template)
        run('docker', 'exec', 'kms_gateway', 'cp', '/etc/nginx/kms-demo.template', '/etc/nginx/kms-demo.conf')
        run('docker', 'exec', 'kms_gateway', 'nginx', '-t')
        run('docker', 'exec', 'kms_gateway', 'nginx', '-s', 'reload')
        raise
    result = {'certificateIpSans': [OLD, NEW], 'strictTlsAndHttp200': True,
              'allKmsContainerIdsAndStartTimesUnchanged': True, 'privateKeysMoved': False}
    (ROOT / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    (ROOT / 'applied').touch()
    print('COMPATIBILITY_OK ' + json.dumps(result))
    print(run('openssl', 'x509', '-in', str(new_cert), '-noout', '-fingerprint', '-sha256').decode().strip())


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('COMPATIBILITY_FAILED ' + type(error).__name__ +
              (' ' + str(error) if isinstance(error, (RuntimeError, AssertionError)) else ''))
        raise SystemExit(1)
