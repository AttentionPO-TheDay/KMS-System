"""Release just the pool upload index fix, with image/config backups and rollback."""
import hashlib
import json
import os
from pathlib import Path
import ssl
import subprocess
import tarfile
import time
import urllib.error
import urllib.request

ROOT = Path('/home/rbf/kms-sys')
HERE = Path(__file__).resolve().parent
TAG = 'pool-chunk-index-20261023'
REPOS = {'dvadmin3-django': 'kms-dvadmin3-django', 'kms_gateway': 'kms-gateway-nginx'}


def run(args, log=None, timeout=120, input=None):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=timeout, input=input)
    if log:
        (HERE / log).write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError('Release command failed; see ' + str(log or args[:3]))
    return result.stdout


def snapshot():
    return {r['Name'].lstrip('/'): r for r in json.loads(run(['docker', 'inspect', *run(['docker', 'ps', '-aq']).decode().split()]))}


def signature(row):
    return dict(mounts=sorted((m['Type'], m['Source'], m['Destination'], m.get('RW')) for m in row['Mounts']),
        ports=row['HostConfig']['PortBindings'], env=sorted(row['Config']['Env']),
        entrypoint=row['Config']['Entrypoint'], cmd=row['Config']['Cmd'], user=row['Config']['User'])


def atomic_write(path, raw):
    temp = path.with_name(path.name + '.pool-index.tmp')
    with temp.open('xb') as stream:
        os.chmod(temp, 0o600)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def main():
    os.umask(0o077)
    manifest = json.loads((HERE / 'manifest.json').read_text())
    for name, digest in manifest.items():
        assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() == digest, name
    before = snapshot()
    expected = json.loads((HERE / 'preflight-images.json').read_text())
    for name in REPOS:
        assert before[name]['Image'] == expected[name], 'Live image changed: ' + name
    labels = before['kms_gateway']['Config']['Labels']
    compose = ['docker', 'compose', '-p', labels['com.docker.compose.project']]
    files = labels['com.docker.compose.project.config_files'].split(',')
    for name in files:
        compose += ['-f', name]
    compose_file = Path(files[0])
    original = compose_file.read_bytes()
    baseline = json.loads(run(compose + ['config', '--format', 'json']))
    backup = HERE / 'backup'
    backup.mkdir(exist_ok=False)
    (backup / 'compose.original').write_bytes(original)
    (backup / 'images.json').write_text(json.dumps({n: before[n]['Config']['Image'] for n in REPOS}, indent=2))
    run(['docker', 'cp', 'dvadmin3-django:/backend/pqkds/node_self_views.py', str(backup / 'node_self_views.py')])
    run(['docker', 'cp', 'kms_gateway:/usr/share/nginx/html/updatedel/index.html', str(backup / 'index.html')])
    dist = HERE / 'dist'
    dist.mkdir(exist_ok=False)
    with tarfile.open(HERE / 'frontend.tar.gz') as archive:
        assert all((dist / m.name).resolve().is_relative_to(dist.resolve()) for m in archive.getmembers())
        archive.extractall(dist)
    (HERE / '.dockerignore').write_text('*\n!pqkds/\n!pqkds/**\n!dist/\n!dist/**\n!Dockerfile.*\n')
    images = {}
    services = []
    for name, repo in REPOS.items():
        base = repo + ':before-' + TAG
        run(['docker', 'tag', before[name]['Image'], base])
        if name == 'dvadmin3-django':
            steps = 'COPY pqkds/node_self_views.py /backend/pqkds/node_self_views.py\n'
        else:
            steps = ('RUN rm -f /usr/share/nginx/html/updatedel/index.html.gz\n'
                     'COPY dist/ /usr/share/nginx/html/updatedel/\n'
                     'RUN find /usr/share/nginx/html/updatedel -type d -exec chmod 755 {} + && '
                     'find /usr/share/nginx/html/updatedel -type f -exec chmod 644 {} +\n')
        dockerfile = HERE / ('Dockerfile.' + name)
        dockerfile.write_text('FROM ' + base + '\n' + steps)
        images[name] = repo + ':' + TAG
        run(['docker', 'build', '--network=none', '--pull=false', '-f', str(dockerfile), '-t', images[name], str(HERE)],
            log=name + '-build.log', timeout=180)
        services.append(before[name]['Config']['Labels']['com.docker.compose.service'])
        print('IMAGE_READY ' + name, flush=True)
    updated = json.loads(json.dumps(baseline))
    for name, image in images.items():
        updated['services'][before[name]['Config']['Labels']['com.docker.compose.service']]['image'] = image
    expected_config = json.loads(json.dumps(updated))
    for name in REPOS:
        service = before[name]['Config']['Labels']['com.docker.compose.service']
        expected_config['services'][service]['image'] = baseline['services'][service]['image']
    assert expected_config == baseline, 'Unexpected compose change'

    def up(log):
        run(compose + ['up', '-d', '--no-deps', '--no-build', '--pull', 'never', *services], log=log, timeout=180)

    try:
        atomic_write(compose_file, (json.dumps(updated, indent=2) + '\n').encode())
        run(compose + ['config', '--quiet'])
        up('compose.log')
        run(['docker', 'exec', 'kms_gateway', 'nginx', '-t'], log='nginx.log')
        after = snapshot()
        for name in REPOS:
            assert signature(before[name]) == signature(after[name]), 'Runtime configuration changed: ' + name
            assert after[name]['Config']['Image'] == images[name]
        unrelated = [n for n in before if n not in REPOS]
        assert all(before[n]['Id'] == after[n]['Id'] and before[n]['Image'] == after[n]['Image'] for n in unrelated)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
        for path, expected_status in [('/updatedel/demo', 200), ('/acceptance/', 200),
                                      ('/demo-api/pqkds/node-self/pool/summary/', 401)]:
            last = None
            for _ in range(20):
                try:
                    request = urllib.request.Request('https://10.112.125.22:8443' + path)
                    try:
                        response = opener.open(request, timeout=10)
                    except urllib.error.HTTPError as exc:
                        response = exc
                    with response:
                        assert response.status == expected_status
                        response.read()
                    last = None
                    break
                except Exception as exc:
                    last = exc
                    time.sleep(2)
            if last:
                raise last
        # This test uses real production crypto and MySQL constraints. Its outer
        # transaction rolls back its temporary nodes, keys, pools and audit rows.
        verify = (HERE / 'verify_pool_chunk_release.py').read_bytes()
        run(['docker', 'exec', '-i', 'dvadmin3-django', 'python', 'manage.py', 'shell'],
            input=verify, log='live-verification.log', timeout=180)
        result = dict(deployed=True, images=images, backup=str(backup),
            unrelatedContainersPreserved=len(unrelated), databaseMigrationRequired=False,
            existingMountsPortsEnvironmentPreserved=True, productionMySQLCryptoVerification=True)
        (HERE / 'deployment-result.json').write_text(json.dumps(result, indent=2))
        print('DEPLOYED ' + json.dumps(result), flush=True)
    except Exception:
        atomic_write(compose_file, original)
        up('rollback-compose.log')
        print('ROLLED_BACK to original images and compose configuration', flush=True)
        raise


if __name__ == '__main__':
    main()
