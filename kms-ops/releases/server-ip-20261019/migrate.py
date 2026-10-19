"""Migrate gateway bindings, TLS and application access lists without changing data."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
import ssl

BASE = Path('/home/rbf/kms-sys')
ROOT = BASE / 'releases/server-ip-20261019'
ACCESS = BASE / 'server-access-ip-20261019'
OLD, NEW = '10.112.125.22', '10.129.114.144'
CLIENTS = ('generate-java', 'updatedel-java', 'dvadmin3-django', 'acceptance-backend')
COMPOSE = ['docker', 'compose', '-p', 'kms-ops', '-f', str(BASE / 'docker-compose.yml'),
           '-f', str(BASE / 'docker-compose.fisco-enabled.yml'), '--profile', 'fabric-did']


def run(*args):
    result = subprocess.run(args, capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError('COMMAND_FAILED ' + ' '.join(args[:3]))
    return result.stdout


def containers():
    ids = run('docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project=kms-ops').split()
    return json.loads(run('docker', 'inspect', *(i.decode() for i in ids)))


def main():
    os.umask(0o077)
    os.chdir(BASE)
    assert not (ROOT / 'applied').exists()
    addresses = json.loads(run('ip', '-j', '-4', 'addr', 'show'))
    assert NEW in {a['local'] for i in addresses for a in i.get('addr_info', [])}
    backup = ROOT / 'backup'
    backup.mkdir(mode=0o700)
    before = containers()
    original = (BASE / 'docker-compose.yml').read_bytes()
    (backup / 'docker-compose.yml').write_bytes(original)
    (backup / 'containers.json').write_text(json.dumps(before))
    template = run('docker', 'exec', 'kms_gateway', 'cat', '/etc/nginx/kms-demo.template').decode()
    (backup / 'kms-demo.template').write_text(template)
    spec = importlib.util.spec_from_file_location('expose', BASE / 'expose-server.py')
    expose = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(expose)
    config = json.loads(run('docker', 'compose', '-p', 'kms-ops', '-f', str(BASE / 'docker-compose.yml'),
                            '--profile', 'fabric-did', 'config', '--no-interpolate',
                            '--no-path-resolution', '--format', 'json'))
    gateway = config['services']['nginx']
    gateway['ports'] = [p for p in gateway['ports'] if p.get('host_ip') != OLD]
    expose.configure(config, NEW)
    ACCESS.mkdir(mode=0o700)
    (ACCESS / 'tls').mkdir(mode=0o700)
    (ACCESS / 'kms-demo.template').write_text(expose.server_template(template, NEW))
    for volume in gateway['volumes']:
        if volume.get('target') == '/etc/nginx/kms-demo.template':
            volume['source'] = str(ACCESS / 'kms-demo.template')
        elif volume.get('target') == '/run/kms-server-tls':
            volume['source'] = str(ACCESS / 'tls')
    cert, key = ACCESS / 'tls/server.crt', ACCESS / 'tls/server.key'
    run('openssl', 'req', '-x509', '-nodes', '-newkey', 'rsa:2048', '-days', '365',
        '-keyout', str(key), '-out', str(cert), '-subj', '/CN=' + NEW,
        '-addext', 'subjectAltName=IP:' + NEW, '-addext', 'basicConstraints=critical,CA:FALSE')
    os.chmod(key, 0o600)
    changed = False
    try:
        expose.helpers.atomic_write(BASE / 'docker-compose.yml', (json.dumps(config, indent=2) + '\n').encode())
        run(*COMPOSE, 'config', '--quiet')
        run(*COMPOSE, 'run', '--rm', '--no-deps', 'nginx', 'nginx', '-t')
        print('CONFIG_AND_TLS_VALIDATED', flush=True)
        changed = True
        run(*COMPOSE, 'up', '-d', '--no-deps', '--no-build', '--force-recreate', *CLIENTS, 'nginx')
        run('docker', 'exec', 'kms_gateway', 'nginx', '-t')
        after = containers()
        changed_names = {'/kms_gateway', '/kms_generate_java', '/kms_updatedel_java',
                         '/dvadmin3-django', '/kms_acceptance_backend'}
        current = {i['Name']: i for i in after}
        for item in before:
            if item['Name'] not in changed_names:
                assert current[item['Name']]['Id'] == item['Id'], 'UNRELATED_CONTAINER_CHANGED'
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                    urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=str(cert))))
        results = {}
        for path in ('/ping', '/updatedel/demo', '/acceptance/'):
            for attempt in range(15):
                try:
                    with opener.open('https://' + NEW + ':8443' + path, timeout=8) as response:
                        results[path] = response.status
                    break
                except OSError:
                    if attempt == 14:
                        raise
                    time.sleep(1)
        # The original root-owned trust file is retained; deliver the new public certificate separately.
        (ROOT / 'kms-server-10.129.114.144.crt').write_bytes(cert.read_bytes())
        os.chmod(ROOT / 'kms-server-10.129.114.144.crt', 0o644)
        result = {'ip': NEW, 'httpsPages': results, 'unrelatedContainerIdsUnchanged': True,
                  'recreatedServices': list(CLIENTS) + ['nginx']}
        (ROOT / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        (ROOT / 'applied').touch()
        print('IP_MIGRATION_OK ' + json.dumps(result), flush=True)
        print(run('openssl', 'x509', '-in', str(cert), '-noout', '-fingerprint', '-sha256').decode().strip())
    except Exception:
        expose.helpers.atomic_write(BASE / 'docker-compose.yml', original)
        if changed:
            run(*COMPOSE, 'up', '-d', '--no-deps', '--no-build', '--force-recreate', *CLIENTS, 'nginx')
        print('IP_MIGRATION_ROLLED_BACK', flush=True)
        raise


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('IP_MIGRATION_FAILED ' + type(error).__name__ +
              (' ' + str(error) if isinstance(error, (RuntimeError, AssertionError)) else ''), flush=True)
        raise SystemExit(1)
