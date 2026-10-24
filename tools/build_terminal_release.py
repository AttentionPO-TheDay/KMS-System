"""Package the instrumented acceptance executor and terminal frontend only."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def main(tag):
    if not tag or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in tag):
        raise ValueError('Use a lowercase release tag')
    release = ROOT / 'kms-ops/releases' / tag
    release.mkdir(parents=True, exist_ok=False)
    shutil.copytree(ROOT / 'kms-acceptance/front/dist', release / 'dist')
    (release / 'runtime').mkdir()
    shutil.copy2(ROOT / 'output/terminal-execution/kms-acceptance-backend', release / 'runtime/kms-acceptance-backend')
    script = (ROOT / 'tools/deploy_lattice_preallocation.py').read_text(encoding='utf-8')
    old_tag = "TAG = 'lattice-preallocation-20261022-r3'"
    old_repos = "REPOS = {'dvadmin3-django': 'kms-dvadmin3-django', 'kms_acceptance_backend': 'kms-acceptance-backend', 'kms_gateway': 'kms-gateway-nginx'}"
    assert script.count(old_tag) == script.count(old_repos) == 1
    script = script.replace(old_tag, f"TAG = '{tag}'").replace(old_repos, "REPOS = {'kms_acceptance_backend': 'kms-acceptance-backend', 'kms_gateway': 'kms-gateway-nginx'}")
    (release / 'apply.py').write_text(script, encoding='utf-8')
    query = "import json,subprocess; cs=json.loads(subprocess.check_output(['docker','inspect','kms_gateway','kms_acceptance_backend'])); print(json.dumps({c['Name'].lstrip('/'):c['Image'] for c in cs}))"
    before = json.loads(subprocess.check_output(['ssh', '-o', 'BatchMode=yes', 'expert-machine', 'python3', '-'], input=query.encode()))
    (release / 'preflight-images.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
    manifest = {p.relative_to(release).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in release.rglob('*') if p.is_file()}
    (release / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    bundle = ROOT / 'output/terminal-execution' / (tag + '.tar.gz')
    with tarfile.open(bundle, 'w:gz') as tar:
        for p in release.rglob('*'):
            if p.is_file():
                tar.add(p, arcname=tag + '/' + p.relative_to(release).as_posix())
    print(json.dumps(dict(bundle=str(bundle), bytes=bundle.stat().st_size, files=len(manifest))))


if __name__ == '__main__':
    main(sys.argv[1])
