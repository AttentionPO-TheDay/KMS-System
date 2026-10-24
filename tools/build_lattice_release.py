"""Prepare a release containing only the lattice change over the live baseline."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
TAG = 'lattice-preallocation-20261022-r3'


def main():
    release = ROOT / 'kms-ops/releases' / TAG
    package = release / 'pqkds'
    package.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'kms-distribute/dvadmin/backend/pqkds'
    for name in ('models.py', 'node_self_views.py', 'key_pool_service.py', 'urls.py',
                 'lattice_preallocation.py', 'lattice_preallocation_math.py', 'lattice_test_views.py'):
        text = (source / name).read_text(encoding='utf-8')
        if name == 'models.py':
            # External-node work is local and not part of this release.
            lines = text.splitlines(True)
            definitions = [node for node in ast.parse(text).body if isinstance(node, ast.ClassDef) and node.name == 'ExternalNodeActivation']
            for node in reversed(definitions):
                del lines[node.lineno - 1:node.end_lineno]
            text = ''.join(line for line in lines if not line.lstrip().startswith('initialization_profile ='))
        (package / name).write_text(text, encoding='utf-8')
    (package / 'migrations').mkdir(exist_ok=True)
    shutil.copy2(source / 'migrations/0041_lattice_preallocation.py', package / 'migrations/0041_lattice_preallocation.py')
    shutil.copytree(ROOT / 'output/lattice-verification/wheels', release / 'wheels', dirs_exist_ok=True)
    shutil.copytree(ROOT / 'kms-acceptance/front/dist', release / 'dist', dirs_exist_ok=True)
    (release / 'runtime').mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'output/lattice-verification/kms-acceptance-backend', release / 'runtime/kms-acceptance-backend')
    shutil.copy2(ROOT / 'tools/deploy_lattice_preallocation.py', release / 'apply.py')
    script = "import json,subprocess; cs=json.loads(subprocess.check_output(['docker','inspect','dvadmin3-django','kms_gateway','kms_acceptance_backend'])); print(json.dumps({c['Name'].lstrip('/'):c['Image'] for c in cs}))"
    before = json.loads(subprocess.check_output(['ssh', '-o', 'BatchMode=yes', 'expert-machine', 'python3', '-'], input=script.encode()))
    (release / 'preflight-images.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
    manifest = {p.relative_to(release).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in release.rglob('*') if p.is_file() and p.name != 'manifest.json'}
    (release / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    bundle = ROOT / 'output/lattice-verification' / (TAG + '.tar.gz')
    with tarfile.open(bundle, 'w:gz') as tar:
        for p in release.rglob('*'):
            if p.is_file(): tar.add(p, arcname=TAG + '/' + p.relative_to(release).as_posix())
    print(json.dumps(dict(bundle=str(bundle), bytes=bundle.stat().st_size, files=len(manifest))))


if __name__ == '__main__': main()
