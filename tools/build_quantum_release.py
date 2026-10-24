"""Package the already-verified evaluator image, Go binary and acceptance UI."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
TAG = 'quantum-evaluation-20261022'


def main():
    out = ROOT/'output/quantum-deployment'
    release = ROOT/'kms-ops/releases'/TAG
    release.mkdir(parents=True, exist_ok=True)
    (release/'runtime').mkdir(exist_ok=True)
    shutil.copy2(out/'kms-acceptance-backend', release/'runtime/kms-acceptance-backend')
    shutil.copy2(ROOT/'tools/deploy_quantum_evaluation.py', release/'apply.py')
    shutil.copytree(ROOT/'kms-acceptance/front/dist', release/'dist', dirs_exist_ok=True)
    shutil.copytree(ROOT/'kms-acceptance/quantum', release/'source/quantum',
                    ignore=shutil.ignore_patterns('__pycache__'), dirs_exist_ok=True)
    script = "import json,subprocess;cs=json.loads(subprocess.check_output(['docker','inspect','kms_gateway','kms_acceptance_backend']));print(json.dumps({c['Name'].lstrip('/'):c['Image'] for c in cs}))"
    baseline = json.loads(subprocess.check_output(['ssh', '-o', 'BatchMode=yes', 'expert-machine', 'python3 -'], input=script.encode()))
    (release/'preflight-images.json').write_text(json.dumps(baseline, indent=2), encoding='utf-8')
    image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', 'kms-quantum-evaluator:local']))[0]
    (release/'quantum-image.json').write_text(json.dumps({'imageId': image['Id'], 'size': image['Size']}), encoding='utf-8')
    archive = out/'quantum-image.tar.gz'
    if not archive.exists():
        print('EXPORTING_QUANTUM_IMAGE', flush=True)
        with gzip.open(archive.with_suffix('.part'), 'wb', compresslevel=1) as f:
            proc = subprocess.Popen(['docker', 'save', 'kms-quantum-evaluator:local'], stdout=subprocess.PIPE)
            shutil.copyfileobj(proc.stdout, f, length=4<<20)
            proc.stdout.close()
            assert proc.wait() == 0
        archive.with_suffix('.part').replace(archive)
    shutil.copy2(archive, release/'quantum-image.tar.gz')
    hashes = {}
    for path in release.rglob('*'):
        if path.is_file() and path.name != 'manifest.json':
            h = hashlib.sha256()
            with path.open('rb') as f:
                for chunk in iter(lambda: f.read(4<<20), b''):
                    h.update(chunk)
            hashes[path.relative_to(release).as_posix()] = h.hexdigest()
    (release/'manifest.json').write_text(json.dumps({'sha256': hashes}, indent=2), encoding='utf-8')
    # The large image archive is transferred separately to avoid recompressing it.
    bundle = out/(TAG+'.tar.gz')
    with tarfile.open(bundle, 'w:gz') as tar:
        for path in release.rglob('*'):
            if path.is_file() and path.name != 'quantum-image.tar.gz':
                tar.add(path, arcname=TAG+'/'+path.relative_to(release).as_posix())
    print(json.dumps({'release': str(release), 'bundleBytes': bundle.stat().st_size,
                      'imageArchiveBytes': archive.stat().st_size, 'files': len(hashes)}), flush=True)


if __name__ == '__main__':
    main()
