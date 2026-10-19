#!/usr/bin/env python3
"""Publish the acceptance result UI and backend while keeping other services intact."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.error
import urllib.request

os.umask(0o077)
release = Path(__file__).resolve().parent
root = Path('/home/rbf/kms-sys')
backup = release / 'backup'
targets = {'kms_acceptance_backend': 'acceptance-backend', 'kms_gateway': 'nginx'}
new_images = {'acceptance-backend': 'kms-acceptance-backend:process-20261019', 'nginx': 'kms-gateway-nginx:process-20261019'}
old_images = {'acceptance-backend': 'kms-acceptance-backend:before-process-20261019', 'nginx': 'kms-gateway-nginx:before-process-20261019'}


def run(*args):
    return subprocess.check_output(args, text=True)


def containers():
    ids = run('docker', 'ps', '-aq').split()
    return {c['Name'].lstrip('/'): c for c in json.loads(run('docker', 'inspect', *ids))}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


all_before = containers()
labels = all_before['kms_acceptance_backend']['Config']['Labels']
project = labels['com.docker.compose.project']
before = {name: c for name, c in all_before.items() if c['Config'].get('Labels', {}).get('com.docker.compose.project') == project}
if labels['com.docker.compose.project.working_dir'] != str(root):
    raise RuntimeError('unexpected deployment root')
manifest = json.loads((release / 'manifest.json').read_text())
for name, expected in manifest['sha256'].items():
    if digest(release / name) != expected:
        raise RuntimeError('payload digest mismatch: ' + name)
backup.mkdir(mode=0o700)  # Never overwrite a previous backup or deployment.
compose_file = root / 'docker-compose.yml'
shutil.copy2(compose_file, backup / 'docker-compose.yml')
os.chmod(backup / 'docker-compose.yml', 0o600)
snapshot = {name: {'id': c['Id'], 'startedAt': c['State']['StartedAt'], 'image': c['Config']['Image']} for name, c in before.items()}
(backup / 'containers.json').write_text(json.dumps(snapshot, indent=2) + '\n')
if all_before['kms_acceptance_backend']['Mounts']:
    raise RuntimeError('review acceptance audit mounts before changing deployment')
run('docker', 'cp', 'kms_acceptance_backend:/app/data', str(backup / 'audit-data'))
for name, service in targets.items():
    run('docker', 'image', 'tag', before[name]['Image'], old_images[service])

backend = release / 'backend-image'
gateway = release / 'gateway-image'
backend.mkdir(); gateway.mkdir()
shutil.copy2(release / 'kms-acceptance-backend', backend / 'kms-acceptance-backend')
shutil.copytree(backup / 'audit-data', backend / 'audit-data')
shutil.copytree(release / 'dist', gateway / 'dist')
(backend / 'Dockerfile').write_text('''FROM kms-acceptance-backend:before-process-20261019
USER root
COPY --chown=10001:10001 kms-acceptance-backend /app/kms-acceptance-backend
COPY --chown=10001:10001 audit-data/ /app/data/
RUN chmod 755 /app/kms-acceptance-backend
USER kms
''')
# Copy over the previous static tree so cached old modules remain available.
(gateway / 'Dockerfile').write_text('''FROM kms-gateway-nginx:before-process-20261019
COPY dist/ /usr/share/nginx/html/acceptance/
RUN find /usr/share/nginx/html/acceptance -type d -exec chmod 755 {} + \\
    && find /usr/share/nginx/html/acceptance -type f -exec chmod 644 {} +
''')
with (release / 'build.log').open('w') as log:
    for service, directory in [('acceptance-backend', backend), ('nginx', gateway)]:
        subprocess.run(['docker', 'build', '--network=none', '-t', new_images[service], str(directory)], stdout=log, stderr=subprocess.STDOUT, check=True)

original = json.loads(compose_file.read_text())
updated = json.loads(json.dumps(original))
for service in new_images:
    updated['services'][service]['image'] = new_images[service]
# The existing A node setting and every Host/Origin, TLS mount and port stay intact.
assert all(original['services'][s] == updated['services'][s] for s in original['services'] if s not in new_images)
compose = ['docker', 'compose', '-p', project]
for filename in labels['com.docker.compose.project.config_files'].split(','):
    compose += ['-f', filename]


def up():
    with (release / 'compose.log').open('a') as log:
        subprocess.run(compose + ['up', '-d', '--no-deps', '--no-build', 'acceptance-backend', 'nginx'], cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True)


try:
    compose_file.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + '\n')
    subprocess.run(compose + ['config', '--quiet'], cwd=root, check=True)
    up()
    deadline = time.monotonic() + 45
    while True:
        try:
            now = containers()
            if not all(now[name]['State']['Running'] for name in targets):
                raise RuntimeError('target container not running')
            gateway_ip = next(iter(now['kms_gateway']['NetworkSettings']['Networks'].values()))['IPAddress']
            request = urllib.request.Request('http://' + gateway_ip + ':8088/acceptance/', headers={'Host': '127.0.0.1:8088'})
            with urllib.request.urlopen(request, timeout=3) as response:
                if response.status != 200:
                    raise RuntimeError('acceptance frontend not ready')
            break
        except Exception:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.5)
    with (release / 'verification.log').open('w') as log:
        subprocess.run(['python3', str(release / 'verify_all.py')], stdout=log, stderr=subprocess.STDOUT, check=True)
    after = containers()
    changed = [name for name, c in before.items() if name not in targets and
               (name not in after or c['Id'] != after[name]['Id'] or c['State']['StartedAt'] != after[name]['State']['StartedAt'])]
    if changed:
        raise RuntimeError('unexpected KMS container changes: ' + ','.join(changed))
    for name in targets:
        old_mounts = sorted((m['Type'], m['Source'], m['Destination'], m.get('RW')) for m in before[name]['Mounts'])
        new_mounts = sorted((m['Type'], m['Source'], m['Destination'], m.get('RW')) for m in after[name]['Mounts'])
        if old_mounts != new_mounts:
            raise RuntimeError('mounted paths changed: ' + name)
    deployed_binary = run('docker', 'exec', 'kms_acceptance_backend', 'sha256sum', '/app/kms-acceptance-backend').split()[0]
    deployed_index = run('docker', 'exec', 'kms_gateway', 'sha256sum', '/usr/share/nginx/html/acceptance/index.html').split()[0]
    assert deployed_binary == manifest['sha256']['kms-acceptance-backend']
    assert deployed_index == manifest['sha256']['dist/index.html']
    result = {'deployed': True, 'node': 'A', 'cases': manifest['cases'], 'targets': [3, 3, 5], 'coverage': [4, 4, 6],
              'containers': {name: after[name]['Id'][:12] for name in targets},
              'otherKmsContainersUnchanged': len(before) - len(targets), 'staticMountsPreserved': True,
              'binarySha256': deployed_binary, 'indexSha256': deployed_index}
    (release / 'deployment-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
except Exception:
    shutil.copy2(backup / 'docker-compose.yml', compose_file)
    up()
    print('DEPLOYMENT_FAILED_ROLLED_BACK', flush=True)
    raise
