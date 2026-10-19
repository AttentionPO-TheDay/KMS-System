"""Publish the final result-note color correction to the gateway only."""
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
backup = release / 'ui-backup'
image = 'kms-gateway-nginx:layout-20261019'


def run(*args):
    return subprocess.check_output(args, text=True)


def snapshot():
    ids = run('docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project=kms-ops').split()
    return {c['Name'].lstrip('/'): c for c in json.loads(run('docker', 'inspect', *ids))}


before = snapshot()
gateway = before['kms_gateway']
labels = gateway['Config']['Labels']
assert labels['com.docker.compose.project.working_dir'] == str(root)
assert gateway['Config']['Image'] == 'kms-gateway-nginx:process-ui-20261019'
manifest = json.loads((release / 'ui-manifest.json').read_text())
for name, expected in manifest.items():
    assert hashlib.sha256((release / name).read_bytes()).hexdigest() == expected, name
backup.mkdir(mode=0o700)
compose_file = root / 'docker-compose.yml'
shutil.copy2(compose_file, backup / 'docker-compose.yml')
os.chmod(backup / 'docker-compose.yml', 0o600)
work = release / 'ui-image'
work.mkdir()
shutil.copytree(release / 'ui-dist', work / 'dist')
(work / 'Dockerfile').write_text('''FROM kms-gateway-nginx:process-ui-20261019
COPY dist/ /usr/share/nginx/html/acceptance/
RUN find /usr/share/nginx/html/acceptance -type d -exec chmod 755 {} + \\
    && find /usr/share/nginx/html/acceptance -type f -exec chmod 644 {} +
''')
with (release / 'ui-build.log').open('w') as log:
    subprocess.run(['docker', 'build', '--network=none', '-t', image, str(work)], stdout=log, stderr=subprocess.STDOUT, check=True)
compose = ['docker', 'compose', '-p', 'kms-ops']
for filename in labels['com.docker.compose.project.config_files'].split(','):
    compose += ['-f', filename]


def up():
    with (release / 'ui-compose.log').open('a') as log:
        subprocess.run(compose + ['up', '-d', '--no-deps', '--no-build', 'nginx'], cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True)


try:
    updated = json.loads(compose_file.read_text())
    updated['services']['nginx']['image'] = image
    compose_file.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + '\n')
    subprocess.run(compose + ['config', '--quiet'], cwd=root, check=True)
    up()
    deadline = time.monotonic() + 30
    while True:
        try:
            run('docker', 'exec', 'kms_gateway', 'nginx', '-t')
            break
        except subprocess.CalledProcessError:
            if time.monotonic() > deadline:
                raise RuntimeError('gateway startup timeout')
            time.sleep(0.5)
    after = snapshot()
    assert all(before[n]['Id'] == after[n]['Id'] and before[n]['State']['StartedAt'] == after[n]['State']['StartedAt'] for n in before if n != 'kms_gateway')
    mounts = lambda c: sorted((m['Type'], m['Source'], m['Destination'], m.get('RW')) for m in c['Mounts'])
    assert mounts(gateway) == mounts(after['kms_gateway'])
    actual = run('docker', 'exec', 'kms_gateway', 'sha256sum', '/usr/share/nginx/html/acceptance/index.html').split()[0]
    assert actual == manifest['ui-dist/index.html']
    result = {'deployed': True, 'image': image, 'otherContainersUnchanged': len(before) - 1, 'mountsPreserved': True, 'indexSha256': actual}
    (release / 'ui-deployment-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
except Exception:
    shutil.copy2(backup / 'docker-compose.yml', compose_file)
    up()
    raise
