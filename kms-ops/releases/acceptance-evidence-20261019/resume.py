"""Resume after staging-only test fixes; refuse any intervening deployment."""
from pathlib import Path
import subprocess
root = Path('/home/rbf/kms-sys')
release = Path(__file__).resolve().parent
assert (root / 'docker-compose.yml').read_bytes() == (release / 'backup/docker-compose.yml').read_bytes()
log = (release / 'django-offline-test.log').read_text()
assert 'Ran 22 tests' in log and log.rstrip().endswith('OK')
source = (release / 'apply.py').read_text()
start = source.index('backup.mkdir(mode=0o700)')
end = source.index("compose = ['docker', 'compose'")
source = source[:start] + "compose_file = root / 'docker-compose.yml'\noriginal = json.loads(compose_file.read_text())\n" + source[end:]
exec(compile(source, str(release / 'apply.py'), 'exec'), {'__file__': str(release / 'apply.py'), '__name__': '__main__'})
