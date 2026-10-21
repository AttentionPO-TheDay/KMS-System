"""Publish reviewed UI copy and the matching node-DID API without changing chain settings."""
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import time
import urllib.request

ROOT = Path('/home/rbf/kms-sys')
HERE = Path(__file__).resolve().parent
TARGETS = {'nginx': 'kms_gateway', 'dvadmin3-django': 'dvadmin3-django',
           'fabric-did-bridge': 'kms_fabric_did'}
IMAGES = {'nginx': 'kms-gateway-nginx:copy-cleanup-20261020',
          'dvadmin3-django': 'kms-dvadmin3-django:copy-cleanup-20261020',
          'fabric-did-bridge': 'kms-fabric-did:copy-cleanup-20261020'}


def run(args, *, timeout=90, log=None):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=timeout)
    if log:
        (HERE / log).write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError('COMMAND_FAILED ' + ' '.join(map(str, args[:3])) + '; details withheld')
    return result.stdout


def snapshot():
    return {name: json.loads(run(['docker', 'inspect', name]))[0] for name in TARGETS.values()}


def atomic_write(path, content):
    temporary = path.with_name(path.name + '.copy-cleanup.tmp')
    with temporary.open('xb') as handle:
        os.chmod(temporary, 0o600)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def signature(item):
    return {'mounts': sorted((m['Type'], m['Source'], m['Destination'], m.get('RW')) for m in item['Mounts']),
            'ports': item['HostConfig']['PortBindings'], 'env': sorted(item['Config']['Env']),
            'entrypoint': item['Config']['Entrypoint'], 'cmd': item['Config']['Cmd']}


CHECK = '''import json, os
from django.db import connection
from django.urls import resolve
from pqkds.models import NodeKeyDidRecord
print(json.dumps({'route':resolve('/api/pqkds/node-self/keys/did/').url_name,
'schemaReady':NodeKeyDidRecord._meta.db_table in connection.introspection.table_names(),
'didNodeEnabled':os.environ.get('FABRIC_DID_NODE_KEYGEN_ENABLED','false')}))
'''


def main():
    os.umask(0o077)
    manifest = json.loads((HERE / 'manifest.json').read_text())
    for name, expected in manifest['sha256'].items():
        assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() == expected, name
    before = snapshot()
    labels = before['kms_gateway']['Config']['Labels']
    assert labels['com.docker.compose.project.working_dir'] == str(ROOT)
    compose = ['docker', 'compose', '-p', labels['com.docker.compose.project']]
    for file in labels['com.docker.compose.project.config_files'].split(','):
        compose.extend(['-f', file])
    compose.extend(['--profile', 'fabric-did'])
    for service, name in TARGETS.items():
        assert before[name]['Config']['Labels']['com.docker.compose.service'] == service
        assert before[name]['Image'] == manifest['baseImages'][service], 'BASE_IMAGE_CHANGED'
    original_file = ROOT / 'docker-compose.yml'
    original = original_file.read_bytes()
    baseline = json.loads(original)
    backup = HERE / ('backup-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    backup.mkdir(mode=0o700)
    (backup / 'docker-compose.yml').write_bytes(original)
    (backup / 'runtime-signatures.json').write_text(json.dumps({n:signature(c) for n,c in before.items()}))
    for service, name in TARGETS.items():
        previous = IMAGES[service].replace(':copy-cleanup-', ':before-copy-cleanup-')
        run(['docker', 'image', 'tag', before[name]['Image'], previous])
        if service == 'nginx':
            steps = ('RUN rm -f /usr/share/nginx/html/updatedel/index.html.gz /usr/share/nginx/html/acceptance/index.html.gz\n'
                     'COPY updatedel/ /usr/share/nginx/html/updatedel/\n'
                     'COPY acceptance/ /usr/share/nginx/html/acceptance/\n'
                     'RUN find /usr/share/nginx/html/updatedel /usr/share/nginx/html/acceptance -type d -exec chmod 755 {} + '
                     '&& find /usr/share/nginx/html/updatedel /usr/share/nginx/html/acceptance -type f -exec chmod 644 {} +\n')
        elif service == 'dvadmin3-django':
            steps = 'COPY django/pqkds/ /backend/pqkds/\n'
        else:
            command = (before[name]['Config']['Entrypoint'] or []) + (before[name]['Config']['Cmd'] or [])
            bridge_jar = command[command.index('-jar') + 1]
            assert bridge_jar.startswith('/') and bridge_jar.endswith('.jar')
            steps = 'COPY ' + json.dumps(['runtime/app.jar', bridge_jar]) + '\n'
        dockerfile = HERE / ('Dockerfile.' + service)
        dockerfile.write_text('FROM ' + previous + '\n' + steps)
        run(['docker', 'build', '--network=none', '--pull=false', '-f', str(dockerfile),
             '-t', IMAGES[service], str(HERE)], timeout=120, log=service+'-build.log')
        if service == 'fabric-did-bridge':
            actual = run(['docker','run','--rm','--network=none','--entrypoint','sha256sum',
                          IMAGES[service],bridge_jar]).decode().split()[0]
            assert actual == manifest['sha256']['runtime/app.jar'], 'BRIDGE_JAR_MISMATCH'
    run(['docker', 'run', '--rm', '--network=none', '--entrypoint', '/opt/venv/bin/python',
         '--mount', 'type=bind,source='+str(HERE/'tests/test_node_key_did_offline.py')+
         ',target=/backend/tests/test_node_key_did_offline.py,readonly',
         IMAGES['dvadmin3-django'], '/backend/tests/test_node_key_did_offline.py'],
        log='backend-offline-tests.log')
    updated = json.loads(json.dumps(baseline))
    for service, image in IMAGES.items():
        updated['services'][service]['image'] = image
    # Entire runtime configuration must be identical except for these image references.
    expected = json.loads(json.dumps(updated))
    for service in IMAGES:
        expected['services'][service]['image'] = baseline['services'][service]['image']
    assert expected == baseline
    def up():
        return run(compose + ['up', '-d', '--no-deps', '--no-build', '--pull', 'never', *IMAGES],
                   timeout=120, log='compose.log')
    try:
        atomic_write(original_file, (json.dumps(updated, indent=2) + '\n').encode())
        run(compose + ['config', '--quiet'])
        run(compose + ['run', '--rm', '--no-deps', 'nginx', 'nginx', '-t'])
        up()
        for attempt in range(30):
            try:
                result = run(['docker', 'exec', 'dvadmin3-django', '/opt/venv/bin/python',
                              'manage.py', 'shell', '-c', CHECK], timeout=10)
                check = json.loads(result.decode().strip().splitlines()[-1])
                assert check['schemaReady'] and check['route'] == 'node-self-key-did'
                run(['docker', 'exec', 'dvadmin3-django', '/opt/venv/bin/python', '-c',
                     "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ws/',timeout=2)"], timeout=5)
                break
            except (RuntimeError, AssertionError, ValueError, IndexError):
                if attempt == 29:
                    raise
                time.sleep(1)
        run(['docker', 'exec', 'kms_gateway', 'nginx', '-t'])
        after = snapshot()
        assert all(signature(after[n]) == signature(before[n]) for n in before)
        for service, name in TARGETS.items():
            actual = run(['docker', 'image', 'inspect', IMAGES[service], '--format', '{{.Id}}']).decode().strip()
            assert after[name]['Image'] == actual
        for app in ('updatedel','acceptance'):
            actual = run(['docker','exec','kms_gateway','sha256sum','/usr/share/nginx/html/'+app+'/index.html']).decode().split()[0]
            assert actual == manifest['sha256'][app+'/index.html']
        cert = ROOT/'server-access-ip-20261019/tls/server.crt'
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=str(cert))))
        pages = {}
        for path in ['/ping','/updatedel/demo','/acceptance/','/demo-api/lifecycle/demo/context']:
            with opener.open('https://10.112.125.22:8443'+path,timeout=10) as response:
                assert response.status == 200
                pages[path] = response.status
        result = {'deployed':True,'images':IMAGES,'backup':str(backup),'https':pages,
                  'runtimeConfigurationPreserved':True,'nodeDidApi':check,'testChainTransactionsSubmitted':0}
        (HERE/'deployment-result.json').write_text(json.dumps(result,indent=2)+'\n')
        print('DEPLOYMENT_OK '+json.dumps(result),flush=True)
    except Exception:
        atomic_write(original_file, original)
        up()
        print('DEPLOYMENT_ROLLED_BACK',flush=True)
        raise


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('DEPLOYMENT_FAILED '+type(exc).__name__+
              (' '+str(exc) if isinstance(exc,(RuntimeError,AssertionError)) else ''),flush=True)
        raise SystemExit(1)
