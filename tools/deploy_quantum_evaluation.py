"""Incremental release on 10.112.125.22; preserve current stack and audit data."""
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
TAG = 'quantum-evaluation-20261022'
TARGETS = {'acceptance-backend': 'kms_acceptance_backend', 'nginx': 'kms_gateway'}
REPOS = {'acceptance-backend': 'kms-acceptance-backend', 'nginx': 'kms-gateway-nginx'}
IMAGES = {svc: repo+':'+TAG for svc, repo in REPOS.items()}
QUANTUM_IMAGE = 'kms-quantum-evaluator:'+TAG
ENV_NAME = 'ACCEPTANCE_QUANTUM_URL'
ENDPOINT = 'http://quantum-evaluator:8800/evaluate'


def run(args, *, timeout=120, log=None):
    p = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=timeout)
    if log:
        (HERE/log).write_bytes(p.stdout+p.stderr)
    if p.returncode:
        raise RuntimeError('COMMAND_FAILED '+' '.join(args[:3])+'; see release log')
    return p.stdout


def snapshot():
    ids = run(['docker', 'ps', '-aq']).decode().split()
    return {c['Name'].lstrip('/'): c for c in json.loads(run(['docker', 'inspect', *ids]))}


def signature(c):
    return dict(mounts=sorted((m['Type'], m['Source'], m['Destination'], m.get('RW')) for m in c['Mounts']),
        ports=c['HostConfig']['PortBindings'], env=sorted(c['Config']['Env']), entrypoint=c['Config']['Entrypoint'],
        cmd=c['Config']['Cmd'], restart=c['HostConfig']['RestartPolicy'], user=c['Config']['User'])


def atomic_write(path, data):
    temporary = path.with_name(path.name+'.'+TAG+'.tmp')
    with temporary.open('xb') as f:
        os.chmod(temporary, 0o600)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary, path)


def main():
    os.umask(0o077)
    manifest = json.loads((HERE/'manifest.json').read_text())
    for name, digest in manifest['sha256'].items():
        h = hashlib.sha256()
        with (HERE/name).open('rb') as f:
            for block in iter(lambda: f.read(4<<20), b''):
                h.update(block)
        assert h.hexdigest() == digest, name
    before = snapshot()
    assert 'kms_quantum_evaluator' not in before, 'ALREADY_DEPLOYED'
    bases = json.loads((HERE/'preflight-images.json').read_text())
    for name in TARGETS.values():
        assert before[name]['Image'] == bases[name], 'BASE_IMAGE_CHANGED '+name
    processes = run(['docker', 'top', 'kms_acceptance_backend', '-eo', 'pid,comm']).decode().splitlines()
    assert not any('wrk' in p or 'security_test' in p for p in processes), 'ACCEPTANCE_TASK_RUNNING'
    labels = before['kms_gateway']['Config']['Labels']
    assert labels['com.docker.compose.project.working_dir'] == str(ROOT)
    compose = ['docker', 'compose', '-p', labels['com.docker.compose.project']]
    for name in labels['com.docker.compose.project.config_files'].split(','):
        compose.extend(['-f', name])
    compose.extend(['--profile', 'fabric-did'])
    compose_file = ROOT/'docker-compose.yml'
    original = compose_file.read_bytes()
    baseline = json.loads(original)
    assert 'quantum-evaluator' not in baseline['services'], 'SERVICE_ALREADY_EXISTS'
    backup = HERE/'backup'
    backup.mkdir(mode=0o700)
    (backup/'docker-compose.yml').write_bytes(original)
    (backup/'runtime-signatures.json').write_text(json.dumps({n: signature(before[n]) for n in TARGETS.values()}))
    run(['docker', 'cp', 'kms_acceptance_backend:/app/data', str(backup/'audit-data')])

    run(['docker', 'load', '-i', str(HERE/'quantum-image.tar.gz')], timeout=900, log='image-load.log')
    expected = json.loads((HERE/'quantum-image.json').read_text())['imageId']
    assert run(['docker', 'image', 'inspect', 'kms-quantum-evaluator:local', '--format', '{{.Id}}']).decode().strip() == expected
    run(['docker', 'tag', expected, QUANTUM_IMAGE])
    print('QUANTUM_IMAGE_READY', flush=True)
    (HERE/'.dockerignore').write_text('*\n!runtime/\n!runtime/**\n!audit-data/\n!audit-data/**\n!dist/\n!dist/**\n!Dockerfile.*\n')

    for svc, name in TARGETS.items():
        base = REPOS[svc]+':before-'+TAG
        run(['docker', 'image', 'tag', before[name]['Image'], base])
        if svc == 'acceptance-backend':
            shutil.copytree(backup/'audit-data', HERE/'audit-data')
            steps = ('USER root\nCOPY --chown=10001:10001 runtime/kms-acceptance-backend /app/kms-acceptance-backend\n'
                'COPY --chown=10001:10001 audit-data/ /app/data/\nRUN chmod 755 /app/kms-acceptance-backend\nUSER kms\n')
        else:
            steps = ('RUN rm -f /usr/share/nginx/html/acceptance/index.html.gz\n'
                'COPY dist/ /usr/share/nginx/html/acceptance/\n'
                'RUN find /usr/share/nginx/html/acceptance -type d -exec chmod 755 {} + '
                '&& find /usr/share/nginx/html/acceptance -type f -exec chmod 644 {} +\n')
        dockerfile = HERE/('Dockerfile.'+svc)
        dockerfile.write_text('FROM '+base+'\n'+steps)
        run(['docker', 'build', '--network=none', '--pull=false', '-f', str(dockerfile), '-t', IMAGES[svc], str(HERE)],
            timeout=180, log=svc+'-build.log')
        print('IMAGE_READY '+svc, flush=True)

    updated = json.loads(json.dumps(baseline))
    for svc, image in IMAGES.items():
        updated['services'][svc]['image'] = image
    env = updated['services']['acceptance-backend']['environment']
    if isinstance(env, list):
        env[:] = [v for v in env if not v.startswith(ENV_NAME+'=')]
        env.append(ENV_NAME+'='+ENDPOINT)
    else:
        env[ENV_NAME] = ENDPOINT
    # Reuse the token already loaded in the running acceptance service; never print it.
    current_env = dict(v.split('=', 1) for v in before['kms_acceptance_backend']['Config']['Env'] if '=' in v)
    token = current_env.get('ACCEPTANCE_INTERNAL_TOKEN', current_env.get('INTERNAL_TOKEN', ''))
    assert len(token) >= 16, 'INTERNAL_TOKEN_NOT_READY'
    updated['services']['quantum-evaluator'] = dict(
        image=QUANTUM_IMAGE, container_name='kms_quantum_evaluator',
        environment={'INTERNAL_TOKEN': token}, networks=baseline['services']['acceptance-backend']['networks'],
        cpus=2, mem_limit='4g', pids_limit=256, security_opt=['no-new-privileges:true'], cap_drop=['ALL'], restart='unless-stopped')
    expected_config = json.loads(json.dumps(updated))
    del expected_config['services']['quantum-evaluator']
    for svc in IMAGES:
        expected_config['services'][svc]['image'] = baseline['services'][svc]['image']
    expected_config['services']['acceptance-backend']['environment'] = baseline['services']['acceptance-backend']['environment']
    assert expected_config == baseline, 'UNEXPECTED_CONFIGURATION_CHANGE'

    def up(services):
        run(compose+['up', '-d', '--no-deps', '--no-build', '--pull', 'never', *services], timeout=180, log='compose.log')

    try:
        atomic_write(compose_file, (json.dumps(updated, indent=2)+'\n').encode())
        run(compose+['config', '--quiet'])
        up(['quantum-evaluator'])
        # A live HTTP authentication check, without using the private token.
        check_code = "import urllib.request,urllib.error;\ntry: urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8800/evaluate',b'{}'))\nexcept urllib.error.HTTPError as e: assert e.code==403; print('AUTH_REJECTION_OK')"
        for attempt in range(30):
            try:
                assert b'AUTH_REJECTION_OK' in run(['docker', 'exec', 'kms_quantum_evaluator', 'sage', '-python', '-c', check_code], timeout=15, log='readiness.log')
                break
            except (RuntimeError, subprocess.TimeoutExpired, AssertionError):
                if attempt == 29:
                    raise
                time.sleep(1)
        up(list(IMAGES))
        print('SERVICES_RECREATED', flush=True)
        run(['docker', 'exec', 'kms_gateway', 'nginx', '-t'], log='nginx-check.log')
        after = snapshot()
        for svc, name in TARGETS.items():
            old, new = signature(before[name]), signature(after[name])
            if svc == 'acceptance-backend':
                old['env'] = sorted([e for e in old['env'] if not e.startswith(ENV_NAME+'=')]+[ENV_NAME+'='+ENDPOINT])
            assert old == new, 'RUNTIME_CONFIGURATION_CHANGED '+name
            assert after[name]['Image'] == run(['docker', 'image', 'inspect', IMAGES[svc], '--format', '{{.Id}}']).decode().strip()
        untouched = [n for n in before if n not in TARGETS.values()]
        assert all(n in after and before[n]['Id'] == after[n]['Id'] and before[n]['Image'] == after[n]['Image'] for n in untouched)
        q = after['kms_quantum_evaluator']
        assert not q['HostConfig']['PortBindings'] and not q['Mounts']
        assert q['Image'] == expected and q['HostConfig']['Memory'] == 4*2**30
        for name, (path, local) in {'kms_acceptance_backend': ('/app/kms-acceptance-backend', 'runtime/kms-acceptance-backend'),
            'kms_gateway': ('/usr/share/nginx/html/acceptance/index.html', 'dist/index.html')}.items():
            assert run(['docker', 'exec', name, 'sha256sum', path]).decode().split()[0] == manifest['sha256'][local]
        ca = ROOT/'server-access-ip-20261019/tls/server.crt'
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=str(ca))))
        pages = {}
        for path in ['/ping', '/updatedel/demo', '/acceptance/', '/demo-api/lifecycle/demo/context']:
            for attempt in range(30):
                try:
                    with opener.open('https://10.112.125.22:8443'+path, timeout=12) as response:
                        assert response.status == 200
                        pages[path] = response.status
                        break
                except Exception:
                    if attempt == 29:
                        raise
                    time.sleep(1)
        result = dict(deployed=True, images={**IMAGES, 'quantum-evaluator': QUANTUM_IMAGE}, backup=str(backup), https=pages,
            unrelatedContainersSameIdAndImage=len(untouched), mountsPortsExistingEnvPreserved=True,
            evaluatorNoHostPortsOrMounts=True, artifactsVerified=True, schemaMigration=None)
        (HERE/'deployment-result.json').write_text(json.dumps(result, indent=2)+'\n')
        print('DEPLOYMENT_OK '+json.dumps(result), flush=True)
    except Exception:
        atomic_write(compose_file, original)
        up(list(IMAGES))
        run(['docker', 'rm', '-f', 'kms_quantum_evaluator'])
        print('DEPLOYMENT_ROLLED_BACK', flush=True)
        raise


if __name__ == '__main__':
    main()
