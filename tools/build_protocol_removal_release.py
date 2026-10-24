"""Package only the acceptance backend and frontend over the live images."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
TAG = 'protocol-group-removal-20261022'


def main():
    release = ROOT / 'kms-ops/releases' / TAG
    release.mkdir(parents=True, exist_ok=False)
    shutil.copytree(ROOT / 'kms-acceptance/front/dist', release / 'dist')
    (release / 'runtime').mkdir()
    shutil.copy2(ROOT / 'output/protocol-group-removal/kms-acceptance-backend',
                 release / 'runtime/kms-acceptance-backend')
    script = (ROOT / 'tools/deploy_lattice_preallocation.py').read_text(encoding='utf-8')
    script = script.replace("TAG = 'lattice-preallocation-20261022-r3'", f"TAG = '{TAG}'")
    script = script.replace("REPOS = {'dvadmin3-django': 'kms-dvadmin3-django', 'kms_acceptance_backend': 'kms-acceptance-backend', 'kms_gateway': 'kms-gateway-nginx'}",
                            "REPOS = {'kms_acceptance_backend': 'kms-acceptance-backend', 'kms_gateway': 'kms-gateway-nginx'}")
    (release / 'apply.py').write_text(script, encoding='utf-8')
    query = "import json,subprocess; cs=json.loads(subprocess.check_output(['docker','inspect','kms_gateway','kms_acceptance_backend'])); print(json.dumps({c['Name'].lstrip('/'):c['Image'] for c in cs}))"
    before = json.loads(subprocess.check_output(['ssh', '-o', 'BatchMode=yes', 'expert-machine', 'python3', '-'], input=query.encode()))
    (release / 'preflight-images.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
    manifest = {p.relative_to(release).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in release.rglob('*') if p.is_file()}
    (release / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    bundle = ROOT / 'output/protocol-group-removal' / (TAG + '.tar.gz')
    with tarfile.open(bundle, 'w:gz') as tar:
        for p in release.rglob('*'):
            if p.is_file():
                tar.add(p, arcname=TAG + '/' + p.relative_to(release).as_posix())
    print(json.dumps(dict(bundle=str(bundle), bytes=bundle.stat().st_size, files=len(manifest))))


if __name__ == '__main__':
    main()
