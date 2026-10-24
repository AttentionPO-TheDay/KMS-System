#!/usr/bin/env python3
"""Run concurrency tests in newly created Docker resources, then remove them."""
from pathlib import Path
import subprocess
import uuid


def run(args):
    return subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout


def main():
    suffix = uuid.uuid4().hex[:8]
    network, database = 'kms-external-sscl-test-' + suffix, 'kms-external-sscl-test-db-' + suffix
    root = Path(__file__).resolve().parents[1]
    try:
        run(['docker', 'network', 'create', '--internal', network])
        run(['docker', 'run', '-d', '--name', database, '--network', network,
             '--tmpfs', '/var/lib/mysql', '-e', 'MYSQL_ROOT_PASSWORD=offline-only-not-production',
             '-e', 'MYSQL_DATABASE=external_sscl_test', 'mysql:8.0', '--innodb-buffer-pool-size=64M'])
        print(run(['docker', 'run', '--rm', '--network', network,
                   '--mount', 'type=bind,source=' + str(root / 'kms-distribute/dvadmin/backend') + ',target=/work,readonly',
                   '-e', 'EXTERNAL_SSCL_DISPOSABLE_TEST=1', '-e', 'EXTERNAL_SSCL_TEST_MYSQL_HOST=' + database,
                   '--entrypoint', 'python', 'kms-dvadmin3-django:local', '/work/tests/test_external_sscl_mysql.py']))
    except subprocess.CalledProcessError as exc:
        print(exc.stdout[-6000:])
        raise
    finally:
        subprocess.run(['docker', 'rm', '-f', database], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['docker', 'network', 'rm', network], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == '__main__': main()
