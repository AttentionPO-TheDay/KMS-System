"""Prepare the frontend release and matching, additive node-DID API sources."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FILES = ['models.py', 'fabric_did_client.py', 'node_key_payloads.py', 'node_key_did.py',
         'node_key_did_views.py', 'node_self_views.py', 'urls.py', 'migrations/0038_nodekeydidrecord.py']
for name in FILES:
    source = ROOT / 'kms-distribute/dvadmin/backend/pqkds' / name
    destination = HERE / 'django/pqkds' / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
    ast.parse(destination.read_text(encoding='utf-8-sig'))
for project, name in [('kms-updatedel', 'updatedel'), ('kms-acceptance', 'acceptance')]:
    shutil.copytree(ROOT / project / 'front/dist', HERE / name, dirs_exist_ok=True)
(HERE / 'runtime').mkdir(exist_ok=True)
shutil.copy2(ROOT / 'kms-fabric-did/target/kms-fabric-did-1.0.0.jar', HERE / 'runtime/app.jar')
(HERE / 'tests').mkdir(exist_ok=True)
shutil.copy2(ROOT / 'kms-distribute/dvadmin/backend/tests/test_node_key_did_offline.py',
             HERE / 'tests/test_node_key_did_offline.py')
manifest = {'baseImages': {
    'nginx': 'sha256:24478694bdeea8da45c213160e74a6a36067eb787dd3bee63f3797f1dc2e88c5',
    'dvadmin3-django': 'sha256:6c2b39edfb6a26aa15246b9fb4c60d15de825aecad3d48dfa9b503e325a386e6',
    'fabric-did-bridge': 'sha256:8cf3ab805bc954c1bf8bf127ef156f4d2be667627ba967cdb1f28f6bd97c2eef'},
    'sha256': {}}
delivery = []
for folder in ['django', 'updatedel', 'acceptance', 'runtime', 'tests']:
    delivery.extend(sorted(p for p in (HERE / folder).rglob('*') if p.is_file()))
delivery.append(HERE / 'apply.py')
for path in delivery:
    manifest['sha256'][path.relative_to(HERE).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
(HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
delivery.append(HERE / 'manifest.json')
with tarfile.open(HERE / 'ui-copy-20261020.tar.gz', 'w:gz', compresslevel=4) as archive:
    for path in delivery:
        info = archive.gettarinfo(str(path), arcname=path.relative_to(HERE).as_posix())
        info.mode = 0o600
        with path.open('rb') as stream:
            archive.addfile(info, stream)
print('Prepared',len(delivery),'files; archive bytes:',(HERE/'ui-copy-20261020.tar.gz').stat().st_size)
