"""Publish service-side rejection codes plus verified acceptance evidence."""
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
images = {'acceptance-backend': 'kms-acceptance-backend:evidence-20261019', 'nginx': 'kms-gateway-nginx:evidence-20261019', 'dvadmin3-django': 'kms-dvadmin3-django:evidence-20261019'}

def run(*args):
    return subprocess.check_output(args, text=True)

def snapshot():
    ids = run('docker', 'ps', '-aq').split()
    return {c['Name'].lstrip('/'): c for c in json.loads(run('docker', 'inspect', *ids))}

manifest = json.loads((release / 'manifest.json').read_text())
for name, expected in manifest['sha256'].items():
    assert hashlib.sha256((release / name).read_bytes()).hexdigest() == expected, name
before = snapshot()
labels = before['kms_acceptance_backend']['Config']['Labels']
assert labels['com.docker.compose.project.working_dir'] == str(root)
assert all(before[n]['Config']['Labels']['com.docker.compose.service'] == service for n, service in targets.items())
# Refuse to overwrite server-only source changes. Check only bounded public code hashes.
check = "import hashlib,json; from pathlib import Path; names=" + repr(list(manifest['djangoBaselines'])) + "; print(json.dumps({n:hashlib.sha256((Path('/backend')/n).read_bytes().replace(b'\\r\\n',b'\\n')).hexdigest() for n in names}))"
assert json.loads(run('docker', 'exec', 'dvadmin3-django', 'python', '-B', '-c', check)) == manifest['djangoBaselines'], 'server source differs from reviewed baseline'
backup.mkdir(mode=0o700)
compose_file = root / 'docker-compose.yml'
shutil.copy2(compose_file, backup / 'docker-compose.yml')
original = json.loads(compose_file.read_text())
assert not before['kms_acceptance_backend']['Mounts'], 'review audit mounts first'
run('docker', 'cp', 'kms_acceptance_backend:/app/data', str(backup / 'audit-data'))
for name, service in targets.items():
    run('docker', 'image', 'tag', before[name]['Image'], images[service].replace(':evidence-', ':before-evidence-'))

for service, image in images.items():
    directory = release / (service + '-image')
    directory.mkdir()
    base = image.replace(':evidence-', ':before-evidence-')
    if service == 'acceptance-backend':
        shutil.copy2(release / 'kms-acceptance-backend', directory / 'kms-acceptance-backend')
        shutil.copytree(backup / 'audit-data', directory / 'audit-data')
        dockerfile = f'FROM {base}\nUSER root\nCOPY --chown=10001:10001 kms-acceptance-backend /app/kms-acceptance-backend\nCOPY --chown=10001:10001 audit-data/ /app/data/\nRUN chmod 755 /app/kms-acceptance-backend\nUSER kms\n'
    elif service == 'nginx':
        shutil.copytree(release / 'dist', directory / 'dist')
        dockerfile = f'FROM {base}\nCOPY dist/ /usr/share/nginx/html/acceptance/\nRUN find /usr/share/nginx/html/acceptance -type d -exec chmod 755 {{}} + && find /usr/share/nginx/html/acceptance -type f -exec chmod 644 {{}} +\n'
    else:
        shutil.copytree(release / 'django', directory / 'django')
        dockerfile = f'FROM {base}\nCOPY django/ /backend/\n'
    (directory / 'Dockerfile').write_text(dockerfile)
    with (release / (service + '-build.log')).open('w') as log:
        subprocess.run(['docker', 'build', '--network=none', '-t', image, str(directory)], stdout=log, stderr=subprocess.STDOUT, check=True)

# Uses only fresh :memory: SQLite, no production settings/env/mounts/network.
with (release / 'django-offline-test.log').open('w') as log:
    subprocess.run(['docker', 'run', '--rm', '--network=none', '--entrypoint', 'python', images['dvadmin3-django'], '-B', 'tests/test_split_keygen_offline.py'], stdout=log, stderr=subprocess.STDOUT, check=True)

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
            subprocess.run(['python3', str(release / 'verify_all.py')], stdout=(release / 'verification.log').open('w'), stderr=subprocess.STDOUT, check=True)
            break
        except subprocess.CalledProcessError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(2)
    after = snapshot()
    # Pre-existing crash-loop containers may auto-restart independently. They
    # must retain their ID/image/config and show an increased Docker restart count.
    auto_restarted = [n for n, c in before.items() if n not in targets and n in after
                      and c['Id'] == after[n]['Id'] and c['Config'] == after[n]['Config']
                      and c['State']['StartedAt'] != after[n]['State']['StartedAt']
                      and c['RestartCount'] > 1 and after[n]['RestartCount'] > c['RestartCount']
                      and c['HostConfig']['RestartPolicy']['Name'] != 'no']
    changed = [n for n, c in before.items() if n not in targets and n not in auto_restarted and (n not in after or c['Id'] != after[n]['Id'] or c['State']['StartedAt'] != after[n]['State']['StartedAt'])]
    assert not changed, 'unrelated container changed: ' + ', '.join(changed)
    mounts = lambda c: sorted((m['Type'], m['Source'], m['Destination'], m.get('RW')) for m in c['Mounts'])
    assert all(mounts(before[n]) == mounts(after[n]) and before[n]['HostConfig']['PortBindings'] == after[n]['HostConfig']['PortBindings'] for n in targets)
    for n in targets:
        assert sorted(before[n]['Config']['Env']) == sorted(after[n]['Config']['Env']), 'environment changed: ' + n
    result = {'deployed': True, 'protocolScenariosPassed': 14, 'uniqueActualCodes': 14, 'quantumAlgorithmAcceptance': 'pending', 'unrelatedContainersUnchanged': len(before) - len(targets) - len(auto_restarted), 'preexistingAutomaticRestarts': auto_restarted, 'unrelatedContainersRecreated': 0, 'mountsPortsEnvPreserved': True, 'images': images}
    (release / 'deployment-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
except Exception:
    shutil.copy2(backup / 'docker-compose.yml', compose_file)
    up()
    print('DEPLOYMENT_FAILED_ROLLED_BACK', flush=True)
    raise
