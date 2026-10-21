#!/usr/bin/env python3
"""Install the channel4 read-only addon and verify its existing SysPid transaction."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import time

from query_confirmed import container, request

HERE = Path(__file__).resolve().parent
IMAGE = 'kms-fabric-did:channel4-jre302-20261020'
FLAGS = ('KMS_CHAIN_WRITES_ENABLED', 'FABRIC_DID_WRITE_ENABLED',
         'FABRIC_DID_CREATE_POLICY_APPROVED')


def run(args):
    result = subprocess.run(args, capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError('Command failed: ' + ' '.join(map(str, args[:3])) +
                           '; output withheld to protect credentials')
    return result.stdout


def write(path, data, mode=0o600):
    with path.open('wb') as stream:
        stream.write(data)
    os.chmod(path, mode)


def patch_deploy(content):
    content = content.replace('\r\n', '\n')
    wrapper = re.search(r'(?ms)^compose\(\)\s*\{\n(?P<body>.*?)^\}', content)
    if not wrapper:
        raise RuntimeError('deploy.sh has no supported compose() wrapper')
    body = wrapper.group('body')
    base = r'docker compose -f "\$COMPOSE_FILE"(?: -f docker-compose\.fisco-enabled\.yml)?'
    suffix = ' -f docker-compose.did-channel4.yml'
    body = body.replace(suffix, '')
    body = body.replace(' --profile fabric-did', '')
    body, count = re.subn(base, lambda match: match.group() + suffix + ' --profile fabric-did', body)
    if count == 0:
        raise RuntimeError('Unsupported deploy.sh compose command')
    return content[:wrapper.start('body')] + body + content[wrapper.end('body'):]


def read_expected():
    expected = json.loads((HERE / 'query-parameters.json').read_text(encoding='utf-8'))
    if expected.get('status') != 'CONFIRMED' or expected.get('transactionValid') is not True:
        raise RuntimeError('Expected original transaction proof is missing')
    return expected


def overlay():
    root = './fabric-did-secrets/syspid-yunId-channel4'
    env = {'FABRIC_DID_ENABLED': 'true', 'FABRIC_DID_CHAIN_ID': 'vendor-didchannel4',
           'FABRIC_DID_METHOD_ID': 'yunId',
           'FABRIC_DID_SYSPID_RECORDS_DIR': '/run/fabric-did/records',
           **{key: 'false' for key in FLAGS}}
    return {'services': {'fabric-did-bridge': {'image': IMAGE,
        'environment': env, 'volumes': [
            {'type': 'bind', 'source': root, 'target': '/run/fabric-did', 'read_only': True},
            {'type': 'bind', 'source': root + '/work', 'target': '/run/fabric-did/work'},
            {'type': 'bind', 'source': root + '/records', 'target': '/run/fabric-did/records'},
        ]}}}


def unpack_identity(target):
    archive = HERE / 'did-identity.tar.gz'
    expected_hash = (HERE / 'did-identity.sha256').read_text(encoding='ascii').split()[0]
    actual_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual_hash != expected_hash:
        raise RuntimeError('DID identity archive checksum mismatch')
    expected = read_expected()
    folder = hashlib.sha256((expected['chainId'] + '\n' + expected['did']).encode()).hexdigest()
    allowed = {'connection.json', 'application-cert.pem', 'application-key.pem',
               'controller-public.pem', 'gm-sdk.properties', 'fabric.config.properties',
               'sys-pid.hex.txt', 'records/' + folder + '/record.json'}
    marker = target / '.identity-package'
    if target.exists():
        if not marker.is_file() or marker.read_text().strip() != actual_hash:
            raise RuntimeError('Existing DID identity directory was preserved; it is not from this addon')
        return
    with tarfile.open(archive, 'r:gz') as packed:
        members = packed.getmembers()
        if {member.name for member in members} != allowed or any(not m.isfile() for m in members):
            raise RuntimeError('Unexpected identity archive contents; no files extracted')
        target.mkdir(mode=0o700, parents=True)
        for member in members:
            destination = target / member.name
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            write(destination, packed.extractfile(member).read())
    (target / 'work').mkdir(mode=0o700)
    write(marker, (actual_hash + '\n').encode())


def verify():
    expected = read_expected()
    item = container()
    code, reply = request(item, '/internal/fabric-did/status')
    state = reply.get('data', {})
    print('DID_CONFIG ' + json.dumps({key: state.get(key) for key in
          ('status', 'enabled', 'configured', 'writeEnabled', 'missingFields')}, ensure_ascii=False), flush=True)
    if code != 200 or not state.get('enabled') or not state.get('configured'):
        print('DID_NOT_READY: install the addon and complete the missing configuration')
        return 1
    code, reply = request(item, '/internal/fabric-did/sys-pids/verify', {'sysPid': expected['sysPid']})
    result = reply.get('data', {})
    keys = ('provider', 'chainId', 'did', 'txId', 'status', 'transactionValid', 'metadataMatches', 'errorCode')
    public = {key: result.get(key) for key in keys}
    print(json.dumps(public, ensure_ascii=False, indent=2), flush=True)
    passed = code == 200 and all(result.get(key) == expected[key] for key in
            ('provider', 'chainId', 'did', 'txId', 'status', 'transactionValid', 'metadataMatches'))
    if passed:
        print('[PASS] 原SysPid交易有效，DID文档回读一致；本次未提交新交易。')
        return 0
    print('[NOT CONFIRMED] 配置已检查，但本次服务器核验尚未通过；不要重建或重发原交易。')
    return 2


def install(base):
    base = base.resolve()
    compose_path, deploy_path = base / 'docker-compose.yml', base / 'deploy.sh'
    if not compose_path.is_file() or not deploy_path.is_file() or not (base / '.env').is_file():
        raise RuntimeError('Specify the deployed main bundle directory containing docker-compose.yml, deploy.sh and .env')
    if base.is_symlink() or compose_path.is_symlink() or deploy_path.is_symlink():
        raise RuntimeError('Deployment paths must be regular files/directories')
    compose = ['docker', 'compose', '-f', str(compose_path)]
    fisco = base / 'docker-compose.fisco-enabled.yml'
    if fisco.is_file():
        compose += ['-f', str(fisco)]
    profile = ['--profile', 'fabric-did']
    config = json.loads(run(compose + profile + ['config', '--format', 'json']))
    service = config.get('services', {}).get('fabric-did-bridge')
    if not service:
        raise RuntimeError('Main deployment has no fabric-did-bridge; install the new offline main bundle first')
    image_archive = HERE / 'kms-did-compatible-image.tar'
    image_hash = (HERE / 'kms-did-compatible-image.sha256').read_text(encoding='ascii').split()[0]
    if hashlib.sha256(image_archive.read_bytes()).hexdigest() != image_hash:
        raise RuntimeError('Compatible DID image archive checksum mismatch')
    run(['docker', 'load', '-i', str(image_archive)])
    identity = run(['docker', 'image', 'inspect', IMAGE,
                    '--format', '{{.Id}}']).decode().strip()
    if identity != (HERE / 'required-image-id.txt').read_text().strip():
        raise RuntimeError('Compatible DID image does not match the addon manifest')
    unpack_identity(base / 'fabric-did-secrets/syspid-yunId-channel4')
    override_path = base / 'docker-compose.did-channel4.yml'
    patched = patch_deploy(deploy_path.read_text(encoding='utf-8-sig')).encode('utf-8')
    changed = {override_path: (json.dumps(overlay(), indent=2) + '\n').encode(), deploy_path: patched}
    originals = {p: p.read_bytes() if p.exists() else None for p in changed}
    backup = base / ('did-config-backup-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    backup.mkdir(mode=0o700)
    for path, data in originals.items():
        if data is not None:
            write(backup / path.name, data)
    effective = compose + ['-f', str(override_path)] + profile
    try:
        for path, data in changed.items():
            write(path, data, 0o700 if path == deploy_path else 0o600)
        run(['bash', '-n', str(deploy_path)])
        run(effective + ['config', '--quiet'])
    except Exception:
        for path, data in originals.items():
            if data is None:
                path.unlink(missing_ok=True)
            else:
                write(path, data, 0o700 if path == deploy_path else 0o600)
        raise
    run(effective + ['up', '-d', '--no-deps', '--no-build', '--pull', 'never',
                     '--force-recreate', 'fabric-did-bridge'])
    for _ in range(25):
        try:
            code, reply = request(container(), '/health', authenticated=False)
            if code == 200:
                break
        except (OSError, RuntimeError):
            pass
        time.sleep(1)
    else:
        raise RuntimeError('DID startup timed out; check docker logs --tail=40 kms_fabric_did')
    print('[OK] 已配置DID只读连接，仅重建DID容器，FISCO和业务写入配置保持原样。', flush=True)
    print('[INFO] 后续启停使用主部署目录的 bash deploy.sh up；不要重跑首次 install.sh。', flush=True)
    return verify()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'verify'))
    parser.add_argument('--base', type=Path, help='Main deployment directory; required for install')
    args = parser.parse_args()
    if args.action == 'install' and args.base is None:
        parser.error('install requires --base')
    os.umask(0o077)
    try:
        return install(args.base) if args.action == 'install' else verify()
    except Exception as error:
        print('[ERROR] ' + (str(error) if isinstance(error, RuntimeError) else type(error).__name__ +
                           '; inspect the DID container and network configuration'))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
