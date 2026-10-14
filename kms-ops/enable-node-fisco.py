#!/usr/bin/env python3
"""Enable the node registration outbox while preserving server FISCO/TLS configuration.

Run in the server deployment directory after loading the new application images.
Never reads or prints a private key; never redeploys the contract or edits .env.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time


def configure(config):
    services = config.get('services', {})
    env = services.get('updatedel-java', {}).get('environment', {})
    contract = env.get('FISCO_CONTRACT_ADDRESS', '') if isinstance(env, dict) else ''
    if not re.fullmatch(r'0x[0-9a-fA-F]{40}', contract) or int(contract, 16) == 0:
        raise ValueError('Existing FISCO contract address is missing; no config changed')
    if env.get('KMS_CHAIN_WRITES_ENABLED') != 'true' or env.get('KMS_LIFECYCLE_CHAIN_SYNC_ENABLED') != 'true':
        raise ValueError('Existing Java FISCO writes are not enabled; no config changed')
    django = services.setdefault('dvadmin3-django', {})
    existing = django.setdefault('environment', {})
    if not isinstance(existing, dict):
        raise ValueError('Unsupported overlay environment layout; no config changed')
    existing.update(KMS_NODE_FISCO_ENABLED='true', KMS_NODE_FISCO_CONTRACT_ADDRESS=contract.lower(),
                    KMS_NODE_FISCO_BASE='http://updatedel-java:9082', KMS_CHAIN_BACKEND='legacy',
                    KMS_CHAIN_WRITES_ENABLED='false')  # Keep old Web3 chain writes paused.
    return config


def run(command):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise RuntimeError('Command failed; inspect container logs locally (output withheld)')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--activate', action='store_true')
    parser.add_argument('--backfill', action='store_true', help='Queue existing ACTIVE key registrations without generating keys')
    args = parser.parse_args()
    if args.backfill and not args.activate:
        raise ValueError('--backfill requires --activate')
    root = Path.cwd()
    path = root / 'docker-compose.fisco-enabled.yml'
    original = path.read_bytes()
    config = configure(json.loads(original))  # Existing connect-existing-fisco.py writes JSON-compatible YAML.
    new = (json.dumps(config, indent=2) + '\n').encode()
    compose = ['docker', 'compose', '-f', 'docker-compose.yml', '-f', path.name, '--profile', 'fabric-did']
    backup = root / ('node-fisco-overlay-backup-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.yml')
    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as file:
        file.write(original)
    fd, temporary = tempfile.mkstemp(prefix='.node-fisco-', dir=root)
    try:
        with os.fdopen(fd, 'wb') as file:
            file.write(new)
        run(['docker', 'compose', '-f', 'docker-compose.yml', '-f', temporary, '--profile', 'fabric-did', 'config', '--quiet'])
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print('[OK] Only node FISCO evidence enabled; Web3 writes remain paused; .env/TLS/chain data unchanged')
    print('[OK] Overlay backup: ' + backup.name)
    if args.activate:
        run(compose + ['up', '-d', '--no-deps', '--force-recreate', 'generate-java', 'updatedel-java', 'dvadmin3-django', 'nginx'])
        if args.backfill:
            for _ in range(60):
                ready = subprocess.run(['docker', 'exec', 'dvadmin3-django', 'test', '-f', '/tmp/kms-node-fisco-schema-ready'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if ready.returncode == 0:
                    break
                time.sleep(2)
            else:
                raise RuntimeError('Django migrations not ready; do not backfill until startup succeeds')
            run(['docker', 'exec', 'dvadmin3-django', 'python', 'manage.py', 'process_node_fisco_evidence', '--backfill'])
        print('[OK] Updated services recreated; node public registration worker started')
        print('[INFO] Verify chainBinding CONFIRMED and transactionValid; activation alone is not a transaction receipt')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('[ERROR] ' + (str(error) if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__))
        raise SystemExit(1)
