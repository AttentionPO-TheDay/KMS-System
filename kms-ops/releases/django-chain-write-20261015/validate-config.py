"""Compare rendered Compose configuration in memory without printing credentials."""
import copy
import json
import subprocess
from pathlib import Path

root = Path('/home/rbf/kms-sys')
release = root / 'releases/django-chain-write-20261015'
prefix = ['docker', 'compose', '-p', 'kms-ops', '-f', str(root / 'docker-compose.yml')]

def config(override):
    return json.loads(subprocess.check_output(prefix + ['-f', str(override), '--profile', 'fabric-did',
                     'config', '--format', 'json'], cwd=root))

before = config(root / 'docker-compose.fisco-enabled.yml')
after = config(release / 'docker-compose.fisco-enabled.yml')
expected = copy.deepcopy(before)
environment = expected['services']['dvadmin3-django']['environment']
assert environment['KMS_CHAIN_BACKEND'] == 'legacy'
assert environment['KMS_CHAIN_WRITES_ENABLED'] == 'false'
environment['KMS_CHAIN_WRITES_ENABLED'] = 'true'
assert expected == after, 'Candidate changes more than the Django chain-write flag'
print('CONFIG_OK: only dvadmin3-django.KMS_CHAIN_WRITES_ENABLED false -> true')
