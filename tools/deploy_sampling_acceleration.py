"""Run on expert-machine: stage the bounded patch, then deploy its two images."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


HERE = Path(__file__).resolve().parent
TAG = 'sampling-acceleration-20261023'
REPOS = {'dvadmin3-django': 'kms-dvadmin3-django', 'kms_gateway': 'kms-gateway-nginx'}


def run(args, log=None, timeout=120):
    result = subprocess.run(args, cwd=HERE, capture_output=True, timeout=timeout)
    if log:
        (HERE / log).write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError('Command failed; see ' + str(log or args[0]))
    return result.stdout


def snapshot():
    ids = run(['docker', 'ps', '-aq']).decode().split()
    return {row['Name'].lstrip('/'): row for row in json.loads(run(['docker', 'inspect', *ids]))}


def signature(row):
    return dict(mounts=sorted((m['Type'], m['Source'], m['Destination'], m.get('RW')) for m in row['Mounts']),
        ports=row['HostConfig']['PortBindings'], env=sorted(row['Config']['Env']),
        entrypoint=row['Config']['Entrypoint'], cmd=row['Config']['Cmd'], user=row['Config']['User'])


def verify_bundle():
    manifest = json.loads((HERE / 'manifest.json').read_text())
    for name, digest in manifest.items():
        assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() == digest, name


def expected_before():
    current = snapshot()
    expected = json.loads((HERE / 'preflight-images.json').read_text())
    for name in REPOS:
        assert current[name]['Image'] == expected[name], 'Live baseline changed: ' + name
    return current


def stage():
    before = expected_before()
    images = {}
    for name, repo in REPOS.items():
        base = repo + ':before-' + TAG
        run(['docker', 'tag', before[name]['Image'], base])
        if name == 'dvadmin3-django':
            steps = 'COPY pqkds/ /backend/pqkds/\n'
        else:
            steps = ('RUN rm -f /usr/share/nginx/html/acceptance/index.html.gz\n'
                'COPY dist/ /usr/share/nginx/html/acceptance/\n'
                'RUN find /usr/share/nginx/html/acceptance -type d -exec chmod 755 {} + && '
                'find /usr/share/nginx/html/acceptance -type f -exec chmod 644 {} +\n')
        dockerfile = HERE / ('Dockerfile.' + name)
        dockerfile.write_text('FROM ' + base + '\n' + steps)
        images[name] = repo + ':' + TAG
        run(['docker', 'build', '--network=none', '--pull=false', '-f', str(dockerfile),
            '-t', images[name], str(HERE)], name + '-build.log', 180)
    run(['docker', 'run', '--rm', '--network', 'none', '--entrypoint', 'python',
        images['dvadmin3-django'], '-m', 'unittest', 'pqkds.test_lattice_preallocation_math', '-v'], 'math-tests.log')
    fd, envfile = tempfile.mkstemp(dir=HERE, prefix='staging-env-')
    os.chmod(envfile, 0o600)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write('\n'.join(before['dvadmin3-django']['Config']['Env']) + '\n')
        network = next(iter(before['dvadmin3-django']['NetworkSettings']['Networks']))
        # -c keeps the test driver's Django/DB setup out of spawned children.
        code = "exec(compile(open('/tmp/verify_sampling_django.py').read(), '/tmp/verify_sampling_django.py', 'exec'))"
        run(['docker', 'run', '--rm', '--network', network, '--env-file', envfile,
            '-v', str(HERE / 'verify_sampling_django.py') + ':/tmp/verify_sampling_django.py:ro',
            '--entrypoint', 'python', images['dvadmin3-django'], '-c', code], 'django-tests.log')
    finally:
        os.unlink(envfile)
    (HERE / 'staging-result.json').write_text(json.dumps(dict(verified=True, images=images,
        scope='math tests, real Kyber/SM4 recovery, Falcon ingress, proof validation and rollback-only MySQL data'), indent=2))
    print('STAGING_VERIFIED', flush=True)


def write_atomic(path, raw):
    temp = path.with_name(path.name + '.sampling.tmp')
    with temp.open('xb') as stream:
        os.chmod(temp, 0o600)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def deploy():
    before = expected_before()
    staged = json.loads((HERE / 'staging-result.json').read_text())
    assert staged['verified']
    labels = before['kms_gateway']['Config']['Labels']
    compose = ['docker', 'compose', '-p', labels['com.docker.compose.project']]
    files = labels['com.docker.compose.project.config_files'].split(',')
    for name in files:
        compose += ['-f', name]
    path = Path(files[0])
    original = path.read_bytes()
    baseline = json.loads(run(compose + ['config', '--format', 'json']))
    backup = HERE / 'backup'
    backup.mkdir(exist_ok=False)
    (backup / 'compose.original').write_bytes(original)
    (backup / 'signatures.json').write_text(json.dumps({n: signature(before[n]) for n in REPOS}))
    services = []
    for name, image in staged['images'].items():
        service = before[name]['Config']['Labels']['com.docker.compose.service']
        baseline['services'][service]['image'] = image
        services.append(service)

    def up():
        run(compose + ['up', '-d', '--no-deps', '--no-build', '--pull', 'never', *services], 'compose.log', 180)

    try:
        write_atomic(path, (json.dumps(baseline, indent=2) + '\n').encode())
        configured = json.loads(run(compose + ['config', '--format', 'json']))
        for name, image in staged['images'].items():
            service = before[name]['Config']['Labels']['com.docker.compose.service']
            assert configured['services'][service]['image'] == image
        up()
        run(['docker', 'exec', 'kms_gateway', 'nginx', '-t'], 'nginx-test.log')
        after = snapshot()
        for name in REPOS:
            assert signature(before[name]) == signature(after[name]), 'Runtime signature changed: ' + name
        unrelated = [name for name in before if name not in REPOS]
        assert all(before[n]['Id'] == after[n]['Id'] and before[n]['Image'] == after[n]['Image'] for n in unrelated)
        result = dict(deployed=True, images=staged['images'], backup=str(backup),
            unchangedContainers=len(unrelated), noSchemaChanges=True, runtimeSettingsPreserved=True)
        (HERE / 'deployment-result.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result), flush=True)
    except BaseException:
        write_atomic(path, original)
        up()
        raise


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('stage', 'deploy'))
    args = parser.parse_args()
    verify_bundle()
    (stage if args.action == 'stage' else deploy)()
