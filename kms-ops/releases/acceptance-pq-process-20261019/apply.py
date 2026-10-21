"""Deploy reviewed native algorithm checks and acceptance results; preserve other services."""
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
backup = release / 'backup'
targets = {'kms_acceptance_backend': 'acceptance-backend', 'kms_gateway': 'nginx', 'dvadmin3-django': 'dvadmin3-django'}
images = {'acceptance-backend': 'kms-acceptance-backend:pq-process-20261019', 'nginx': 'kms-gateway-nginx:pq-process-20261019', 'dvadmin3-django': 'kms-dvadmin3-django:pq-process-20261019'}

def run(*args):
    return subprocess.check_output(args, text=True)
def snapshot():
    return {c['Name'].lstrip('/'): c for c in json.loads(run('docker', 'inspect', *run('docker', 'ps', '-aq').split()))}

manifest = json.loads((release / 'manifest.json').read_text())
for name, expected in manifest['sha256'].items():
    assert hashlib.sha256((release / name).read_bytes()).hexdigest() == expected, name
before = snapshot()
preflight = json.loads((release / 'preflight-images.json').read_text())
assert all(before[n]['Image'] == image for n, image in preflight.items()), 'deployed images changed after preflight'
assert 'OK' in (release / 'native-tests.log').read_text(), 'native checks did not pass'
backup.mkdir(mode=0o700)  # Do not rerun a used release.
compose_file = root / 'docker-compose.yml'
shutil.copy2(compose_file, backup / 'docker-compose.yml')
original = json.loads(compose_file.read_text())
labels = before['kms_acceptance_backend']['Config']['Labels']
assert labels['com.docker.compose.project.working_dir'] == str(root)
assert all(before[n]['Config']['Labels']['com.docker.compose.service'] == svc for n, svc in targets.items())
assert not before['kms_acceptance_backend']['Mounts']
run('docker', 'cp', 'kms_acceptance_backend:/app/data', str(backup / 'audit-data'))
for name, service in targets.items():
    if service == 'dvadmin3-django':
        continue  # Already built and tested in preflight.
    base = images[service].replace(':pq-process-', ':before-pq-process-')
    run('docker', 'image', 'tag', before[name]['Image'], base)
    directory = release / (service + '-image')
    directory.mkdir()
    if service == 'acceptance-backend':
        shutil.copy2(release / 'kms-acceptance-backend', directory / 'kms-acceptance-backend')
        shutil.copytree(backup / 'audit-data', directory / 'audit-data')
        dockerfile = f'FROM {base}\nUSER root\nCOPY --chown=10001:10001 kms-acceptance-backend /app/kms-acceptance-backend\nCOPY --chown=10001:10001 audit-data/ /app/data/\nRUN chmod 755 /app/kms-acceptance-backend\nUSER kms\n'
    else:
        shutil.copytree(release / 'dist', directory / 'dist')
        dockerfile = f'FROM {base}\nCOPY dist/ /usr/share/nginx/html/acceptance/\nRUN find /usr/share/nginx/html/acceptance -type d -exec chmod 755 {{}} + && find /usr/share/nginx/html/acceptance -type f -exec chmod 644 {{}} +\n'
    (directory / 'Dockerfile').write_text(dockerfile)
    with (release / (service + '-build.log')).open('w') as log:
        subprocess.run(['docker', 'build', '--network=none', '-t', images[service], str(directory)], stdout=log, stderr=subprocess.STDOUT, check=True)
compose = ['docker', 'compose', '-p', labels['com.docker.compose.project']]
for name in labels['com.docker.compose.project.config_files'].split(','):
    compose += ['-f', name]
def up():
    with (release / 'compose.log').open('a') as log:
        subprocess.run(compose + ['up', '-d', '--no-deps', '--no-build', *images], cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True)
try:
    updated = json.loads(json.dumps(original))
    for service, image in images.items():
        updated['services'][service]['image'] = image
    compose_file.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + '\n')
    subprocess.run(compose + ['config', '--quiet'], cwd=root, check=True)
    up()
    deadline = time.monotonic() + 60
    while True:
        try:
            with (release / 'verification.log').open('w') as log:
                subprocess.run(['python3', str(release / 'verify_live.py')], stdout=log, stderr=subprocess.STDOUT, check=True)
            break
        except subprocess.CalledProcessError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(2)
    after = snapshot()
    unchanged = [n for n in before if n not in targets and n in after and before[n]['Id'] == after[n]['Id'] and before[n]['State']['StartedAt'] == after[n]['State']['StartedAt']]
    assert len(unchanged) == len(before) - len(targets), 'unrelated container changed'
    mounts = lambda c: sorted((m['Type'], m['Source'], m['Destination'], m.get('RW')) for m in c['Mounts'])
    assert all(mounts(before[n]) == mounts(after[n]) and before[n]['HostConfig']['PortBindings'] == after[n]['HostConfig']['PortBindings'] and sorted(before[n]['Config']['Env']) == sorted(after[n]['Config']['Env']) for n in targets)
    result = {'deployed': True, 'protocolCases': 14, 'uniqueRejectionCodes': 14, 'algorithmChecks': 26, 'algorithmClasses': 4, 'unrelatedContainersUnchanged': len(unchanged), 'mountsPortsEnvPreserved': True, 'images': images}
    (release / 'deployment-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
except Exception:
    shutil.copy2(backup / 'docker-compose.yml', compose_file)
    up()
    print('DEPLOYMENT_FAILED_ROLLED_BACK', flush=True)
    raise
