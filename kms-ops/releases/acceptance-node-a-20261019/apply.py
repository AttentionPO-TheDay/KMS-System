#!/usr/bin/env python3
"""Deploy only the acceptance backend; retain its old image, config and audit data."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

os.umask(0o077)
release = Path(__file__).resolve().parent
root = Path('/home/rbf/kms-sys')
backup = release / 'backup'
service = 'kms_acceptance_backend'
new_image = 'kms-acceptance-backend:node-a-20261019'
old_tag = 'kms-acceptance-backend:before-node-a-20261019'


def run(*args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs)


def containers():
    ids = run('docker', 'ps', '-aq').split()
    return {c['Name']: c for c in json.loads(run('docker', 'inspect', *ids))}


before = containers()
current = before['/' + service]
labels = current['Config']['Labels']
before = {name: c for name, c in before.items()
          if c['Config'].get('Labels', {}).get('com.docker.compose.project') == labels['com.docker.compose.project']}
if labels.get('com.docker.compose.project.working_dir') != str(root):
    raise RuntimeError('unexpected compose working directory')
if current['Mounts']:
    raise RuntimeError('review new acceptance mounts before deploying')
manifest = json.loads((release / 'manifest.json').read_text())
binary = release / 'kms-acceptance-backend'
if hashlib.sha256(binary.read_bytes()).hexdigest() != manifest['binarySha256']:
    raise RuntimeError('binary digest mismatch')
compose_path = root / 'docker-compose.yml'
snapshot = {name: {'id': c['Id'], 'startedAt': c['State']['StartedAt'], 'image': c['Config']['Image']} for name, c in before.items()}
if backup.exists():
    if sys.argv[1:] != ['--resume']:
        raise RuntimeError('existing backup: explicit verified resume required')
    original = json.loads((backup / 'containers.json').read_text())
    project_original = {name: original.get(name) for name in before}
    if project_original.get('/' + service) != snapshot['/' + service]:
        old_image_id = json.loads(run('docker', 'image', 'inspect', old_tag))[0]['Id']
        if current['Image'] != old_image_id:
            raise RuntimeError('acceptance is not running the rollback image')
        project_original['/' + service] = snapshot['/' + service]
    if project_original != snapshot or compose_path.read_bytes() != (backup / 'docker-compose.yml').read_bytes():
        raise RuntimeError('baseline changed; refusing to replace original backup')
else:
    backup.mkdir(mode=0o700)
    shutil.copy2(compose_path, backup / 'docker-compose.yml')
    os.chmod(backup / 'docker-compose.yml', 0o600)
    (backup / 'containers.json').write_text(json.dumps(snapshot, indent=2) + '\n')
    run('docker', 'image', 'tag', current['Image'], old_tag)
    run('docker', 'cp', service + ':/app/data', str(backup / 'data'))
dockerfile = '''FROM kms-acceptance-backend:before-node-a-20261019
USER root
COPY --chown=10001:10001 kms-acceptance-backend /app/kms-acceptance-backend
COPY --chown=10001:10001 backup/data/ /app/data/
RUN chmod 755 /app/kms-acceptance-backend
USER kms
'''
(release / 'Dockerfile').write_text(dockerfile)
with (release / 'build.log').open('w') as log:
    subprocess.run(['docker', 'build', '--network=none', '-t', new_image, str(release)], stdout=log, stderr=subprocess.STDOUT, check=True)
text = compose_path.read_text()
if text.lstrip().startswith('{'):
    config = json.loads(text)
    target = config['services']['acceptance-backend']
    target['image'] = new_image
    environment = target.setdefault('environment', {})
    if not isinstance(environment, dict):
        raise RuntimeError('unexpected JSON compose environment type')
    environment['ACCEPTANCE_SECURITY_NODE_ID'] = '${ACCEPTANCE_SECURITY_NODE_ID:-A}'
    text = json.dumps(config, ensure_ascii=False, indent=2) + '\n'
else:
    match = re.search(r'(?ms)^  acceptance-backend:\n.*?(?=^  [A-Za-z0-9_-]+:|\Z)', text)
    if not match:
        raise RuntimeError('acceptance service block not found')
    block = match.group()
    block, count = re.subn(r'(?m)^    image:.*$', '    image: ' + new_image, block)
    if count != 1:
        raise RuntimeError('unexpected acceptance image count')
    if 'ACCEPTANCE_SECURITY_NODE_ID=' in block:
        block = re.sub(r'(?m)^      - ACCEPTANCE_SECURITY_NODE_ID=.*$', '      - ACCEPTANCE_SECURITY_NODE_ID=${ACCEPTANCE_SECURITY_NODE_ID:-A}', block)
    else:
        if '    environment:\n' not in block:
            raise RuntimeError('acceptance environment block not found')
        block = block.replace('    environment:\n', '    environment:\n      - ACCEPTANCE_SECURITY_NODE_ID=${ACCEPTANCE_SECURITY_NODE_ID:-A}\n', 1)
    text = text[:match.start()] + block + text[match.end():]
compose = ['docker', 'compose', '-p', labels['com.docker.compose.project']]
for filename in labels['com.docker.compose.project.config_files'].split(','):
    compose += ['-f', filename]


def up():
    with (release / 'compose.log').open('a') as log:
        subprocess.run(compose + ['up', '-d', '--no-deps', '--no-build', 'acceptance-backend'], cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True)


try:
    compose_path.write_text(text)
    subprocess.run(compose + ['config', '--quiet'], cwd=root, check=True)
    up()
    deadline = time.monotonic() + 40
    while True:
        try:
            c = containers()['/' + service]
            ip = next(iter(c['NetworkSettings']['Networks'].values()))['IPAddress']
            with urllib.request.urlopen('http://' + ip + ':9090/api/health', timeout=3) as response:
                if response.status == 200:
                    break
        except urllib.error.HTTPError as error:
            # Direct requests deliberately lack the trusted Demo gateway header.
            if error.code == 404 and json.load(error).get('message') == '受控 Demo 网关必需':
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('unexpected acceptance readiness response')
            time.sleep(0.5)
        except Exception:
            if time.monotonic() >= deadline:
                raise RuntimeError('acceptance backend did not become healthy')
            time.sleep(0.5)
    if (release / 'verification.log').exists():
        shutil.copy2(release / 'verification.log', release / ('verification-before-retry-' + str(time.time_ns()) + '.log'))
    with (release / 'verification.log').open('w') as log:
        subprocess.run(['python3', str(release / 'verify.py')], stdout=log, stderr=subprocess.STDOUT, check=True)
    after = containers()
    changed = [name for name, c in before.items() if name != '/' + service and
               (name not in after or c['Id'] != after[name]['Id'] or c['State']['StartedAt'] != after[name]['State']['StartedAt'])]
    if changed:
        raise RuntimeError('unrelated containers changed: ' + ','.join(changed))
    deployed = after['/' + service]
    env = dict(v.split('=', 1) for v in deployed['Config']['Env'] if '=' in v)
    if env.get('ACCEPTANCE_SECURITY_NODE_ID') != 'A':
        raise RuntimeError('deployed node configuration is not A')
    result = {'deployed': True, 'node': 'A', 'image': new_image, 'binarySha256': manifest['binarySha256'],
              'previousContainer': current['Id'][:12], 'newContainer': deployed['Id'][:12],
              'unrelatedContainersUnchanged': len(before) - 1, 'threeGenerationProbesPassed': True}
    (release / 'deployment-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
except Exception:
    shutil.copy2(backup / 'docker-compose.yml', compose_path)
    up()
    print('DEPLOYMENT_FAILED_ROLLED_BACK', flush=True)
    raise
