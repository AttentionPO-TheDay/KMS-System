"""Restore gateway bindings to 10.112.125.22; keep the existing dual-IP TLS setup."""
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import ssl
import subprocess
import time
import urllib.request

BASE = Path('/home/rbf/kms-sys')
OLD, NEW = '10.129.114.144', '10.112.125.22'
CERT = BASE / 'server-access-ip-20261019/tls/server.crt'
COMPOSE = ['docker', 'compose', '-p', 'kms-ops', '-f', str(BASE / 'docker-compose.yml'),
           '-f', str(BASE / 'docker-compose.fisco-enabled.yml'), '--profile', 'fabric-did']


def run(*args, timeout=60):
    result = subprocess.run(args, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('COMMAND_FAILED: ' + ' '.join(args[:3]) + '; details withheld')
    return result.stdout


def snapshot():
    ids = run('docker', 'ps', '-aq').decode().split()
    return {c['Name']: {'id': c['Id'], 'startedAt': c['State']['StartedAt']}
            for c in json.loads(run('docker', 'inspect', *ids))}


def atomic_write(path, content, mode):
    temporary = path.with_name(path.name + '.ip-return.tmp')
    with temporary.open('xb') as handle:
        os.chmod(temporary, mode)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def main():
    os.umask(0o077)
    os.chdir(BASE)
    interfaces = json.loads(run('ip', '-j', '-4', 'addr', 'show'))
    assert NEW in {a['local'] for i in interfaces for a in i.get('addr_info', [])}
    base = BASE / 'docker-compose.yml'
    original = base.read_bytes()
    original_mode = base.stat().st_mode & 0o777
    config = json.loads(original)
    ports = config['services']['nginx']['ports']
    changed = 0
    for port in ports:
        if port.get('host_ip') == OLD:
            assert (str(port['published']), int(port['target'])) in {
                ('80', 80), ('8088', 8088), ('8443', 443)}
            port['host_ip'] = NEW
            changed += 1
    assert changed == 3, 'EXPECTED_THREE_OLD_IP_BINDINGS'
    # The preexisting template, trust certificate, service allowlists and overlays already support NEW.
    run('openssl', 'verify', '-trusted', str(CERT), '-verify_ip', NEW, str(CERT))
    template = run('docker', 'exec', 'kms_gateway', 'cat', '/etc/nginx/kms-demo.template')
    assert ('server_name ' + NEW + ' ' + OLD + ';').encode() in template
    run('docker', 'exec', 'kms_gateway', 'nginx', '-t')
    before = snapshot()
    release = BASE / 'releases' / ('server-ip-return-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    release.mkdir(mode=0o700)
    (release / 'docker-compose.yml.backup').write_bytes(original)
    (release / 'containers-before.json').write_text(json.dumps(before, indent=2))
    atomic_write(base, (json.dumps(config, indent=2) + '\n').encode(), original_mode)
    try:
        run(*COMPOSE, 'config', '--quiet')
        run(*COMPOSE, 'run', '--rm', '--no-deps', 'nginx', 'nginx', '-t', timeout=90)
    except Exception:
        atomic_write(base, original, original_mode)
        raise
    print('CONFIG_VALIDATED; BACKUP=' + str(release), flush=True)
    # Only recreate the gateway: application containers and all data services stay in place.
    run(*COMPOSE, 'up', '-d', '--no-deps', '--no-build', '--force-recreate', 'nginx', timeout=90)
    run('docker', 'exec', 'kms_gateway', 'nginx', '-t')
    gateway = json.loads(run('docker', 'inspect', 'kms_gateway'))[0]
    actual_ports = gateway['HostConfig']['PortBindings']
    for published, target in [('80', '80/tcp'), ('8088', '8088/tcp'), ('8443', '443/tcp')]:
        assert any(p['HostIp'] == NEW and p['HostPort'] == published for p in actual_ports[target])
    assert not any(p['HostIp'] == OLD for rows in actual_ports.values() for p in rows)
    assert hashlib.sha256(template).digest() == hashlib.sha256(
        run('docker', 'exec', 'kms_gateway', 'cat', '/etc/nginx/kms-demo.template')).digest()
    after = snapshot()
    for name, state in before.items():
        if name != '/kms_gateway':
            assert after.get(name) == state, 'UNRELATED_CONTAINER_CHANGED: ' + name
    context = ssl.create_default_context(cafile=str(CERT))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                urllib.request.HTTPSHandler(context=context))
    results = {}
    for path in ['/ping', '/updatedel/demo', '/acceptance/', '/demo-api/lifecycle/demo/context']:
        for attempt in range(10):
            try:
                with opener.open('https://' + NEW + ':8443' + path, timeout=5) as response:
                    assert response.status == 200
                    if path.endswith('/demo/context'):
                        body = json.load(response)
                        assert body['code'] == 200 and body['data']['entryMode'] == 'DEMO'
                    results[path] = response.status
                break
            except OSError:
                if attempt == 9:
                    raise
                time.sleep(1)
    result = {'ip': NEW, 'https': results, 'onlyGatewayRecreated': True,
              'otherContainerCountUnchanged': len(before) - 1,
              'existingCertificateAndTemplateRetained': True,
              'backup': str(release)}
    (release / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print('IP_RETURN_OK ' + json.dumps(result), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('IP_RETURN_FAILED ' + type(exc).__name__ +
              (' ' + str(exc) if isinstance(exc, (RuntimeError, AssertionError)) else ''), flush=True)
        raise SystemExit(1)
