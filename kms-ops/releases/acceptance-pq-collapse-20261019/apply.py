"""Publish only the algorithm process disclosure control to the gateway."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

os.umask(0o077)
release = Path(__file__).resolve().parent
root = Path('/home/rbf/kms-sys')
image = 'kms-gateway-nginx:pq-collapse-20261019'
def run(*args):
    return subprocess.check_output(args, text=True)
def snapshot():
    return {c['Name'].lstrip('/'): c for c in json.loads(run('docker', 'inspect', *run('docker', 'ps', '-aq').split()))}

manifest = json.loads((release / 'manifest.json').read_text())
for name, expected in manifest.items():
    assert hashlib.sha256((release / name).read_bytes()).hexdigest() == expected, name
before = snapshot()
gateway = before['kms_gateway']
assert gateway['Config']['Image'] == 'kms-gateway-nginx:pq-process-20261019'
labels = gateway['Config']['Labels']
assert labels['com.docker.compose.project.working_dir'] == str(root)
backup = release / 'backup'
backup.mkdir(mode=0o700)
compose_file = root / 'docker-compose.yml'
shutil.copy2(compose_file, backup / 'docker-compose.yml')
work = release / 'image'
work.mkdir()
shutil.copytree(release / 'dist', work / 'dist')
(work / 'Dockerfile').write_text('FROM kms-gateway-nginx:pq-process-20261019\nCOPY dist/ /usr/share/nginx/html/acceptance/\nRUN find /usr/share/nginx/html/acceptance -type d -exec chmod 755 {} + && find /usr/share/nginx/html/acceptance -type f -exec chmod 644 {} +\n')
with (release / 'build.log').open('w') as log:
    subprocess.run(['docker', 'build', '--network=none', '-t', image, str(work)], stdout=log, stderr=subprocess.STDOUT, check=True)
compose = ['docker', 'compose', '-p', labels['com.docker.compose.project']]
for name in labels['com.docker.compose.project.config_files'].split(','):
    compose += ['-f', name]
def up():
    with (release / 'compose.log').open('a') as log:
        subprocess.run(compose + ['up', '-d', '--no-deps', '--no-build', 'nginx'], cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True)
try:
    updated = json.loads(compose_file.read_text())
    updated['services']['nginx']['image'] = image
    compose_file.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + '\n')
    subprocess.run(compose + ['config', '--quiet'], cwd=root, check=True)
    up()
    for attempt in range(20):
        try:
            run('docker', 'exec', 'kms_gateway', 'nginx', '-t')
            break
        except subprocess.CalledProcessError:
            if attempt == 19:
                raise
            time.sleep(0.5)
    after = snapshot()
    assert all(n in after and before[n]['Id'] == after[n]['Id'] and before[n]['State']['StartedAt'] == after[n]['State']['StartedAt'] for n in before if n != 'kms_gateway')
    mounts = lambda c: sorted((m['Type'], m['Source'], m['Destination'], m.get('RW')) for m in c['Mounts'])
    assert mounts(gateway) == mounts(after['kms_gateway'])
    assert gateway['HostConfig']['PortBindings'] == after['kms_gateway']['HostConfig']['PortBindings']
    assert sorted(gateway['Config']['Env']) == sorted(after['kms_gateway']['Config']['Env'])
    actual = run('docker', 'exec', 'kms_gateway', 'sha256sum', '/usr/share/nginx/html/acceptance/index.html').split()[0]
    assert actual == manifest['dist/index.html']
    result = {'deployed': True, 'image': image, 'otherContainersUnchanged': len(before) - 1, 'mountsPortsEnvPreserved': True}
    (release / 'deployment-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
except Exception:
    shutil.copy2(backup / 'docker-compose.yml', compose_file)
    up()
    raise
