"""Incremental, backed-up release of three pages and their actual executor."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path('/home/rbf/kms-sys')
HERE = Path(__file__).resolve().parent
TAG = 'lattice-preallocation-20261022-r3'
REPOS = {'dvadmin3-django': 'kms-dvadmin3-django', 'kms_acceptance_backend': 'kms-acceptance-backend', 'kms_gateway': 'kms-gateway-nginx'}
if os.environ.get('LATTICE_FRONTEND_ONLY') == '1':
    REPOS = {'kms_gateway': REPOS['kms_gateway']}


def run(args, log=None, timeout=120):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=timeout)
    if log: (HERE / log).write_bytes(result.stdout + result.stderr)
    if result.returncode: raise RuntimeError('Release command failed; see ' + str(log or 'release log'))
    return result.stdout


def snapshot():
    ids = run(['docker', 'ps', '-aq']).decode().split()
    return {row['Name'].lstrip('/'): row for row in json.loads(run(['docker', 'inspect', *ids]))}


def signature(row):
    return dict(mounts=sorted((m['Type'], m['Source'], m['Destination'], m.get('RW')) for m in row['Mounts']),
        ports=row['HostConfig']['PortBindings'], env=sorted(row['Config']['Env']),
        entrypoint=row['Config']['Entrypoint'], cmd=row['Config']['Cmd'], user=row['Config']['User'])


def atomic_write(path, raw):
    temp = path.with_name(path.name + '.lattice.tmp')
    with temp.open('xb') as stream:
        os.chmod(temp, 0o600); stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    os.replace(temp, path)


def main():
    os.umask(0o077)
    hashes = json.loads((HERE / 'manifest.json').read_text())
    for name, digest in hashes.items(): assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() == digest
    before = snapshot()
    expected = json.loads((HERE / 'preflight-images.json').read_text())
    for name in REPOS: assert before[name]['Image'] == expected[name], 'Live image changed: ' + name
    processes = run(['docker', 'top', 'kms_acceptance_backend', '-eo', 'pid,comm']).decode()
    assert 'wrk' not in processes, 'Acceptance task is running'
    labels = before['kms_gateway']['Config']['Labels']
    compose = ['docker', 'compose', '-p', labels['com.docker.compose.project']]
    compose_files = labels['com.docker.compose.project.config_files'].split(',')
    for name in compose_files: compose += ['-f', name]
    compose_file = Path(compose_files[0])
    original = compose_file.read_bytes()
    baseline = json.loads(run(compose + ['config', '--format', 'json']))
    backup = HERE / 'backup'
    backup.mkdir(exist_ok=False)
    (backup / 'compose.original').write_bytes(original)
    (backup / 'signatures.json').write_text(json.dumps({n: signature(before[n]) for n in REPOS}))
    run(['docker', 'cp', 'kms_acceptance_backend:/app/data', str(backup / 'audit-data')])
    shutil.copytree(backup / 'audit-data', HERE / 'audit-data')
    (HERE / '.dockerignore').write_text('*\n!pqkds/\n!pqkds/**\n!wheels/\n!wheels/**\n!dist/\n!dist/**\n!runtime/\n!runtime/**\n!audit-data/\n!audit-data/**\n!Dockerfile.*\n')
    images = {}
    for name, repo in REPOS.items():
        base = repo + ':before-' + TAG
        run(['docker', 'tag', before[name]['Image'], base])
        if name == 'dvadmin3-django':
            steps = 'COPY pqkds/ /backend/pqkds/\nCOPY wheels/ /tmp/lattice-wheels/\nRUN pip install --no-index --no-deps --find-links /tmp/lattice-wheels threadpoolctl==3.6.0\n'
        elif name == 'kms_acceptance_backend':
            steps = 'USER root\nCOPY --chown=10001:10001 runtime/kms-acceptance-backend /app/kms-acceptance-backend\nCOPY --chown=10001:10001 audit-data/ /app/data/\nRUN chmod 755 /app/kms-acceptance-backend\nUSER kms\n'
        else:
            steps = 'RUN rm -f /usr/share/nginx/html/acceptance/index.html.gz\nCOPY dist/ /usr/share/nginx/html/acceptance/\nRUN find /usr/share/nginx/html/acceptance -type d -exec chmod 755 {} + && find /usr/share/nginx/html/acceptance -type f -exec chmod 644 {} +\n'
        dockerfile = HERE / ('Dockerfile.' + name)
        dockerfile.write_text('FROM ' + base + '\n' + steps)
        images[name] = repo + ':' + TAG
        run(['docker', 'build', '--network=none', '--pull=false', '-f', str(dockerfile), '-t', images[name], str(HERE)], log=name + '-build.log', timeout=180)
        print('IMAGE_READY ' + name, flush=True)
    # Run the additive migration with exactly the live DB environment. Existing
    # backends remain available and tolerate the new nullable FK column.
    if 'dvadmin3-django' in images:
        fd, envfile = tempfile.mkstemp(dir=HERE, prefix='migration-')
        os.chmod(envfile, 0o600)
        try:
            with os.fdopen(fd, 'w') as stream: stream.write('\n'.join(before['dvadmin3-django']['Config']['Env']) + '\n')
            network = next(iter(before['dvadmin3-django']['NetworkSettings']['Networks']))
            run(['docker', 'run', '--rm', '--network', network, '--env-file', envfile,
                 images['dvadmin3-django'], 'python', 'manage.py', 'migrate', 'pqkds', '0041_lattice_preallocation', '--noinput'], log='migration.log', timeout=120)
        finally: os.unlink(envfile)
    updated = json.loads(json.dumps(baseline))
    services = []
    for name, image in images.items():
        service = before[name]['Config']['Labels']['com.docker.compose.service']
        updated['services'][service]['image'] = image
        services.append(service)
    def up(): run(compose + ['up', '-d', '--no-deps', '--no-build', '--pull', 'never', *services], log='compose.log', timeout=180)
    try:
        atomic_write(compose_file, (json.dumps(updated, indent=2) + '\n').encode())
        run(compose + ['config', '--quiet'])
        up()
        run(['docker', 'exec', 'kms_gateway', 'nginx', '-t'], log='nginx.log')
        after = snapshot()
        for name in REPOS:
            assert signature(before[name]) == signature(after[name]), 'Runtime changed: ' + name
        unrelated = [n for n in before if n not in REPOS and n != 'kms_lattice_staging']
        assert all(before[n]['Id'] == after[n]['Id'] and before[n]['Image'] == after[n]['Image'] for n in unrelated)
        result = dict(deployed=True, images=images, backup=str(backup), unrelatedContainersPreserved=len(unrelated),
                      migration='pqkds.0041_lattice_preallocation' if 'dvadmin3-django' in images else None, existingMountsPortsEnvironmentPreserved=True)
        (HERE / 'deployment-result.json').write_text(json.dumps(result, indent=2))
        print('DEPLOYED ' + json.dumps(result), flush=True)
    except Exception:
        atomic_write(compose_file, original)
        up()
        print('Images rolled back; additive nullable column and evidence tables retained.', flush=True)
        raise


if __name__ == '__main__': main()
