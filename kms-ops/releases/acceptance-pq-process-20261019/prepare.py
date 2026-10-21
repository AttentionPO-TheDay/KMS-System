"""Prepare only the reviewed acceptance/native algorithm payload, locally."""
import hashlib
import json
from pathlib import Path
import shutil

release = Path(__file__).resolve().parent
root = release.parents[2]
django_names = ['pqkds/acceptance_pq.py', 'pqkds/acceptance_pq_views.py', 'pqkds/acceptance_pq_vectors.json', 'pqkds/urls.py', 'tests/test_acceptance_pq.py']
for name in django_names:
    dest = release / 'django' / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / 'kms-distribute/dvadmin/backend' / name, dest)
shutil.copytree(root / 'kms-acceptance/front/dist', release / 'dist', dirs_exist_ok=True)
shutil.copy2(release.parent / 'acceptance-evidence-20261019/expected-codes.json', release / 'expected-codes.json')
baseline = (release / 'server-baseline/urls.py').read_bytes().replace(b'\r\n', b'\n')
manifest = {'cases': list(json.loads((release / 'expected-codes.json').read_text())),
            'djangoBaselines': {'pqkds/urls.py': hashlib.sha256(baseline).hexdigest()},
            'sha256': {}}
for prefix in ['django', 'dist']:
    for path in (release / prefix).rglob('*'):
        if path.is_file():
            manifest['sha256'][path.relative_to(release).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
binary = release / 'kms-acceptance-backend'
manifest['sha256'][binary.name] = hashlib.sha256(binary.read_bytes()).hexdigest()
(release / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print('Prepared', len(manifest['sha256']), 'hashed artifacts')
