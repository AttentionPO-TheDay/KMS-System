"""Build and test native payload offline BEFORE touching any deployed container."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

release = Path(__file__).resolve().parent
def run(*args):
    return subprocess.check_output(args, text=True)
manifest = json.loads((release / 'manifest.json').read_text())
for name, expected in manifest['sha256'].items():
    assert hashlib.sha256((release / name).read_bytes()).hexdigest() == expected, name
names = ['dvadmin3-django', 'kms_acceptance_backend', 'kms_gateway']
before = {c['Name'].lstrip('/'): c['Image'] for c in json.loads(run('docker', 'inspect', *names))}
(release / 'preflight-images.json').write_text(json.dumps(before))
check = "import hashlib; from pathlib import Path; print(hashlib.sha256(Path('/backend/pqkds/urls.py').read_bytes().replace(b'\\r\\n',b'\\n')).hexdigest())"
assert run('docker', 'exec', 'dvadmin3-django', 'python', '-B', '-c', check).strip() == manifest['djangoBaselines']['pqkds/urls.py']
base = 'kms-dvadmin3-django:before-pq-process-20261019'
run('docker', 'image', 'tag', before['dvadmin3-django'], base)
directory = release / 'dvadmin3-django-image'
directory.mkdir(exist_ok=True)
shutil.copytree(release / 'django', directory / 'django', dirs_exist_ok=True)
(directory / 'Dockerfile').write_text(f'FROM {base}\nCOPY django/ /backend/\n')
with (release / 'native-build.log').open('w') as log:
    subprocess.run(['docker', 'build', '--network=none', '-t', 'kms-dvadmin3-django:pq-process-20261019', str(directory)], stdout=log, stderr=subprocess.STDOUT, check=True)
with (release / 'native-tests.log').open('w') as log:
    subprocess.run(['docker', 'run', '--rm', '--network=none', '--entrypoint', 'python', 'kms-dvadmin3-django:pq-process-20261019', '-B', 'tests/test_acceptance_pq.py'], stdout=log, stderr=subprocess.STDOUT, check=True)
print('PASS: isolated native tests, no network, no DB/settings/env or production mounts')
