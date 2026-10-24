"""Package only this feature; baseline Django files must match the remote image."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TAG = 'symmetric-reclamation-20261022'


def main():
    release = ROOT/'kms-ops/releases'/TAG
    release.mkdir(exist_ok=True)
    backend = ROOT/'kms-distribute/dvadmin/backend'
    files = {**{'django/pqkds/'+name:backend/'pqkds'/name for name in (
        'acceptance_revoke.py','acceptance_symmetric_reclaim.py','acceptance_symmetric_reclaim_views.py','key_pool_service.py','urls.py')},
        'runtime/kms-acceptance-backend':ROOT/'output/symmetric-reclamation/kms-acceptance-backend',
        'apply.py':ROOT/'tools/deploy_symmetric_reclamation.py',
        'tests/test_acceptance_symmetric_reclaim_mysql.py':backend/'tests/test_acceptance_symmetric_reclaim_mysql.py'}
    for name,path in files.items():
        dest = release/name
        dest.parent.mkdir(exist_ok=True,parents=True)
        shutil.copy2(path,dest)
    shutil.copytree(ROOT/'kms-acceptance/front/dist',release/'dist',dirs_exist_ok=True)
    before = ROOT/'output/symmetric-reclamation/remote-baseline'
    for label,filename in {'urls':'urls.py','pool':'key_pool_service.py','revoke':'acceptance_revoke.py'}.items():
        base = subprocess.check_output(['git','show','HEAD:kms-distribute/dvadmin/backend/pqkds/'+filename],cwd=ROOT)
        assert base.replace(b'\r\n',b'\n')==(before/f'kms-sm4-{label}-before.py').read_bytes().replace(b'\r\n',b'\n')
    output = subprocess.check_output(['ssh','-o','BatchMode=yes','expert-machine','docker inspect kms_gateway dvadmin3-django kms_acceptance_backend --format "{{.Name}} {{.Image}}"'],text=True)
    bases = {line.split()[0].lstrip('/'):line.split()[1] for line in output.splitlines()}
    (release/'preflight-images.json').write_text(json.dumps(bases,indent=2))
    manifest = {str(p.relative_to(release)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in release.rglob('*') if p.is_file() and p.name!='manifest.json'}
    (release/'manifest.json').write_text(json.dumps({'sha256':manifest},indent=2))
    archive = ROOT/'output/symmetric-reclamation'/f'{TAG}.tar.gz'
    import tarfile
    with tarfile.open(archive,'w:gz') as tar:
        tar.add(release,arcname=TAG)
    print(json.dumps(dict(release=str(release),archive=str(archive),files=len(manifest),bytes=archive.stat().st_size)))


if __name__=='__main__':
    main()
