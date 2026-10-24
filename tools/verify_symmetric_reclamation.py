"""Run real SM4 reclamation tests in a disposable Docker MySQL database."""
from pathlib import Path
import subprocess
import uuid


def run(args):
    return subprocess.run(args, check=True, text=True, encoding='utf-8', errors='replace', stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout


def main():
    root = Path(__file__).resolve().parents[1]
    suffix = uuid.uuid4().hex[:8]
    network, database = 'kms-sm4-test-' + suffix, 'kms-sm4-test-db-' + suffix
    output = root / 'output/symmetric-reclamation'
    output.mkdir(parents=True, exist_ok=True)
    # Copy source over the image's backend to retain compiled Kyber libraries.
    script = '''import os, shutil, time, runpy
for name in ('acceptance_revoke.py', 'acceptance_symmetric_reclaim.py', 'acceptance_symmetric_reclaim_views.py', 'key_pool_service.py'):
    shutil.copyfile('/source/pqkds/'+name, '/backend/pqkds/'+name)
os.environ['DJANGO_SETTINGS_MODULE']='application.settings'
import django
django.setup()
from django.db import connection
for attempt in range(90):
    try:
        connection.ensure_connection()
        break
    except Exception:
        if attempt == 89: raise
        time.sleep(.5)
from django.core.management import call_command
call_command('migrate', interactive=False, verbosity=0)
runpy.run_path('/source/tests/test_acceptance_symmetric_reclaim_mysql.py', run_name='__main__')
'''
    try:
        run(['docker', 'network', 'create', '--internal', network])
        run(['docker', 'run', '-d', '--name', database, '--network', network,
             '--tmpfs', '/var/lib/mysql', '-e', 'MYSQL_ROOT_PASSWORD=disposable-test-only',
             '-e', 'MYSQL_DATABASE=sm4_test', 'mysql:8.0', '--innodb-buffer-pool-size=64M'])
        print(run(['docker', 'run', '--rm', '--network', network,
            '--mount', f'type=bind,source={root / "kms-distribute/dvadmin/backend"},target=/source,readonly',
            '--mount', f'type=bind,source={output},target=/evidence',
            '-e', 'DATABASE_HOST='+database, '-e', 'DATABASE_NAME=sm4_test',
            '-e', 'DATABASE_PASSWORD=disposable-test-only', '-e', 'KMS_ACCEPTANCE_MYSQL_TEST=1',
            '-e', 'PYTHONIOENCODING=utf-8',
            '-e', 'KMS_ACCEPTANCE_EVIDENCE_OUTPUT=/evidence/mysql-evidence.json',
            '--entrypoint', 'python', 'kms-dvadmin3-django:local', '-c', script]))
    except subprocess.CalledProcessError as exc:
        print(exc.stdout[-5000:])
        raise
    finally:
        subprocess.run(['docker', 'rm', '-f', database], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['docker', 'network', 'rm', network], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == '__main__':
    main()
